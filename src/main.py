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
    1. Ao lado do executável (para permitir edição sem recompilar após empacotar).
    2. Empacotado com o app (fallback inicial).
    """
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        externo = exe_dir / "mapeamento.json"
        if externo.exists():
            return externo
        return Path(sys._MEIPASS) / "config" / "mapeamento.json"  # type: ignore[attr-defined]
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
