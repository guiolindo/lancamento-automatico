"""
Entrypoint para empacotamento com Nuitka.

Fica na raiz do projeto (fora de src/) porque o Nuitka compila o entrypoint
como módulo top-level. Se src/main.py fosse o entrypoint, os imports
relativos ('from .core.logger') quebrariam porque main viraria top-level
sem contexto de pacote.

Como launcher.py está fora de src/, ele pode importar 'src.main' como
pacote absoluto, e todos os imports relativos internos do pacote passam a
funcionar normalmente.
"""

from __future__ import annotations

import sys


def main() -> int:
    from src.main import main as run
    return run()


if __name__ == "__main__":
    sys.exit(main())
