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


BUILD_MARKER = "build-69 (docs completas: README + ARCHITECTURE + DECISIONS)"


def main() -> int:
    _boot_trace("src.main.main() entrada")
    _boot_trace(f"BUILD: {BUILD_MARKER}")

    # -------- IMPORTS MÍNIMOS PRIMEIRO: só o essencial pra ter QApplication + Splash na tela.
    # Qt é o que mais demora pra importar (~2-4s em Nuitka bundle). Fazendo
    # isso aqui e mostrando o splash ANTES dos outros imports, o usuário
    # vê algo na tela em ~2s em vez dos ~10s antigos.
    _boot_trace("importando PySide6 (mínimo)")
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    _boot_trace("criando QApplication")
    app = QApplication(sys.argv)
    app.setApplicationName("Auto Conferi")
    app.setOrganizationName("Auto Conferi")

    # Ícone do app (barra de título, taskbar)
    try:
        for cand in (
            Path(__file__).resolve().parent / "assets" / "branding" / "logo_autoconferi_256.png",
            Path(sys.executable).resolve().parent / "src" / "assets" / "branding" / "logo_autoconferi_256.png",
        ):
            if cand.exists():
                app.setWindowIcon(QIcon(str(cand)))
                break
    except Exception:  # noqa: BLE001
        pass

    # SPLASH IMEDIATO — antes dos imports pesados. Assim o usuário vê
    # 'Auto Conferi' na tela em ~2s de boot em vez de esperar 8-10s
    # de tela preta.
    _boot_trace("criando splash imediato")
    from .gui.splash import AutoConferiSplash
    splash = AutoConferiSplash()
    splash.show()
    splash.start_animation()
    app.processEvents()

    # -------- IMPORTS PESADOS: agora que o splash está visível, o resto
    # dos módulos pode importar sem o usuário achar que travou.
    splash.set_etapa("Carregando módulos…")
    app.processEvents()

    _boot_trace("importando core.logger")
    from .core.logger import log
    log.info("=" * 60)
    log.info("APP INICIADO — %s", BUILD_MARKER)
    log.info("=" * 60)

    _boot_trace("importando core.mapping/settings")
    from .core.mapping import MappingRepository
    from .core.settings_store import SettingsStore

    splash.set_etapa("Lendo configurações…")
    app.processEvents()

    try:
        _boot_trace("carregando SettingsStore")
        settings = SettingsStore()
        _boot_trace("carregando mapeamento.json")
        mp = _mapping_path()
        mapping = MappingRepository(mp)
    except Exception as e:  # noqa: BLE001
        _boot_trace(f"falha na inicialização: {type(e).__name__}: {e}")
        log.exception("Falha na inicialização")
        splash.close()
        QMessageBox.critical(None, "Erro na inicialização", str(e))
        return 1

    splash.set_etapa("Preparando interface…")
    app.processEvents()

    _boot_trace("importando gui.main_window")
    from .gui.main_window import MainWindow

    _boot_trace("criando MainWindow")
    win = MainWindow(settings, mapping, mp)
    app.aboutToQuit.connect(win._encerrar_threads)

    _boot_trace("MainWindow.show()")
    splash.set_etapa("Pronto")
    app.processEvents()
    win.show()
    # Fecha splash com pequeno delay pra dar sensação de transição
    QTimer.singleShot(200, splash.close)
    _boot_trace("app.exec()")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
