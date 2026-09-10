"""
Empacotamento portátil com Nuitka (RECOMENDADO).

Por que Nuitka em vez de PyInstaller:
- Compila Python para C e depois para binário nativo (não faz "unpack em runtime"),
  o que reduz drasticamente falsos-positivos de antivírus corporativos.
- Modo --standalone gera uma pasta autocontida com o .exe + DLLs — copia para
  pen-drive, roda direto em qualquer Windows sem admin, sem instalação, sem
  precisar de Python na máquina alvo.
- Sem UPX (compressão), sem descompactação em %TEMP% — perfis típicos de
  malware que fazem AV disparar.

Pré-requisitos (na SUA máquina de desenvolvimento, NÃO na do TOTVS):
    Python 3.11 ou 3.12 (Windows x64)
    pip install -r requirements.txt
    pip install nuitka zstandard ordered-set

    Compilador C (Nuitka baixa MSVC/MinGW automaticamente na 1a compilação,
    aceite quando ele perguntar).

Uso:
    python build/build.py

Saída:
    dist/LancamentoAutomatico.dist/         <- pasta portátil (copie inteira)
        LancamentoAutomatico.exe
        mapeamento.json                     <- editável pelo usuário final
        ... (DLLs e recursos)

Distribuição:
    Zipe a pasta 'LancamentoAutomatico.dist' e envie para a máquina alvo.
    Basta descompactar e clicar em LancamentoAutomatico.exe.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DIST = ROOT / "dist"
NOME = "LancamentoAutomatico"


def _icone() -> str | None:
    icon = ROOT / "build" / "app.ico"
    return str(icon) if icon.exists() else None


def run() -> int:
    if DIST.exists():
        shutil.rmtree(DIST, ignore_errors=True)
    DIST.mkdir(parents=True, exist_ok=True)

    import os
    jobs = str(max(2, (os.cpu_count() or 2)))
    args = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--assume-yes-for-downloads",
        "--enable-plugin=pyside6",
        # 'attach' = sem console em duplo clique, mas se rodar do CMD, saída
        # aparece no terminal. Isso ajuda no debug do usuário final sem
        # deixar janela preta piscando na abertura normal.
        "--windows-console-mode=attach",
        # Performance de build (não de runtime): desabilita LTO — LTO custa
        # 20+ min extras em máquinas com PySide6 e não muda anti-AV.
        "--lto=no",
        f"--jobs={jobs}",
        # Corta subpacotes pesados que não usamos, para reduzir tempo/tamanho.
        "--nofollow-import-to=tkinter",
        "--nofollow-import-to=unittest",
        "--nofollow-import-to=pydoc",
        "--nofollow-import-to=doctest",
        "--company-name=Multicom",
        "--product-name=Lancamento Automatico TOTVS",
        "--file-version=0.1.0.0",
        "--product-version=0.1.0.0",
        "--file-description=Automacao de lancamento de impostos TOTVS + Gemini",
        "--copyright=Multicom",
        f"--output-dir={DIST}",
        f"--output-filename={NOME}.exe",
        # Empacota o mapeamento.json dentro da pasta standalone.
        f"--include-data-files={SRC / 'config' / 'mapeamento.json'}=config/mapeamento.json",
        # Precisa incluir explicitamente o nosso pacote 'src' porque o
        # entrypoint (launcher.py) só faz um import dinâmico dele.
        "--include-package=src",
        # Módulos que podem ser resolvidos por importação dinâmica.
        "--include-package=google.generativeai",
        "--include-package=pywinauto",
        "--include-package=rapidfuzz",
        "--include-package=PIL",
        # Data files que essas libs carregam em runtime (cacert.pem, .proto,
        # roots.pem etc.). Sem isso o certifi crasha logo no import.
        "--include-package-data=certifi",
        "--include-package-data=google",
        "--include-package-data=grpc",
        "--include-package-data=pywinauto",
    ]

    icone = _icone()
    if icone:
        args.append(f"--windows-icon-from-ico={icone}")

    args.append(str(ROOT / "launcher.py"))

    print(">>", " ".join(args))
    r = subprocess.run(args, cwd=str(ROOT))
    if r.returncode != 0:
        return r.returncode

    # Nuitka nomeia a pasta pelo entrypoint (launcher.dist). Renomeia pro
    # nome comercial.
    origem_pasta = DIST / "launcher.dist"
    destino_pasta = DIST / f"{NOME}.dist"
    if origem_pasta.exists() and origem_pasta != destino_pasta:
        if destino_pasta.exists():
            shutil.rmtree(destino_pasta)
        origem_pasta.rename(destino_pasta)

    # Copia o mapeamento.json ao lado do .exe para permitir edição pelo usuário
    # sem mexer em subpastas.
    mapeamento_ext = destino_pasta / "mapeamento.json"
    mapeamento_int = destino_pasta / "config" / "mapeamento.json"
    if mapeamento_int.exists() and not mapeamento_ext.exists():
        shutil.copy2(mapeamento_int, mapeamento_ext)
        print(f"Copiado: {mapeamento_ext}")

    print()
    print("=" * 60)
    print(f"Pronto: {destino_pasta}")
    print("Zipe essa pasta inteira e leve para a maquina do TOTVS.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(run())
