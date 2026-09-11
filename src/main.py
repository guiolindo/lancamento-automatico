from __future__ import annotations

import sys
from pathlib import Path


def _mapping_path() -> Path:
    """
    Localiza o arquivo mapeamento.json. Prioridade:
    1. Ao lado do executável.
    2. Subpasta 'config' ao lado do executável (Nuitka standalone).
    3. Junto ao código fonte (dev).
    """
    exe_dir = None
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
    elif "__compiled__" in globals() or hasattr(sys, "_MEIPASS"):
        exe_dir = Path(sys.argv[0]).resolve().parent

    if exe_dir is not None:
        for candidato in (exe_dir / "mapeamento.json", exe_dir / "config" / "mapeamento.json"):
            if candidato.exists():
                return candidato

    return Path(__file__).parent / "config" / "mapeamento.json"


def _boot_trace(mensagem: str) -> None:
    """Reusa o trace do launcher — se estiver rodando compilado."""
    try:
        from datetime import datetime
        exe_dir = Path(sys.argv[0]).resolve().parent if (
            getattr(sys, "frozen", False) or "__compiled__" in globals()
        ) else Path(__file__).resolve().parent.parent
        with open(exe_dir / "boot_trace.log", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%H:%M:%S.%f}] {mensagem}\n")
    except Exception:  # noqa: BLE001
        pass


BUILD_MARKER = "build-51 (workflow permissions: contents write pra release)"


def main() -> int:
    _boot_trace("src.main.main() entrada")
    _boot_trace(f"BUILD: {BUILD_MARKER}")

    _boot_trace("importando PySide6")
    from PySide6.QtWidgets import QApplication, QMessageBox

    _boot_trace("importando core.logger")
    from .core.logger import log
    # loga o build também no arquivo principal (não só no boot_trace)
    log.info("=" * 60)
    log.info("APP INICIADO — %s", BUILD_MARKER)
    log.info("=" * 60)

    _boot_trace("importando core.mapping")
    from .core.mapping import MappingRepository

    _boot_trace("importando core.settings_store")
    from .core.settings_store import SettingsStore

    _boot_trace("importando gui.main_window")
    from .gui.main_window import MainWindow

    _boot_trace("criando QApplication")
    app = QApplication(sys.argv)
    app.setApplicationName("Lançamento Automático TOTVS")
    app.setOrganizationName("Multicom")
    # Ícone: barra de título, taskbar, alt-tab
    try:
        from PySide6.QtGui import QIcon
        for cand in (
            Path(__file__).resolve().parent / "assets" / "branding" / "logo_simbolo.png",
            Path(sys.executable).resolve().parent / "src" / "assets" / "branding" / "logo_simbolo.png",
            Path(sys.executable).resolve().parent / "assets" / "branding" / "logo_simbolo.png",
        ):
            if cand.exists():
                app.setWindowIcon(QIcon(str(cand)))
                break
    except Exception:  # noqa: BLE001
        pass

    try:
        _boot_trace("carregando SettingsStore")
        settings = SettingsStore()

        _boot_trace("carregando mapeamento.json")
        mp = _mapping_path()
        mapping = MappingRepository(mp)
    except Exception as e:  # noqa: BLE001
        _boot_trace(f"falha na inicialização: {type(e).__name__}: {e}")
        log.exception("Falha na inicialização")
        QMessageBox.critical(None, "Erro na inicialização", str(e))
        return 1

    _boot_trace("criando MainWindow")
    win = MainWindow(settings, mapping, mp)
    _boot_trace("MainWindow.show()")
    win.show()
    _boot_trace("app.exec()")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
