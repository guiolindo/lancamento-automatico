from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from enum import Enum
from typing import Optional


class TipoFilial(str, Enum):
    LOJA = "LOJA"
    CD = "CD"
    ADM = "ADM"


class StatusLancamento(str, Enum):
    PENDENTE = "PENDENTE"
    EM_ANDAMENTO = "EM_ANDAMENTO"
    SUCESSO = "SUCESSO"
    FALHA = "FALHA"
    IGNORADO = "IGNORADO"


@dataclass
class Filial:
    codigo: int
    nome: str
    tipo: TipoFilial
    aliases: list[str] = field(default_factory=list)
    # Código da filial no Consinco. Usado por impostos que declaram
    # `pessoa_por_filial: true` (FGTS_CONSIG, build-113) — o campo Pessoa
    # do TOTVS recebe o codigo_consinco desta filial em vez do
    # `pessoa_codigo` fixo do imposto.
    codigo_consinco: Optional[int] = None


@dataclass
class Imposto:
    chave: str
    descricao: str
    especie_totvs: str
    especie_descricao: str
    pessoa_codigo: int
    pessoa_nome: str
    observacao_template: str
    colunas_tipo_folha: list[str] = field(default_factory=list)
    # Regra pra mes_ref/ano_ref que vão pra `observacao_template`.
    # None (default): usa o que o Gemini extraiu do PDF.
    # "mes_anterior_emissao": ignora Gemini; usa (data_emissao - 1 mês).
    #   Usado pelo INSS: emissão 20/07/2026 → observação "REFERENTE A: 06/2026".
    mes_ref_regra: Optional[str] = None
    # Campos multi-espécie (build-113 — FGTS_CONSIG).
    # `pessoa_por_filial: True` → pessoa_codigo do lançamento vem da
    # filial (Filial.codigo_consinco), não do imposto.
    pessoa_por_filial: bool = False
    # `especie_por_coluna[COL] = "MFGTS"` → cada coluna do relatório
    # vira lançamento com espécie própria (em vez de todos usarem
    # `especie_totvs` do imposto). Fallback: `especie_totvs`.
    especie_por_coluna: dict = field(default_factory=dict)
    # `observacao_por_coluna[COL] = "FGTS MENSAL - REF: {mes_ref}/..."`
    # → cada coluna vira lançamento com observação própria.
    # Fallback: `observacao_template`.
    observacao_por_coluna: dict = field(default_factory=dict)


@dataclass
class Lancamento:
    filial_codigo: int
    filial_nome: str
    especie: str
    pessoa_codigo: int
    observacao: str
    valor: float
    data_emissao: date
    data_contabilizacao: date
    vencimento: date
    tipo_folha: str
    mes_ref: str
    ano_ref: str
    nro_documento: Optional[str] = None
    status: StatusLancamento = StatusLancamento.PENDENTE
    erro: Optional[str] = None
    tentativas: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["data_emissao"] = self.data_emissao.isoformat()
        d["data_contabilizacao"] = self.data_contabilizacao.isoformat()
        d["vencimento"] = self.vencimento.isoformat()
        d["status"] = self.status.value
        return d


@dataclass
class LinhaExtracao:
    """Uma linha bruta extraída do relatório pelo Gemini (uma filial × colunas)."""
    filial_documento: str
    valores: dict[str, float]
    total_filial: Optional[float] = None


@dataclass
class NotaDespesa:
    """Uma NFS-e ou DAE a ser lançada no módulo Orçamento.

    Campos "core" (NFS-e OTIMO, build-96): pagina, numero, data_emissao,
    valor, data_lancto, template_chave.

    Campos "DAE" (build-101): cnpj identifica a filial; tipo_dae escolhe
    a observação/descrição (regime_normal | adic_fundo_pobreza); vencimento
    vem do próprio DAE; filial_codigo/filial_nome são resolvidos via
    cnpjs_filiais.json na hora de montar a lista.

    Campos "Pluxee" (build-107): cnpj_prestador valida contra
    template.cnpj_esperado; cnpj_tomador resolve `filial_emissao_codigo`
    (empresa da aba Nota + linha 1 da contab); anotacao_caneta resolve
    `filial_caneta_codigo` (fuzzy match contra cnpjs_filiais.json →
    linha 2 da contab + string da observação).
    """
    pagina: int
    numero: str
    data_emissao: Optional[date]
    valor: float
    data_lancto: date
    template_chave: str
    # DAE-only
    cnpj: Optional[str] = None
    tipo_dae: Optional[str] = None       # "regime_normal" | "adic_fundo_pobreza"
    vencimento_dae: Optional[date] = None
    filial_codigo: Optional[int] = None
    filial_nome: Optional[str] = None
    # Pluxee (nota que endereça 2 filiais — emissão vs caneta)
    cnpj_prestador: Optional[str] = None
    cnpj_tomador: Optional[str] = None
    filial_emissao_codigo: Optional[int] = None
    filial_emissao_nome: Optional[str] = None
    anotacao_caneta: Optional[str] = None
    filial_caneta_codigo: Optional[int] = None
    filial_caneta_nome: Optional[str] = None
    # Estado
    status: StatusLancamento = StatusLancamento.PENDENTE
    erro: Optional[str] = None
    motivo_ignorado: Optional[str] = None  # ex: "já lançada"
