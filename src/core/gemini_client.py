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


PROMPT_BASE = """Você é um extrator estruturado de dados de relatórios fiscais brasileiros.

Extraia do documento em anexo TODAS as linhas de filiais e seus valores.

## CATÁLOGO DE FILIAIS (nome canônico ← sinônimos JÁ conhecidos)

Cada relatório vem de um setor diferente e cada setor tem apelidos/abreviações
próprios pras filiais. O catálogo abaixo lista as filiais oficiais e os
sinônimos que o app já conhece — mas é INCOMPLETO por natureza, novas
abreviações aparecem sempre.

{catalogo}

## COMO NORMALIZAR "filial_documento"

Sua tarefa é sempre devolver o NOME CANÔNICO (a coluna "Nome" do catálogo),
NÃO o texto bruto do documento. Para chegar lá, tente na ordem:

1. Match exato (ignora caixa e acentos) com o nome canônico ou com um
   sinônimo já listado.
2. Se falhou, TENTE INFERIR pela convenção brasileira de abreviação:
   - Iniciais de cidade: "SAJ" → Santo Antonio de Jesus; "CTG" → Contagem;
     "LEM" → Luis Eduardo Magalhaes; "VDC" → Vitoria da Conquista.
   - Palavra parcial ou truncada: "CTGM" / "CONTAG" → Contagem;
     "L VERDE" / "LN VERDE" → Serra Verde (Linha Verde é o mesmo lugar);
     "P AFONSO" → Paulo Afonso; "RIB NEVES" → Ribeirao das Neves.
   - Códigos numéricos: "CD 040", "CD-040", "CD300", "300" → CD Ribeirao das
     Neves (mesmo código TOTVS); "301" → CD Campina Verde; "502" → ADM Barao.
   - Prefixos operacionais: "CD X" é sempre um centro de distribuição;
     "ADM X" é administrativo/comercial; sem prefixo é loja.
3. Ignore prefixos institucionais tipo "MULTICOM ATACADO E VAREJO S/A -".
4. Só devolva o texto bruto quando NÃO houver candidato plausível (ex.:
   filial nova que a empresa acabou de abrir e nem existe no catálogo).
   Nesse caso o app cai num fuzzy match depois.

## AMBIGUIDADES: LOJA vs CD com nome de cidade parecido

Algumas cidades têm loja física E centro de distribuição com nomes muito
parecidos (ex.: Feira de Santana loja e CD Feira de Santana; Ribeirao das
Neves loja e CD Ribeirao das Neves). O relatório usa UMA de duas convenções
possíveis pra distinguir — e você precisa OLHAR O RELATÓRIO INTEIRO ANTES
de decidir qual convenção esse relatório específico está usando.

**Convenção A — marca a LOJA:**
Se aparecer "X (LOJA)" ou "X LOJA" ou "LOJA X" em qualquer linha do relatório,
então a convenção é marcar explicitamente a loja:
- "FEIRA DE SANTANA (LOJA)"  → NOME CANÔNICO: "Feira de Santana"
- "FEIRA DE SANTANA"  (sem qualificador) → NOME CANÔNICO: "CD Feira de Santana"

**Convenção B — marca o CD:**
Se aparecer "CD X" ou "CD F. DE X" em qualquer linha do relatório, então a
convenção é marcar explicitamente o CD:
- "CD FEIRA DE SANTANA" → NOME CANÔNICO: "CD Feira de Santana"
- "FEIRA DE SANTANA"  (sem qualificador) → NOME CANÔNICO: "Feira de Santana"

**Como escolher:** olhe TODAS as linhas do documento antes de resolver a
primeira ambiguidade. Se você vir qualquer linha com "(LOJA)" ou "LOJA",
use convenção A. Se você vir qualquer linha com "CD" na frente, use
convenção B. As duas convenções não coexistem no mesmo relatório.

**Casos raros:** se aparecer só uma "X" solta e nenhum marcador `(LOJA)`
nem `CD` no relatório inteiro, e a cidade tem loja+CD no catálogo, devolva
o texto bruto "X" — o app vai tentar resolver por fuzzy matching ou o
operador ajusta manualmente.

NÃO invente códigos. Você só precisa devolver o nome canônico; o app resolve
o código sozinho.

## REGRAS GERAIS DE VALORES

- Ignore linhas de totalização geral (ex.: "TOTAL GERAL").
- Ignore marcações manuscritas (√, X, riscos, canetadas). Elas NÃO indicam
  pular linha — extraia sempre tudo.
- Os valores estão em Real brasileiro (formato "R$ 1.234,56"). Retorne SEMPRE
  como número (float) sem separador de milhar e com ponto decimal.
  Ex.: "R$ 45.527,93" → 45527.93.
- Uma célula vazia deve virar 0 (zero) ou ser omitida do objeto "valores".

## FORMATO DA RESPOSTA

Retorne APENAS um JSON válido nesta estrutura, sem markdown, sem comentários:

{{
  "imposto": "{imposto_chave}",
  "mes_ref": "MM",
  "ano_ref": "AAAA",
  "linhas": [
    {{
      "filial_documento": "NOME CANÔNICO do catálogo, ou texto do documento se não bater",
      "valores": {{ ... veja regras específicas abaixo ... }},
      "total_filial": 60666.36
    }}
  ]
}}

"""


