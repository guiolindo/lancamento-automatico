from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from .core.logger import log
from .core.mapping import MappingRepository
from .core.settings_store import SettingsStore
from .gui.main_window import MainWindow


def _mapping_path() -> Path:
    """
    Localiza o arquivo mapeamento.json. Prioridade:
    1. Ao lado do executável (permite editar sem recompilar quando empacotado).
    2. Subpasta 'config' ao lado do executável (Nuitka standalone).
    3. Junto ao código fonte (dev).
    """
    exe_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else None
    if exe_dir is None:
        # Nuitka: __compiled__ é injetado; se não for compilado, é dev.
        if "__compiled__" in globals() or hasattr(sys, "_MEIPASS"):
            exe_dir = Path(sys.argv[0]).resolve().parent

    if exe_dir is not None:
        for candidato in (exe_dir / "mapeamento.json", exe_dir / "config" / "mapeamento.json"):
            if candidato.exists():
                return candidato

    return Path(__file__).parent / "config" / "mapeamento.json"


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Lançamento Automático TOTVS")
    app.setOrganizationName("Multicom")

    try:
        settings = SettingsStore()
        mp = _mapping_path()
        mapping = MappingRepository(mp)
    except Exception as e:  # noqa: BLE001
        log.exception("Falha na inicialização")
        QMessageBox.critical(None, "Erro na inicialização", str(e))
        return 1

    win = MainWindow(settings, mapping, mp)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
