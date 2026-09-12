"""
Barra de progresso de atualização — aparece no topo da MainWindow enquanto
o updater baixa e prepara a nova versão.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton
)

from ..core import updater
from ..core.logger import log


class _UpdaterSignals(QObject):
    progresso = Signal(int, int, str)   # baixados, total, msg
    concluido = Signal(str)             # msg final
    erro = Signal(str)


class UpdaterBar(QFrame):
    """QFrame fino que aparece no topo enquanto atualização baixa.
    Escondido por padrão. Chama .iniciar(info) pra começar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("UpdaterBar")
        self.setFixedHeight(42)
        self.setVisible(False)
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._signals = _UpdaterSignals()
        self._signals.progresso.connect(self._on_progresso)
        self._signals.concluido.connect(self._on_concluido)
        self._signals.erro.connect(self._on_erro)

        h = QHBoxLayout(self)
        h.setContentsMargins(20, 6, 12, 6)
        h.setSpacing(12)

        self.lbl = QLabel("Atualizando…")
        self.lbl.setStyleSheet("color: white; font-size: 12px; font-weight: 600;")
        h.addWidget(self.lbl)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setFixedHeight(8)
        self.bar.setTextVisible(False)
        h.addWidget(self.bar, 1)

        self.lbl_bytes = QLabel("0 / 0 MB")
        self.lbl_bytes.setStyleSheet("color: rgba(255,255,255,0.8); font-size: 11px;")
        h.addWidget(self.lbl_bytes)

        # Botão × removido — durante o download não fazia sentido
        # cancelar (atualização é obrigatória, download é rápido). No
        # estado 'concluído' e 'erro' o widget é escondido automaticamente
        # depois de alguns segundos.
        self.btn_cancel = None

        # Cor de fundo laranja Economart (a barra é vistosa por design)
        self.setStyleSheet(
            "#UpdaterBar { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #FF6900, stop:1 #FF7A1A); border: none; }"
            "QProgressBar { background: rgba(255,255,255,0.25); border-radius: 4px; }"
            "QProgressBar::chunk { background: white; border-radius: 4px; }"
        )

    def iniciar(self, info: "updater.InfoAtualizacao") -> None:
        """Dispara o download em thread. Chame do main thread."""
        if self._thread and self._thread.is_alive():
            return
        self._info = info
        self._cancel_event.clear()
        self.bar.setValue(0)
        self.lbl.setText("Iniciando…")
        self.lbl_bytes.setText("")
        self.setVisible(True)

        def worker():
            try:
                updater.baixar_e_preparar(
                    info,
                    on_progress=lambda b, t, m: self._signals.progresso.emit(b, t, m),
                    cancel_event=self._cancel_event,
                )
                self._signals.concluido.emit(
                    "Atualização baixada — vai aplicar na próxima vez que abrir o app"
                )
            except updater.UpdateCancelled:
                self._signals.erro.emit("Cancelado")
            except updater.UpdateError as e:
                self._signals.erro.emit(str(e))
            except Exception as e:  # noqa: BLE001
                log.exception("Falha inesperada no updater")
                self._signals.erro.emit(f"{type(e).__name__}: {e}")

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def _cancelar(self) -> None:
        self._cancel_event.set()
        self.lbl.setText("Cancelando…")

    def _fmt_mb(self, b: int) -> str:
        return f"{b / (1024 * 1024):.1f} MB"

    def _on_progresso(self, baixados: int, total: int, msg: str) -> None:
        self.lbl.setText(msg)
        if total > 0:
            pct = int(baixados * 100 / total)
            self.bar.setValue(min(100, max(0, pct)))
            self.lbl_bytes.setText(f"{self._fmt_mb(baixados)} / {self._fmt_mb(total)}")
        else:
            self.lbl_bytes.setText(self._fmt_mb(baixados))

    def _on_concluido(self, msg: str) -> None:
        self.lbl.setText("✓  " + msg)
        self.bar.setValue(100)
        # Muda cor pra verde de sucesso
        self.setStyleSheet(
            "#UpdaterBar { background: #16A34A; border: none; }"
            "QProgressBar { background: rgba(255,255,255,0.25); border-radius: 4px; }"
            "QProgressBar::chunk { background: white; border-radius: 4px; }"
        )
        # Some sozinho após 6s
        from PySide6.QtCore import QTimer as _QT
        _QT.singleShot(6000, lambda: self.setVisible(False))

    def _on_erro(self, msg: str) -> None:
        self.lbl.setText("✕  " + (msg[:80] + "…" if len(msg) > 80 else msg))
        self.setStyleSheet(
            "#UpdaterBar { background: #DC2626; border: none; }"
            "QProgressBar { background: rgba(255,255,255,0.25); border-radius: 4px; }"
            "QProgressBar::chunk { background: white; border-radius: 4px; }"
        )
        self.bar.setValue(0)
        # Some sozinho após 8s (mais tempo pra usuário ler o erro)
        from PySide6.QtCore import QTimer as _QT
        _QT.singleShot(8000, lambda: self.setVisible(False))