# Regras específicas por imposto (build-90). Cada imposto tem particularidades
# de layout (colunas por tipo de folha vs coluna única), fonte da referência
# (extraída do PDF vs calculada da data de emissão), e cabeçalhos típicos.
# Adicionar imposto novo aqui + entry em mapeamento.json.

PROMPT_IRRF = """## REGRAS ESPECÍFICAS DESTE RELATÓRIO — IRRF

Este é um relatório de **IRRF (Imposto de Renda Retido na Fonte) sobre Folha
de Pagamento**. Layout típico: uma linha por filial, com MÚLTIPLAS colunas
separando por tipo de folha.

- Colunas esperadas em "valores": **{colunas}**.
  Use esses nomes exatos como chaves.
- Cada filial pode ter valor em uma ou mais colunas simultaneamente.
- Identifique o mês/ano de referência (ex.: "IRRF 07/2026" → mes_ref="07",
  ano_ref="2026"). Se não aparecer, deixe em branco.

Exemplo de linha bem extraída:
```
{{"filial_documento": "Contagem",
  "valores": {{"ADIANTAMENTO": 45527.93, "MENSAL": 14831.09}},
  "total_filial": 60359.02}}
```
"""

PROMPT_INSS = """## REGRAS ESPECÍFICAS DESTE RELATÓRIO — INSS

Este é um relatório de **INSS sobre Folha de Pagamento**. Layout típico:
uma linha por filial, com UMA ÚNICA COLUNA de valor total (sem separação
por tipo de folha).

- Coluna única: **{colunas}** (só o nome "VALOR").
  Coloque o valor total da filial sob essa chave.
- NÃO tente separar por tipo de folha. É sempre um valor consolidado.
- **NÃO PRECISA identificar mês/ano** de referência no PDF — deixe
  `mes_ref` e `ano_ref` em BRANCO (`""`). O app calcula automaticamente
  a competência (mês anterior à data de emissão) na hora de montar a
  observação. Se você tentar adivinhar, provavelmente vai errar porque
  o PDF do INSS pode ter datas de mês antigo, atual e futuro
  simultaneamente (data de emissão do relatório, competência, vencimento).

Exemplo de linha bem extraída:
```
{{"filial_documento": "Contagem",
  "valores": {{"VALOR": 160090.96}},
  "total_filial": 160090.96}}
```
"""


