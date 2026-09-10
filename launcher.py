"""
Entrypoint para empacotamento com Nuitka.

Fica na raiz do projeto (fora de src/) porque o Nuitka compila o entrypoint
como módulo top-level. Se src/main.py fosse o entrypoint, os imports
relativos ('from .core.logger') quebrariam porque main viraria top-level
sem contexto de pacote.

Além disso, o launcher captura QUALQUER exceção que aconteça durante o
boot e escreve em 'startup_error.log' ao lado do .exe. Se o app não
abrir, o usuário sempre tem um log para me mandar.
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path


def _log_startup_error(err: BaseException) -> None:
    """Grava qualquer erro de boot num log ao lado do executável."""
    try:
        if getattr(sys, "frozen", False) or "__compiled__" in globals():
            base = Path(sys.argv[0]).resolve().parent
        else:
            base = Path(__file__).resolve().parent
        log_path = base / "startup_error.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
            f.write(f"exe: {sys.argv[0]}\n")
            f.write(f"cwd: {os.getcwd()}\n")
            f.write(f"python: {sys.version}\n")
            f.write(f"platform: {sys.platform}\n\n")
            traceback.print_exception(type(err), err, err.__traceback__, file=f)
            f.write("\n")
    except Exception:
        # Em último caso, tenta stderr; se estiver disponível.
        try:
            traceback.print_exc(file=sys.stderr)
        except Exception:
            pass


def _show_error_dialog(msg: str) -> None:
    """Última tentativa: mostrar um MessageBox nativo do Windows sem depender de Qt."""
    try:
        import ctypes  # type: ignore[import-not-found]
        ctypes.windll.user32.MessageBoxW(
            None, msg, "Lançamento Automático — erro no início", 0x10
        )
    except Exception:
        pass


def main() -> int:
    try:
        from src.main import main as run
        return run()
    except BaseException as e:  # noqa: BLE001
        _log_startup_error(e)
        _show_error_dialog(
            "O aplicativo não conseguiu iniciar.\n\n"
            f"{type(e).__name__}: {e}\n\n"
            "Um arquivo 'startup_error.log' foi criado na mesma pasta do "
            "executável com mais detalhes."
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
