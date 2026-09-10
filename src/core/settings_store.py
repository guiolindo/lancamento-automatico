from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .logger import log


def _default_path() -> Path:
    """Localiza pasta de config com fallback se Path.home() falhar."""
    import os
    import sys
    candidatos = []
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
            return base / "settings.json"
        except Exception:  # noqa: BLE001
            continue
    base = Path(os.getcwd())
    return base / "settings.json"


DEFAULTS: dict[str, Any] = {
    "gemini_api_key": "",
    "gemini_model": "gemini-3.5-flash-lite",
    "delays": {
        # Delays enxutos. Se algum PC específico ficar rápido demais e errar,
        # editar ~/.lancamento-automatico/settings.json.
        "apos_click_ms": 100,             # tempo pro foco chegar na VM
        "apos_selectall_ms": 40,          # tempo pro Ctrl+A registrar
        "intervalo_digitacao_s": 0.003,   # entre teclas do typewrite
        "entre_campos_ms": 80,
        "apos_especie_ms": 400,           # banco/agência auto-preencher
        "apos_pessoa_ms": 400,            # P.Nota auto-preencher
        "apos_gerar_parcelas_ms": 1000,
        "apos_confirmar_ms": 1000,
        "timeout_janela_s": 30,
    },
    "rpa": {
        "titulo_janela": "Operador Financeiro",
        "titulo_janela_erro": "",
        "max_tentativas_duplicidade": 10,
        "confirmar_automaticamente": True,
    },
    "ultima_pasta_upload": "",
    "tema": "escuro",
}


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or _default_path()
        self._data: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self._data = json.loads(json.dumps(DEFAULTS))
            self.save()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except (OSError, json.JSONDecodeError):
            log.exception("Falha lendo settings.json — usando defaults")
            self._data = json.loads(json.dumps(DEFAULTS))
        self._merge_defaults(self._data, DEFAULTS)
        self._migrar_modelos_obsoletos()

    def _migrar_modelos_obsoletos(self) -> None:
        """Substitui nomes de modelo Gemini removidos/descontinuados."""
        obsoletos = {
            "gemini-2.0-flash-exp": "gemini-3.5-flash-lite",
            "gemini-2.5-flash-lite": "gemini-3.5-flash-lite",
            "gemini-2.5-flash": "gemini-3.5-flash-lite",
            "gemini-1.0-pro": "gemini-3.5-flash-lite",
            "gemini-pro": "gemini-3.5-flash-lite",
            "gemini-pro-vision": "gemini-3.5-flash-lite",
        }
        atual = self._data.get("gemini_model")
        if atual in obsoletos:
            novo = obsoletos[atual]
            log.info("Migrando modelo Gemini: %s -> %s", atual, novo)
            self._data["gemini_model"] = novo
            self.save()

    def _merge_defaults(self, current: dict, defaults: dict) -> None:
        for k, v in defaults.items():
            if k not in current:
                current[k] = json.loads(json.dumps(v))
            elif isinstance(v, dict) and isinstance(current[k], dict):
                self._merge_defaults(current[k], v)

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get(self, key: str, default: Any = None) -> Any:
        parts = key.split(".")
        cur: Any = self._data
        for p in parts:
            if not isinstance(cur, dict) or p not in cur:
                return default
            cur = cur[p]
        return cur

    def set(self, key: str, value: Any) -> None:
        parts = key.split(".")
        cur = self._data
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = value
        self.save()

    @property
    def data(self) -> dict[str, Any]:
        return self._data
