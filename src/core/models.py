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