PROMPT_FGTS_CONSIG = """## REGRAS ESPECÍFICAS DESTE RELATÓRIO — FGTS + Consignado

Este é o relatório mensal de **FGTS + Empréstimo Consignado**. Layout:
uma linha por filial, com DUAS colunas de valor lado a lado —
"VALOR FGTS" e "VALOR EMPRÉSTIMO CONSIGNADO".

- Colunas esperadas em "valores": **{colunas}** (use exatamente
  essas chaves: `FGTS` e `CONSIG`).
- Cada linha do relatório vira DOIS lançamentos separados (um pra
  FGTS, um pro Consignado) — mas você só entrega os valores; a
  separação é feita pelo app.
- Se algum campo aparecer como "R$ -" (traço), "0,00" ou vazio,
  registre como 0 (ou omita a chave); o app pula lançamentos com
  valor zero.
- O relatório traz o mês/ano no cabeçalho no formato "MM.AAAA"
  (ex.: "08.2026"). Coloque em `mes_ref` = "08" e `ano_ref` = "2026".
- Nomes das filiais vêm no formato "MULTICOM ATACADO E VAREJO S/A - <NOME>".
  Devolva SÓ o `<NOME>` no `filial_documento` — o prefixo "MULTICOM..."
  é ruído.
- Ignore a linha "TOTAL" no rodapé e a linha "TOTAL GFD - FGTS DIGITAL"
  (esse é o consolidado geral, não uma filial).

Exemplo de linha bem extraída:
```
{{"filial_documento": "Contagem",
  "valores": {{"FGTS": 33350.18, "CONSIG": 21959.80}},
  "total_filial": 55309.98}}
```

Se uma filial tem só FGTS (ex.: Araxá com Empréstimo em branco),
devolva só a chave FGTS:
```
{{"filial_documento": "Araxa",
  "valores": {{"FGTS": 21789.98}},
  "total_filial": 21789.98}}
```
"""


PROMPTS_POR_IMPOSTO: dict[str, str] = {
    "IRRF": PROMPT_IRRF,
    "INSS": PROMPT_INSS,
    "FGTS_CONSIG": PROMPT_FGTS_CONSIG,
}


