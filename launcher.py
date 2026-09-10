"""
Entrypoint para empacotamento com Nuitka.

Fica na raiz do projeto (fora de src/) porque o Nuitka compila o entrypoint
como módulo top-level. Se src/main.py fosse o entrypoint, os imports
relativos ('from .core.logger') quebrariam porque main viraria top-level
sem contexto de pacote.

Além disso, o launcher:
- Blinda sys.stdin/stdout/stderr contra None (evita STATUS_FATAL_APP_EXIT).
- Silencia warnings e telemetria antes de qualquer import pesado.
- Envolve o boot em try/except; qualquer exceção vira MessageBox +
  'startup_error.log' ao lado do exe.
- Cada etapa do boot escreve num 'boot_trace.log' pra facilitar
  diagnóstico quando algo trava sem gerar exceção.
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path


# ---------- 1. Blindar stdio ANTES de qualquer coisa ----------
def _garantir_stdio() -> None:
    for nome in ("stdin", "stdout", "stderr"):
        atual = getattr(sys, nome, None)
        if atual is None or getattr(atual, "closed", False):
            try:
                modo = "r" if nome == "stdin" else "w"
                setattr(sys, nome, open(os.devnull, modo, encoding="utf-8", errors="ignore"))
            except Exception:  # noqa: BLE001
                pass


_garantir_stdio()


# ---------- 2. Silenciar warnings e telemetria ----------
# Muitas libs (google.*, grpc, urllib3, pydantic) emitem DeprecationWarning
# ou RuntimeWarning durante o import. Em modo GUI standalone uma linha
# desviada pra stderr pode virar STATUS_FATAL_APP_EXIT.
import warnings

warnings.filterwarnings("ignore")
os.environ.setdefault("PYTHONWARNINGS", "ignore")
os.environ.setdefault("GRPC_VERBOSITY", "NONE")
os.environ.setdefault("GRPC_TRACE", "")
os.environ.setdefault("GLOG_minloglevel", "3")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("ABSL_LOGGING_MIN_LOG_LEVEL", "3")


# ---------- 3. Utilitários de log de boot ----------
def _exe_dir() -> Path:
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        return Path(sys.argv[0]).resolve().parent
    return Path(__file__).resolve().parent


def _boot_trace(mensagem: str) -> None:
    """Marca cada etapa do boot num arquivo, mesmo se o Python travar depois."""
    try:
        with open(_exe_dir() / "boot_trace.log", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%H:%M:%S.%f}] {mensagem}\n")
    except Exception:  # noqa: BLE001
        pass


def _log_startup_error(err: BaseException) -> None:
    try:
        log_path = _exe_dir() / "startup_error.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
            f.write(f"exe: {sys.argv[0]}\n")
            f.write(f"cwd: {os.getcwd()}\n")
            f.write(f"python: {sys.version}\n")
            f.write(f"platform: {sys.platform}\n")
            f.write(f"sys.path (primeiros 10):\n")
            for p in sys.path[:10]:
                f.write(f"  - {p}\n")
            f.write("\n")
            traceback.print_exception(type(err), err, err.__traceback__, file=f)
            f.write("\n")
    except Exception:  # noqa: BLE001
        try:
            traceback.print_exc(file=sys.stderr)
        except Exception:
            pass


def _show_error_dialog(msg: str) -> None:
    try:
        import ctypes  # type: ignore[import-not-found]
        ctypes.windll.user32.MessageBoxW(
            None, msg, "Lançamento Automático — erro no início", 0x10
        )
    except Exception:  # noqa: BLE001
        pass


# ---------- 4. Boot com tracing ----------
def main() -> int:
    _boot_trace("launcher: início")
    try:
        _boot_trace("importando src.main")
        from src.main import main as run
        _boot_trace("src.main importado com sucesso")

        _boot_trace("executando src.main.main()")
        rc = run()
        _boot_trace(f"src.main.main() retornou {rc}")
        return rc
    except BaseException as e:  # noqa: BLE001
        _boot_trace(f"EXCEÇÃO: {type(e).__name__}: {e}")
        _log_startup_error(e)
        _show_error_dialog(
            "O aplicativo não conseguiu iniciar.\n\n"
            f"{type(e).__name__}: {e}\n\n"
            "Foram criados 'startup_error.log' e 'boot_trace.log' na "
            "mesma pasta do executável com mais detalhes."
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
