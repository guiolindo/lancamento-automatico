"""
Script de empacotamento com PyInstaller.

Uso (no Windows, com venv ativado):
    pip install pyinstaller
    python build/build.py

Gera dist/LancamentoAutomatico.exe (one-file, sem console).
O mapeamento.json é copiado para a pasta dist ao lado do .exe para permitir
edição pelo usuário final sem recompilar.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DIST = ROOT / "dist"
BUILD = ROOT / "build" / "_pyi"


def run() -> int:
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onefile",
        "--name", "LancamentoAutomatico",
        "--paths", str(SRC),
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        "--specpath", str(BUILD),
        "--add-data", f"{SRC / 'config' / 'mapeamento.json'}{';' if sys.platform == 'win32' else ':'}config",
        str(SRC / "main.py"),
    ]
    print(">>", " ".join(args))
    r = subprocess.run(args)
    if r.returncode != 0:
        return r.returncode

    # Copia o mapeamento.json ao lado do .exe para permitir edição pelo usuário.
    origem = SRC / "config" / "mapeamento.json"
    destino = DIST / "mapeamento.json"
    if origem.exists():
        shutil.copy2(origem, destino)
        print(f"Copiado: {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