def _construir_prompt(imposto: Imposto, mapping: MappingRepository) -> str:
    """Junta o prompt base (catálogo + regras universais) com a seção
    específica do imposto. Se não houver seção específica, usa um
    genérico que só menciona as colunas."""
    especifico_tmpl = PROMPTS_POR_IMPOSTO.get(imposto.chave)
    if especifico_tmpl is None:
        log.warning(
            "Prompt específico não definido pra imposto '%s' — usando fallback genérico",
            imposto.chave,
        )
        especifico_tmpl = (
            "## REGRAS ESPECÍFICAS DESTE RELATÓRIO — {chave}\n\n"
            "Colunas esperadas em 'valores': **{{colunas}}**. Use esses nomes exatos como chaves.\n"
        ).format(chave=imposto.chave)

    especifico = especifico_tmpl.format(colunas=", ".join(imposto.colunas_tipo_folha))

    base = PROMPT_BASE.format(
        catalogo=_construir_catalogo(mapping),
        imposto_chave=imposto.chave,
    )
    return base + especifico


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

        prompt = _construir_prompt(imposto, mapping)

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

    # ---------- NFS-e (módulo Orçamento, build-95..107) ----------

    def extrair_notas_nfse(self, arquivo_pdf: Path, extrair_anotacao_caneta: bool = False) -> list[dict]:
        """Extrai lista de dicts NFS-e do PDF. Cada página = 1 nota.

        Sempre extrai: pagina, numero, data_emissao, valor,
                       cnpj_prestador (validação client-side), cnpj_tomador
                       (resolve filial de emissão).
        Se `extrair_anotacao_caneta=True`: também extrai `anotacao_caneta`
                       (texto escrito à mão no rosto da nota — Pluxee usa
                       pra identificar a filial destinatária real).

        Zero tolerância a chute: campo ilegível vem em branco.
        """
        arquivo_pdf = Path(arquivo_pdf)
        if not arquivo_pdf.exists():
            raise FileNotFoundError(arquivo_pdf)

        log.info("extrair_notas_nfse: lendo %s (caneta=%s)",
                 arquivo_pdf.name, extrair_anotacao_caneta)
        with open(arquivo_pdf, "rb") as f:
            dados = f.read()
        b64 = base64.standard_b64encode(dados).decode("ascii")

        prompt = _PROMPT_NFSE_COM_CANETA if extrair_anotacao_caneta else _PROMPT_NFSE
        payload = {
            "contents": [{"parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "application/pdf", "data": b64}},
            ]}],
            "generationConfig": {"response_mime_type": "application/json"},
        }
        url = f"{API_BASE}/models/{self._model_name}:generateContent"
        r = requests.post(url, params={"key": self._api_key}, json=payload, timeout=180)
        log.info("extrair_notas_nfse: HTTP %s", r.status_code)
        if r.status_code >= 400:
            raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:400]}")

        data = r.json()
        try:
            texto = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Resposta Gemini sem texto: {str(data)[:400]}") from e

        parsed = self._parse_json(texto)
        notas = parsed.get("notas") or []
        resultado: list[dict] = []
        for i, n in enumerate(notas):
            try:
                resultado.append({
                    "pagina":         int(n.get("pagina") or (i + 1)),
                    "numero":         str(n.get("numero", "")).strip(),
                    "data_emissao":   str(n.get("data_emissao", "")).strip(),
                    "valor":          float(n.get("valor") or 0.0),
                    "cnpj_prestador": "".join(c for c in str(n.get("cnpj_prestador", "")) if c.isdigit()),
                    "cnpj_tomador":   "".join(c for c in str(n.get("cnpj_tomador", "")) if c.isdigit()),
                    "anotacao_caneta": str(n.get("anotacao_caneta", "")).strip(),
                })
            except (TypeError, ValueError) as e:
                log.warning("extrair_notas_nfse: linha %d inválida (%s): %r", i, e, n)
                resultado.append({
                    "pagina": i + 1, "numero": "", "data_emissao": "", "valor": 0.0,
                    "cnpj_prestador": "", "cnpj_tomador": "", "anotacao_caneta": "",
                })
        log.info("extrair_notas_nfse: %d notas extraídas", len(resultado))
        return resultado

    # ---------- DAE Bahia (build-101) ----------

    def extrair_daes(self, arquivo_pdf: Path) -> list[dict]:
        """Extrai lista de DAEs (guias ICMS Bahia) de um PDF. Cada DAE
        vira {pagina, numero_serie, cnpj, tipo, valor, vencimento, referencia}.
        Deduplicação de vias é responsabilidade do prompt (retornar 1 por
        Nº de série único).
        """
        arquivo_pdf = Path(arquivo_pdf)
        if not arquivo_pdf.exists():
            raise FileNotFoundError(arquivo_pdf)

        log.info("extrair_daes: lendo %s", arquivo_pdf.name)
        with open(arquivo_pdf, "rb") as f:
            dados = f.read()
        b64 = base64.standard_b64encode(dados).decode("ascii")

        payload = {
            "contents": [{"parts": [
                {"text": _PROMPT_DAE},
                {"inline_data": {"mime_type": "application/pdf", "data": b64}},
            ]}],
            "generationConfig": {"response_mime_type": "application/json"},
        }
        url = f"{API_BASE}/models/{self._model_name}:generateContent"
        r = requests.post(url, params={"key": self._api_key}, json=payload, timeout=180)
        log.info("extrair_daes: HTTP %s", r.status_code)
        if r.status_code >= 400:
            raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:400]}")

        data = r.json()
        try:
            texto = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Resposta Gemini sem texto: {str(data)[:400]}") from e

        parsed = self._parse_json(texto)
        daes = parsed.get("daes") or []
        resultado: list[dict] = []
        for i, d in enumerate(daes):
            try:
                resultado.append({
                    "pagina":       int(d.get("pagina") or (i + 1)),
                    "numero_serie": str(d.get("numero_serie", "")).strip(),
                    "cnpj":         "".join(c for c in str(d.get("cnpj", "")) if c.isdigit()),
                    "tipo":         str(d.get("tipo", "")).strip(),
                    "valor":        float(d.get("valor") or 0.0),
                    "vencimento":   str(d.get("vencimento", "")).strip(),
                    "referencia":   str(d.get("referencia", "")).strip(),
                })
            except (TypeError, ValueError) as e:
                log.warning("extrair_daes: linha %d inválida (%s): %r", i, e, d)
                resultado.append({
                    "pagina": i + 1, "numero_serie": "", "cnpj": "",
                    "tipo": "", "valor": 0.0, "vencimento": "", "referencia": "",
                })
        log.info("extrair_daes: %d DAE(s) extraída(s)", len(resultado))
        return resultado


