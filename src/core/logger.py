from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


# Regex de redação. Cobre 3 formatos comuns em que a chave da API pode
# vazar num traceback ou log:
#   ?key=AIza...          → URL do requests em exception
#   x-goog-api-key: AIza  → dump de headers, se algum debug logar
#   key=AIza (raw)        → algum log manual antigo
# Cada match preserva o prefixo (key=/api-key: etc) pra o operador
# entender O QUE foi redigido, mas o valor vira ***REDACTED***.
_REDACT_PATTERNS = [
    re.compile(r"([?&](?:key|api[_-]?key)=)[^&\s\"'>]+", re.IGNORECASE),
    re.compile(r"(x-goog-api-key\s*[:=]\s*)['\"]?[A-Za-z0-9_.\-]{16,}['\"]?", re.IGNORECASE),
    # AIza... é o prefixo de chave do Google (39 chars); mesmo se
    # aparecer solta em algum lugar sem "key=" prefixo, redige.
    re.compile(r"\b(AIza)[A-Za-z0-9_\-]{20,}\b"),
    # AQ.Ab8... prefixo de "API key v3" do Google Gemini (visto em prod).
    re.compile(r"\b(AQ\.[A-Za-z0-9]{2,4})[A-Za-z0-9_\-]{20,}\b"),
]


def _redact(texto: str) -> str:
    for pat in _REDACT_PATTERNS:
        texto = pat.sub(r"\1***REDACTED***", texto)
    return texto


class _RedactApiKeys(logging.Filter):
    """Redige chaves de API em toda mensagem/traceback logada.

    Aplicado no logger raiz do app — não depende de o chamador lembrar
    de sanitizar. Cobre também `log.exception(...)` (traceback vem via
    `record.exc_info` → o Formatter renderiza depois; a redação da
    mensagem já pega o principal, e o `_format_stack_hook` abaixo
    intercepta o traceback final)."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            msg = record.getMessage()
            record.msg = _redact(msg)
            record.args = ()
        except Exception:  # noqa: BLE001
            pass
        return True


class _RedactingFormatter(logging.Formatter):
    """Formatter que também roda a redação no traceback formatado.
    O filter acima cuida da mensagem principal; este cuida do
    exc_info (que só é renderizado no format())."""

    def format(self, record: logging.LogRecord) -> str:
        out = super().format(record)
        return _redact(out)


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
    logger.addFilter(_RedactApiKeys())
    fmt = _RedactingFormatter(
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

    # RotatingFileHandler: máximo 5MB por arquivo, 3 backups. Total ~20MB.
    # Antes usávamos um arquivo por dia (yyyy-mm-dd.log) sem limpeza —
    # acumulava indefinidamente e um dia crescia sem limite. Rotation
    # resolve os dois problemas com um handler só. Nome fixo pra o
    # updater/backup encontrar sem regex.
    logfile = _log_dir() / "lancamento.log"
    fh = RotatingFileHandler(
        logfile,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


log = setup_logger()
