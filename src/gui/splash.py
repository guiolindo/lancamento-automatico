"""Splash animado do Auto Conferi — fade-in do logo + wordmark + progresso."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import (
    Property, QEasingCurve, QPropertyAnimation, Qt, QTimer
)
from PySide6.QtGui import QFont, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget


def _buscar_logo() -> Path | None:
    aqui = Path(__file__).resolve()
    candidatos = [
        aqui.parent.parent / "assets" / "branding" / "logo_autoconferi_256.png",
        Path(sys.executable).resolve().parent / "src" / "assets" / "branding" / "logo_autoconferi_256.png",
    ]
    for c in candidatos:
        if c.exists():
            return c
    return None


class AutoConferiSplash(QWidget):
    """520x280, sem borda, fade-in do logo e wordmark, barra pulsante."""

    def __init__(self):
        super().__init__()
        self.setWindowFlag(Qt.SplashScreen)
        self.setWindowFlag(Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setFixedSize(520, 280)

        # Centralizar
        try:
            geo = QGuiApplication.primaryScreen().availableGeometry()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2,
            )
        except Exception:
            pass

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 40, 0, 24)
        v.setSpacing(0)
        v.setAlignment(Qt.AlignHCenter)

        # Logo
        self._logo = QLabel(alignment=Qt.AlignCenter)
        logo_path = _buscar_logo()
        if logo_path:
            pm = QPixmap(str(logo_path))
            self._logo.setPixmap(
                pm.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        self._logo_op = 0.0
        v.addWidget(self._logo)
        v.addSpacing(18)

        # Wordmark
        self._brand = QLabel("Auto Conferi", alignment=Qt.AlignCenter)
        self._brand.setStyleSheet(
            "color: #F5F7FA; font-family: 'Segoe UI'; font-size: 22px; "
            "font-weight: 700; letter-spacing: 0.5px;"
        )
        v.addWidget(self._brand)

        self._tag = QLabel("lançamentos assistidos", alignment=Qt.AlignCenter)
        self._tag.setStyleSheet(
            "color: #B7C2CF; font-family: 'Segoe UI'; font-size: 11px;"
        )
        v.addWidget(self._tag)

        v.addStretch(1)

        # Barra fina
        self._bar = QProgressBar()
        self._bar.setRange(0, 0)  # modo indeterminado
        self._bar.setFixedSize(260, 3)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(
            "QProgressBar { border: none; background: #202A35; border-radius: 2px; }"
            "QProgressBar::chunk { background: #15803D; border-radius: 2px; }"
        )
        v.addWidget(self._bar, alignment=Qt.AlignCenter)
        v.addSpacing(6)

        self._etapa = QLabel("Preparando…", alignment=Qt.AlignCenter)
        self._etapa.setStyleSheet(
            "color: #B7C2CF; font-family: 'Segoe UI'; font-size: 10px;"
        )
        v.addWidget(self._etapa)

        # Fundo estilo Nexora/Auto Conferi
        self.setStyleSheet(
            "AutoConferiSplash { background: #0F141A; border: 1px solid #344252; }"
        )
        # Precisa setar o object name pra o style acima aplicar em QWidget derivado
        self.setObjectName("AutoConferiSplash")

        # Wordmark começa invisível pra fade-in escalonado
        self._brand.setStyleSheet(self._brand.styleSheet() + " color: transparent;")

        self._logo_anim = None
        self._brand_anim = None
        self._tag_anim = None

    def start_animation(self) -> None:
        """Chama depois de show(). Fade sequencial logo → wordmark → tag."""
        # Sem QGraphicsOpacityEffect que às vezes pinta borrado em alguns
        # sistemas — usamos QTimer + alteração de stylesheet.
        self._logo.setStyleSheet("")  # instant
        QTimer.singleShot(80, lambda: self._brand.setStyleSheet(
            "color: #F5F7FA; font-family: 'Segoe UI'; font-size: 22px; "
            "font-weight: 700; letter-spacing: 0.5px;"
        ))
        QTimer.singleShot(180, lambda: self._tag.setStyleSheet(
            "color: #B7C2CF; font-family: 'Segoe UI'; font-size: 11px;"
        ))

    def set_etapa(self, texto: str) -> None:
        self._etapa.setText(texto)