_PROMPT_NFSE = """Você é um extrator de Notas Fiscais de Serviço eletrônica
(NFS-e / DANFSe) brasileiras.

Cada página do PDF anexo é UMA NFS-e. Extraia por nota:

1. `numero`: o "Número da NFS-e" (campo padrão do cabeçalho DANFSe, também
   chamado "Nº NFS-e" ou "Número"). Dígitos apenas. Ex.: "216559".

2. `data_emissao`: a "Data e Hora da Emissão da NFS-e" (só a data, no formato
   "AAAA-MM-DD"). Ex.: "2026-08-19". NÃO confundir com "Data e Hora da
   Emissão da DPS" (a DPS é o pedido, não a nota).

3. `valor`: o "Valor Total da NFS-e" ou "Valor Líquido da NFS-e" (campo do
   rodapé). Float com ponto decimal, sem separador de milhar. Ex.: 17.35.

4. `cnpj_prestador`: o "CNPJ / CPF" do quadro "Prestador de Serviços" —
   14 dígitos apenas (sem pontuação). Ex.: "20211412000188" (do texto
   "20.211.412/0001-88").

5. `cnpj_tomador`: o "CPF/CNPJ" do quadro "Tomador de Serviços" —
   14 dígitos. É pelo tomador que o app resolve a filial de emissão.

Retorne APENAS um JSON válido, sem markdown, sem comentários:

{
  "notas": [
    {"pagina": 1, "numero": "216559", "data_emissao": "2026-08-19",
     "valor": 17.35, "cnpj_prestador": "12345678000199",
     "cnpj_tomador": "28548486000116"}
  ]
}

Se algum campo estiver ilegível, deixe em branco ("" ou 0.0) — o app pede
revisão manual. NUNCA invente valores. Melhor vazio que chute.
Se uma página não for NFS-e (capa, folha separadora), pule.
"""


_PROMPT_NFSE_COM_CANETA = """Você é um extrator de Notas Fiscais de Serviço
eletrônica (NFS-e / DANFSe) brasileiras + ANOTAÇÕES MANUSCRITAS no rosto
da nota.

Cada página do PDF anexo é UMA NFS-e. Extraia por nota:

1. `numero`: "Número da NFS-e" (dígitos). Ex.: "0841044".
2. `data_emissao`: "Data Emissão" no formato "AAAA-MM-DD".
3. `valor`: "Valor Total da Nota" (float, ponto decimal).
4. `cnpj_prestador`: CNPJ do "Prestador de Serviços" — 14 dígitos.
5. `cnpj_tomador`: CNPJ do "Tomador de Serviços" — 14 dígitos.
6. `anotacao_caneta`: texto ESCRITO A CANETA (manuscrito) no corpo da
   nota — normalmente no meio do papel, em azul ou preto, letra de mão.
   Costuma ser o NOME DE UMA CIDADE ou LOJA (ex.: "Luis Eduardo",
   "Juazeiro", "Feira de Santana", "CD Ribeirão"). Ignore assinaturas
   e carimbos oficiais — só o rabisco/anotação livre. Se não houver
   rabisco ou não der pra ler, deixe "". NUNCA CHUTE — se estiver
   embaralhado ou parcialmente coberto, prefira vazio.

Retorne APENAS um JSON válido:

{
  "notas": [
    {"pagina": 1, "numero": "0841044", "data_emissao": "2026-01-22",
     "valor": 1096.63, "cnpj_prestador": "20211412000188",
     "cnpj_tomador": "28548486000388", "anotacao_caneta": "Luis Eduardo"}
  ]
}

NUNCA invente número, CNPJ ou anotação de caneta. Melhor vazio que
chute. Se uma página não for NFS-e (capa, verso em branco), pule.
"""


# ---------- DAE Bahia (build-101) ----------

