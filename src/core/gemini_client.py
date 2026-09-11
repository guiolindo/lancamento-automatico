from __future__ import annotations

import base64
import json
import re
from datetime import date
from pathlib import Path
from typing import Optional

import requests

from .logger import log
from .mapping import MappingRepository
from .models import Filial, Imposto, Lancamento, LinhaExtracao, StatusLancamento

# Cliente REST puro para a API do Gemini. Substituiu a lib google-generativeai,
# que puxa gRPC/Cython (cygrpc.pyd) e crasha silenciosamente em bundles
# Nuitka standalone. Usamos requests direto, o que é mais leve, mais
# previsível e não tem dependência problemática.


API_BASE = "https://generativelanguage.googleapis.com/v1beta"

_MIME_POR_EXTENSAO = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


PROMPT_TEMPLATE = """Você é um extrator estruturado de dados de relatórios fiscais brasileiros.

Extraia do documento em anexo TODAS as linhas de filiais e seus valores por tipo de folha.

## CATÁLOGO DE FILIAIS (nome canônico ← sinônimos aceitos)

Cada relatório vem de um setor diferente e usa abreviações/apelidos próprios
para as filiais. Use este catálogo para normalizar: se o documento mostrar
uma abreviação (ex.: "CTG", "L VERDE", "SAJ", "CD 040"), retorne o
NOME CANÔNICO correspondente na chave "filial_documento", NÃO o texto bruto.

{catalogo}

Regras adicionais para o casamento:
- Match é case-insensitive e ignora acentos.
- Ignore prefixos como "MULTICOM ATACADO E VAREJO S/A -".
- Se nenhum item do catálogo bater, aí sim devolva o texto exato do documento
  (o app tenta um fuzzy match depois).

## REGRAS GERAIS

- Ignore linhas de totalização geral (ex.: "TOTAL GERAL").
- Ignore marcações manuscritas (√, X, riscos, canetadas). Elas NÃO indicam pular linha — extraia sempre tudo.
- Os valores estão em Real brasileiro (formato "R$ 1.234,56"). Retorne SEMPRE como número (float) sem separador de milhar e com ponto decimal. Ex.: "R$ 45.527,93" -> 45527.93.
- Uma célula vazia deve virar 0 (zero) ou ser omitida do objeto "valores".
- Identifique o mês e ano de referência do imposto (ex.: "IRRF 07/2026" → mes_ref="07", ano_ref="2026").
- As colunas esperadas são exatamente: {colunas}. Use esses nomes como chaves em "valores".

Retorne APENAS um JSON válido nesta estrutura, sem markdown, sem comentários:

{{
  "imposto": "{imposto_chave}",
  "mes_ref": "MM",
  "ano_ref": "AAAA",
  "linhas": [
    {{
      "filial_documento": "NOME CANÔNICO do catálogo, ou texto do documento se não bater",
      "valores": {{
        "ADIANTAMENTO": 45527.93,
        "FERIAS": 307.34,
        "MENSAL": 14831.09
      }},
      "total_filial": 60666.36
    }}
  ]
}}
"""


def _construir_catalogo(mapping: MappingRepository) -> str:
    """Monta o texto do catálogo pra injetar no prompt.
    Formato: '- Nome Canônico (código NNN) ← alias1, alias2, ...'"""
    linhas = []
    for filial in mapping.filiais:
        aliases = [a for a in filial.aliases if a.upper().strip() != filial.nome.upper().strip()]
        sinonimos = ", ".join(aliases) if aliases else "—"
        linhas.append(f"- {filial.nome} (código {filial.codigo}) ← {sinonimos}")
    return "\n".join(linhas) if linhas else "(catálogo vazio)"


class GeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-lite"):
        if not api_key:
            raise ValueError("Chave da API Gemini não configurada")
        log.info("GeminiClient: inicializando (REST puro, sem gRPC)")
        self._api_key = api_key
        self._model_name = model
        log.info("GeminiClient: pronto")

    def extrair(self, arquivo: Path, imposto: Imposto, mapping: MappingRepository) -> dict:
        arquivo = Path(arquivo)
        if not arquivo.exists():
            raise FileNotFoundError(arquivo)

        prompt = PROMPT_TEMPLATE.format(
            colunas=", ".join(imposto.colunas_tipo_folha),
            imposto_chave=imposto.chave,
            catalogo=_construir_catalogo(mapping),
        )

        log.info("extrair: lendo arquivo %s", arquivo.name)
        with open(arquivo, "rb") as f:
            dados = f.read()
        mime = _MIME_POR_EXTENSAO.get(arquivo.suffix.lower(), "application/octet-stream")
        b64 = base64.standard_b64encode(dados).decode("ascii")

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": mime, "data": b64}},
                    ]
                }
            ],
            "generationConfig": {"response_mime_type": "application/json"},
        }

        url = f"{API_BASE}/models/{self._model_name}:generateContent"
        log.info("extrair: POST %s (arquivo %s bytes, mime %s)", url, len(dados), mime)
        r = requests.post(
            url,
            params={"key": self._api_key},
            json=payload,
            timeout=120,
        )
        log.info("extrair: HTTP %s", r.status_code)
        if r.status_code >= 400:
            trecho = r.text[:500]
            raise RuntimeError(f"Gemini HTTP {r.status_code}: {trecho}")

        data = r.json()
        try:
            texto = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Resposta Gemini sem texto: {data}") from e
        log.info("extrair: resposta recebida (%d chars)", len(texto))
        return self._parse_json(texto)

    def _parse_json(self, texto: str) -> dict:
        try:
            return json.loads(texto)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", texto, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            log.error("Resposta Gemini não é JSON válido: %s", texto[:500])
            raise


def montar_lancamentos(
    extracao: dict,
    imposto: Imposto,
    mapping: MappingRepository,
    data_emissao: date,
    data_contabilizacao: Optional[date] = None,
    vencimento: Optional[date] = None,
) -> tuple[list[Lancamento], list[LinhaExtracao]]:
    """
    Transforma a extração bruta do Gemini em uma lista plana de lançamentos
    (um por combinação filial × tipo de folha com valor > 0).

    Retorna também a lista de linhas não resolvidas (filial sem match no de-para).
    """
    data_contabilizacao = data_contabilizacao or data_emissao
    vencimento = vencimento or data_emissao

    mes_ref = extracao.get("mes_ref") or ""
    ano_ref = extracao.get("ano_ref") or ""

    lancamentos: list[Lancamento] = []
    nao_resolvidas: list[LinhaExtracao] = []

    for linha in extracao.get("linhas", []):
        filial_doc = linha.get("filial_documento", "").strip()
        valores = linha.get("valores", {}) or {}
        linha_obj = LinhaExtracao(
            filial_documento=filial_doc,
            valores={k: float(v or 0) for k, v in valores.items()},
            total_filial=(float(linha["total_filial"]) if linha.get("total_filial") is not None else None),
        )

        filial: Optional[Filial] = mapping.resolve_filial(filial_doc)
        if filial is None:
            nao_resolvidas.append(linha_obj)
            continue

        for tipo_folha, valor in linha_obj.valores.items():
            if not valor or valor <= 0:
                continue
            observacao = imposto.observacao_template.format(
                mes_ref=mes_ref, ano_ref=ano_ref, tipo_folha=tipo_folha,
            )
            lancamentos.append(Lancamento(
                filial_codigo=filial.codigo,
                filial_nome=filial.nome,
                especie=imposto.especie_totvs,
                pessoa_codigo=imposto.pessoa_codigo,
                observacao=observacao,
                valor=round(valor, 2),
                data_emissao=data_emissao,
                data_contabilizacao=data_contabilizacao,
                vencimento=vencimento,
                tipo_folha=tipo_folha,
                mes_ref=mes_ref,
                ano_ref=ano_ref,
                status=StatusLancamento.PENDENTE,
            ))

    log.info("Montagem: %d lançamentos gerados, %d filiais não resolvidas",
             len(lancamentos), len(nao_resolvidas))
    return lancamentos, nao_resolvidas
