from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path


def _log_dir() -> Path:
    """Localiza pasta de log com fallback se Path.home() falhar."""
    import os
    candidatos = []
    try:
        candidatos.append(Path.home())
    except Exception:  # noqa: BLE001
        pass
    for var in ("USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
        val = os.environ.get(var)
        if val:
            candidatos.append(Path(val))
    # último recurso: ao lado do exe
    candidatos.append(Path(sys.argv[0]).resolve().parent)

    for c in candidatos:
        try:
            base = c / ".lancamento-automatico" / "logs"
            base.mkdir(parents=True, exist_ok=True)
            return base
        except Exception:  # noqa: BLE001
            continue
    # se ainda assim falhou, usa /tmp equivalente
    base = Path(os.getcwd()) / "logs"
    base.mkdir(parents=True, exist_ok=True)
    return base


def setup_logger(name: str = "lancamento", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # StreamHandler pro stdout, forçando UTF-8 para não quebrar em Windows
    # com cp1252 (que não aceita → ✎ etc.). reconfigure() existe no Python 3.7+.
    try:
        if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    logfile = _log_dir() / f"{datetime.now():%Y-%m-%d}.log"
    fh = logging.FileHandler(logfile, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


log = setup_logger()
