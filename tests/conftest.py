"""
Stubs de dependências que o CI Ubuntu não consegue instalar (Win32/GUI)
mas que alguns módulos importam no top-level. Sem isso, `import src.gui.*`
já explode com ModuleNotFoundError antes de a gente chegar num teste.

O truque é o mesmo do smoke gate em `.github/workflows/lint.yml`: cria
um objeto que responde a qualquer atributo/call devolvendo outro objeto
do mesmo tipo. Suficiente pra o import passar sem executar nada real.
"""

from __future__ import annotations

import sys


class _Stub:
    def __getattr__(self, name):
        return _Stub()

    def __call__(self, *args, **kwargs):
        return _Stub()


for mod in (
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "pyautogui",
    "pywinauto",
    "pywinauto.application",
    "pygetwindow",
    "mss",
    "cv2",
    "numpy",
    "PIL",
    "PIL.Image",
):
    sys.modules.setdefault(mod, _Stub())
