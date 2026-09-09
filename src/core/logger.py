from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path


def _log_dir() -> Path:
    base = Path.home() / ".lancamento-automatico" / "logs"
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

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    logfile = _log_dir() / f"{datetime.now():%Y-%m-%d}.log"
    fh = logging.FileHandler(logfile, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


log = setup_logger()
