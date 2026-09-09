from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .logger import log


def _default_path() -> Path:
    base = Path.home() / ".lancamento-automatico"
    base.mkdir(parents=True, exist_ok=True)
    return base / "settings.json"


DEFAULTS: dict[str, Any] = {
    "gemini_api_key": "",
    "gemini_model": "gemini-2.0-flash-exp",
    "delays": {
        "entre_campos_ms": 150,
        "apos_especie_ms": 800,
        "apos_pessoa_ms": 800,
        "apos_gerar_parcelas_ms": 1500,
        "apos_confirmar_ms": 2000,
        "timeout_janela_s": 20,
    },
    "rpa": {
        "titulo_janela": "Inclusão de Títulos",
        "titulo_janela_erro": "",
        "max_tentativas_duplicidade": 10,
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
