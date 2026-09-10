from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Optional

from .logger import log
from .mapping import MappingRepository
from .models import Filial, Imposto, Lancamento, LinhaExtracao, StatusLancamento

# NÃO importar google.generativeai nem PIL aqui no topo. São libs pesadas
# que podem falhar no boot do bundle e derrubar o app inteiro (o erro
# STATUS_FATAL_APP_EXIT que vimos). Importamos dentro das funções que
# realmente usam.


PROMPT_TEMPLATE = """Você é um extrator estruturado de dados de relatórios fiscais brasileiros.

Extraia do documento em anexo TODAS as linhas de filiais e seus valores por tipo de folha.

Regras:
- Ignore linhas de totalização geral (ex.: "TOTAL GERAL").
- Ignore marcações manuscritas (√, X, riscos, canetadas). Elas NÃO indicam pular linha — extraia sempre tudo.
- Os valores estão em Real brasileiro (formato "R$ 1.234,56"). Retorne SEMPRE como número (float) sem separador de milhar e com ponto decimal. Ex.: "R$ 45.527,93" -> 45527.93.
- Uma célula vazia deve virar 0 (zero) ou ser omitida do objeto "valores".
- Preserve o nome da filial EXATAMENTE como está escrito no documento (mesmo com "MULTICOM ATACADO E VAREJO S/A -" no início).
- Identifique o mês e ano de referência do imposto (ex.: "IRRF 07/2026" → mes_ref="07", ano_ref="2026").
- As colunas esperadas são exatamente: {colunas}. Use esses nomes como chaves em "valores".

Retorne APENAS um JSON válido nesta estrutura, sem markdown, sem comentários:

{{
  "imposto": "{imposto_chave}",
  "mes_ref": "MM",
  "ano_ref": "AAAA",
  "linhas": [
    {{
      "filial_documento": "nome exato da filial no documento",
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


class GeminiClient:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-lite"):
        if not api_key:
            raise ValueError("Chave da API Gemini não configurada")
        log.info("GeminiClient: importando google.generativeai")
        import google.generativeai as genai  # lazy: só ao usar
        log.info("GeminiClient: configurando (transporte REST — evita crash de gRPC em bundle Nuitka)")
        # transport='rest' força HTTP puro e evita o carregamento do
        # cygrpc.pyd que crasha silenciosamente em bundles standalone.
        genai.configure(api_key=api_key, transport="rest")
        log.info("GeminiClient: instanciando GenerativeModel(%s)", model)
        self._genai = genai
        self._model = genai.GenerativeModel(model)
        self._model_name = model
        log.info("GeminiClient: pronto")

    def extrair(self, arquivo: Path, imposto: Imposto) -> dict:
        arquivo = Path(arquivo)
        if not arquivo.exists():
            raise FileNotFoundError(arquivo)

        prompt = PROMPT_TEMPLATE.format(
            colunas=", ".join(imposto.colunas_tipo_folha),
            imposto_chave=imposto.chave,
        )

        log.info("extrair: carregando arquivo")
        conteudo = self._carregar_arquivo(arquivo)
        log.info("extrair: enviando %s para Gemini (%s)", arquivo.name, self._model_name)

        resp = self._model.generate_content(
            [prompt, conteudo],
            generation_config={"response_mime_type": "application/json"},
        )
        log.info("extrair: resposta recebida (%d chars)", len(resp.text or ""))
        texto = resp.text or ""
        return self._parse_json(texto)

    def _carregar_arquivo(self, arquivo: Path):
        suffix = arquivo.suffix.lower()
        if suffix == ".pdf":
            return self._genai.upload_file(str(arquivo))
        from PIL import Image  # lazy
        return Image.open(arquivo)

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