_PROMPT_DAE = """Você é um extrator de DAE (Documento de Arrecadação Estadual)
da Secretaria da Fazenda da Bahia — a guia usada pra pagar ICMS sobre
energia elétrica.

Cada página do PDF pode conter UMA ou DUAS DAEs iguais (via + via —
2 canhotos do mesmo documento). NÃO conte a mesma DAE duas vezes:
extraia UMA linha por documento único (identificado pelo "Nº de série
/ Nosso Número"). Se aparecer 2 vias do mesmo Nº de série, retorne
apenas 1 entrada.

Se a mesma página tem 2 DAEs DIFERENTES (Nº de série diferente),
extraia AS DUAS.

Campos por DAE:

1. `numero_serie`: o "Nº DE SÉRIE / NOSSO NÚMERO" (dígitos apenas).
   Ex.: "1962122751", "1962123053".

2. `cnpj`: o "CNPJ / CPF" do contribuinte (14 dígitos apenas, sem
   pontuação). Ex.: "28548486001007" (do texto "28.548.486/0010-07").

3. `tipo`: qual imposto é. Olhe o campo "ESPECIFICAÇÃO DA RECEITA":
     - Se contém "REGIME NORMAL"       → devolva "regime_normal"
     - Se contém "ADIC FUNDO POBREZA"
       ou "ADIC. FUNDO POBREZA"
       ou "FUNDO POBREZA"              → devolva "adic_fundo_pobreza"
     - Caso contrário devolva ""       (o app pede revisão manual)

4. `valor`: o "TOTAL A RECOLHER" (ou "VALOR PRINCIPAL" se total não
   estiver visível). Float com ponto decimal. Ex.: 8845.61, 862.99.

5. `vencimento`: a "DATA DE VENCIMENTO" no formato "AAAA-MM-DD".
   Ex.: "2026-09-30" (do texto "30/09/2026").

6. `referencia`: o campo "REFERÊNCIA" (mês/ano da competência).
   Formato "MM/AAAA". Ex.: "07/2026". Só pra rastreabilidade.

Ignore: número da NF de energia mencionada em Informações
Complementares, código de município, códigos de barras — o app só
precisa dos 6 campos acima.

Retorne APENAS um JSON válido, sem markdown, sem comentários:

{
  "daes": [
    {
      "pagina": 1,
      "numero_serie": "1962122751",
      "cnpj": "28548486001007",
      "tipo": "regime_normal",
      "valor": 8845.61,
      "vencimento": "2026-09-30",
      "referencia": "07/2026"
    }
  ]
}

Se algum campo estiver ilegível, deixe em branco ("" ou 0.0) — o app
pede revisão manual. NUNCA invente valores nem CNPJ. Melhor vazio que
chute (documento fiscal).
"""


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

    # Regra específica por imposto — sobrescreve o que veio do Gemini.
    # INSS: a observação sempre faz referência ao MÊS ANTERIOR à data
    # de emissão (competência da folha), independente do que aparecer
    # no relatório. Ver mapeamento.json: "mes_ref_regra".
    if imposto.mes_ref_regra == "mes_anterior_emissao":
        y = data_emissao.year
        m = data_emissao.month - 1
        if m == 0:
            m = 12
            y -= 1
        mes_ref = f"{m:02d}"
        ano_ref = str(y)
        log.info(
            "montar_lancamentos: regra 'mes_anterior_emissao' aplicada — "
            "emissão %s → ref %s/%s", data_emissao, mes_ref, ano_ref,
        )

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

            # Observação: por coluna (FGTS_CONSIG) ou template global.
            obs_template = imposto.observacao_por_coluna.get(tipo_folha) or imposto.observacao_template
            observacao = obs_template.format(
                mes_ref=mes_ref, ano_ref=ano_ref, tipo_folha=tipo_folha,
                filial_nome=filial.nome,
            )

            # Espécie: por coluna (FGTS→MFGTS, CONSIG→CONSIG) ou padrão.
            especie = imposto.especie_por_coluna.get(tipo_folha) or imposto.especie_totvs

            # Pessoa: código Consinco da filial (FGTS_CONSIG) ou padrão do imposto.
            if imposto.pessoa_por_filial:
                if filial.codigo_consinco is None:
                    log.warning(
                        "montar_lancamentos: filial %s (%d) sem codigo_consinco no de-para — "
                        "linha %s / %s pulada", filial.nome, filial.codigo, tipo_folha, valor
                    )
                    continue
                pessoa_codigo = filial.codigo_consinco
            else:
                pessoa_codigo = imposto.pessoa_codigo

            lancamentos.append(Lancamento(
                filial_codigo=filial.codigo,
                filial_nome=filial.nome,
                especie=especie,
                pessoa_codigo=pessoa_codigo,
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
