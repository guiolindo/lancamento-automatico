"""
Calibração da tela 'Notas Fiscais de Despesa' do TOTVS Orçamento (build-96).

Módulo separado do `calibracao.py` (que é do Operador Financeiro) porque
o Orçamento tem tela diferente: 3 abas (Nota, Financeiro, Contabilização),
campos diferentes, botões diferentes (+ pra novo, Autorizar pra fechar).

Mesma estratégia: coordenadas relativas ao canto SUPERIOR-ESQUERDO da
janela, capturadas via calibração inicial. Vale enquanto o layout do
TOTVS não muda.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Ordem canônica dos campos a calibrar no Orçamento.
# (chave, rótulo humano, é_botão)
CAMPOS = [
    # ---- Aba Nota ----
    ("empresa",              "Campo Empresa (código)",              False),
    ("nat_despesa",          "Campo Natureza da Despesa (código)",  False),
    ("pessoa",               "Campo Pessoa (código)",               False),
    ("nota_fiscal",          "Campo Nota Fiscal (número)",          False),
    ("data_emissao",         "Campo Data de Emissão",               False),
    ("data_lancto",          "Campo Data de Lançamento",            False),
    ("st_doc",               "Campo St.Doc",                        False),
    ("modelo",               "Campo Modelo",                        False),
    ("observacao_fiscal",    "Campo Observação (aba Nota)",         False),
    ("valor_total_nf",       "Campo Valor Total da NF",             False),
    ("check_icms",           "Checkbox ICMS (aba Nota)",            True),
    # ---- Aba Financeiro ----
    ("aba_financeiro",       "Aba Financeiro (título)",             True),
    ("observacao_financeira","Campo Observação (aba Financeiro)",   False),
    ("radio_vencimento",     "Radio 'Vencimento' (modo parcelas)",  True),
    ("qtd_parcelas",         "Campo Qtd. Parcelas",                 False),
    ("dias_entre_venc",      "Campo Dias entre vencimentos",        False),
    ("data_vencimento",      "Campo Data do 1º Vencimento",         False),
    ("btn_gerar",            "Botão Gerar parcelas (Financeiro)",   True),
    # ---- Aba Contabilização ----
    ("aba_contabilizacao",   "Aba Contabilização (título)",         True),
    ("contab_linha1_valor",  "Célula Valor — linha 1 da contab.",   False),
    ("contab_linha2_valor",  "Célula Valor — linha 2 da contab.",   False),
    # ---- Botões finais ----
    ("btn_novo_mais",        "Botão + (novo/gravar)",               True),
    ("btn_autorizar",        "Botão Autorizar",                     True),
]

# Campos OPCIONAIS: popup de duplicidade + tecla F2 (limpar tela).
# Necessários se `duplicidade_regra` = "pular_ja_lancada" no template.
CAMPOS_OPCIONAIS = [
    ("popup_dupl_ok",   "Botão OK do popup 'Aviso' de duplicidade",  True),
    ("popup_atencao_sim","Botão Sim do popup 'Atenção' (após F2)",   True),
]


@dataclass
class CalibracaoOrcamento:
    # Título parcial que casa com a janela Orçamento — user informou
    # que a janela começa com 'Orçamento' (build-95).
    titulo_janela: str = "Orçamento"
    campos: dict[str, tuple[int, int]] = field(default_factory=dict)
    cores: dict[str, tuple[int, int, int]] = field(default_factory=dict)

    def esta_completa(self) -> bool:
        return all(chave in self.campos for chave, _, _ in CAMPOS)

    def falta_calibrar(self) -> list[str]:
        return [chave for chave, _, _ in CAMPOS if chave not in self.campos]

    def to_dict(self) -> dict:
        return {
            "titulo_janela": self.titulo_janela,
            "campos": {k: list(v) for k, v in self.campos.items()},
            "cores": {k: list(v) for k, v in self.cores.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CalibracaoOrcamento":
        return cls(
            titulo_janela=d.get("titulo_janela", "Orçamento"),
            campos={k: tuple(v) for k, v in (d.get("campos") or {}).items() if len(v) == 2},
            cores={k: tuple(v) for k, v in (d.get("cores") or {}).items() if len(v) == 3},
        )


def _default_dir() -> Path:
    candidatos: list[Path] = []
    try:
        candidatos.append(Path.home())
    except Exception:  # noqa: BLE001
        pass
    for var in ("USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
        val = os.environ.get(var)
        if val:
            candidatos.append(Path(val))
    candidatos.append(Path(sys.argv[0]).resolve().parent)
    for c in candidatos:
        try:
            base = c / ".lancamento-automatico"
            base.mkdir(parents=True, exist_ok=True)
            return base
        except Exception:  # noqa: BLE001
            continue
    return Path(os.getcwd())


def default_path() -> Path:
    return _default_dir() / "calibracao_orcamento.json"


def carregar(path: Optional[Path] = None) -> CalibracaoOrcamento:
    p = Path(path) if path else default_path()
    if not p.exists():
        return CalibracaoOrcamento()
    try:
        with open(p, "r", encoding="utf-8") as f:
            return CalibracaoOrcamento.from_dict(json.load(f))
    except Exception:  # noqa: BLE001
        return CalibracaoOrcamento()


def salvar(calib: CalibracaoOrcamento, path: Optional[Path] = None) -> None:
    p = Path(path) if path else default_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(calib.to_dict(), f, indent=2, ensure_ascii=False)
