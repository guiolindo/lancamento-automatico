"""
Calibração dos campos da tela 'Inclusão de Títulos' do TOTVS.

Como o TOTVS roda em VM/RemoteApp, pywinauto NÃO consegue enxergar os
controles internos da janela (ela chega ao PC local como um "quadro"
opaco vindo do RDP). A estratégia é clicar em coordenadas relativas ao
canto da janela — o usuário faz uma calibração inicial informando a
posição de cada campo, e o robô guarda esses offsets.

A calibração vale enquanto o layout do TOTVS não muda. Se o operador
mudar de resolução ou o TOTVS receber update, é só recalibrar.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Ordem canônica dos campos que precisam ser calibrados.
# (chave, rótulo humano, é_botão)
CAMPOS = [
    ("empresa",           "Campo Empresa (código)",         False),
    ("especie",           "Campo Espécie",                  False),
    ("pessoa",            "Campo Pessoa (código)",          False),
    ("observacao",        "Campo Observação",               False),
    ("nro_documento",     "Campo Nro.Documento",            False),
    ("dt_emissao",        "Campo Dt.Emissão",               False),
    ("dt_contabilizacao", "Campo Dt.Contabilização",        False),
    ("vencimento",        "Campo Vencimento Inicial",       False),
    ("valor",             "Campo Valor Faturado",           False),
    ("btn_gerar_parcelas","Botão Gerar Parcelas",           True),
    ("btn_confirmar",     "Botão + (gravar lançamento)",    True),
]


@dataclass
class Calibracao:
    titulo_janela: str = "Inclusão de Títulos"
    # offset (dx, dy) do campo em relação ao canto SUPERIOR-ESQUERDO da janela
    campos: dict[str, tuple[int, int]] = field(default_factory=dict)

    def esta_completa(self) -> bool:
        return all(chave in self.campos for chave, _, _ in CAMPOS)

    def falta_calibrar(self) -> list[str]:
        return [chave for chave, _, _ in CAMPOS if chave not in self.campos]

    def to_dict(self) -> dict:
        return {
            "titulo_janela": self.titulo_janela,
            "campos": {k: list(v) for k, v in self.campos.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Calibracao":
        return cls(
            titulo_janela=d.get("titulo_janela", "Inclusão de Títulos"),
            campos={k: tuple(v) for k, v in (d.get("campos") or {}).items() if len(v) == 2},
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
    return _default_dir() / "calibracao.json"


def carregar(path: Optional[Path] = None) -> Calibracao:
    p = Path(path) if path else default_path()
    if not p.exists():
        return Calibracao()
    try:
        with open(p, "r", encoding="utf-8") as f:
            return Calibracao.from_dict(json.load(f))
    except Exception:  # noqa: BLE001
        return Calibracao()


def salvar(calib: Calibracao, path: Optional[Path] = None) -> None:
    p = Path(path) if path else default_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(calib.to_dict(), f, indent=2, ensure_ascii=False)
