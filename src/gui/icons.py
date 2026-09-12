"""Ícones vetoriais desenhados via QPainter — sem depender de font emoji
(que varia por sistema/DPI) nem de arquivos SVG externos."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _pixmap(size: int, cor: str, draw_fn) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    pen = QPen(QColor(cor))
    pen.setWidthF(size * 0.09)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    draw_fn(p, size)
    p.end()
    return pm


def icon_lote(cor: str, size: int = 20) -> QIcon:
    """Documento com dobra + linhas."""
    def draw(p, s):
        m = s * 0.20
        w = s - 2 * m
        h = w * 1.15
        y0 = (s - h) / 2
        # Retângulo
        path = QPainterPath()
        dobra = w * 0.28
        path.moveTo(m, y0)
        path.lineTo(m + w - dobra, y0)
        path.lineTo(m + w, y0 + dobra)
        path.lineTo(m + w, y0 + h)
        path.lineTo(m, y0 + h)
        path.closeSubpath()
        p.drawPath(path)
        # Dobra
        p.drawLine(int(m + w - dobra), int(y0),
                   int(m + w - dobra), int(y0 + dobra))
        p.drawLine(int(m + w - dobra), int(y0 + dobra),
                   int(m + w), int(y0 + dobra))
        # Linhas de texto
        for i in range(2):
            y = y0 + h * (0.55 + i * 0.18)
            p.drawLine(int(m + w * 0.18), int(y),
                       int(m + w * 0.7), int(y))
    return QIcon(_pixmap(size, cor, draw))


def icon_filiais(cor: str, size: int = 20) -> QIcon:
    """Prédio simples com janelas."""
    def draw(p, s):
        m = s * 0.20
        w = s - 2 * m
        h = w
        y0 = (s - h) / 2
        # Retângulo
        p.drawRect(int(m), int(y0), int(w), int(h))
        # Janelas: 2x2 grid
        cell = w / 4
        for row in range(2):
            for col in range(2):
                x = m + w * 0.25 + col * cell * 1.1
                y = y0 + h * 0.25 + row * cell * 1.1
                p.drawRect(int(x), int(y), int(cell * 0.5), int(cell * 0.5))
    return QIcon(_pixmap(size, cor, draw))


def icon_config(cor: str, size: int = 20) -> QIcon:
    """Engrenagem simplificada — 6 dentes."""
    def draw(p, s):
        import math
        cx = cy = s / 2
        raio_ext = s * 0.35
        raio_int = s * 0.16
        # Engrenagem = círculo + 6 pequenos retângulos ao redor
        p.drawEllipse(QRectF(cx - raio_int * 1.6, cy - raio_int * 1.6,
                             raio_int * 3.2, raio_int * 3.2))
        p.drawEllipse(QRectF(cx - raio_int * 0.6, cy - raio_int * 0.6,
                             raio_int * 1.2, raio_int * 1.2))
        for i in range(6):
            ang = i * math.pi / 3
            x1 = cx + math.cos(ang) * raio_int * 1.8
            y1 = cy + math.sin(ang) * raio_int * 1.8
            x2 = cx + math.cos(ang) * raio_ext
            y2 = cy + math.sin(ang) * raio_ext
            p.drawLine(int(x1), int(y1), int(x2), int(y2))
    return QIcon(_pixmap(size, cor, draw))


def icon_sobre(cor: str, size: int = 20) -> QIcon:
    """Círculo com 'i' dentro."""
    def draw(p, s):
        m = s * 0.20
        w = s - 2 * m
        p.drawEllipse(int(m), int(m), int(w), int(w))
        cx = s / 2
        # Ponto do i
        p.drawEllipse(int(cx - s * 0.03), int(m + w * 0.20),
                      int(s * 0.06), int(s * 0.06))
        # Traço do i
        p.drawLine(int(cx), int(m + w * 0.42),
                   int(cx), int(m + w * 0.75))
    return QIcon(_pixmap(size, cor, draw))


def icon_tema_dark(cor: str, size: int = 20) -> QIcon:
    """Lua crescente pra 'ir pro escuro'."""
    def draw(p, s):
        # Lua = círculo cheio com círculo menor subtraído
        r = s * 0.32
        cx = s / 2
        cy = s / 2
        p.setBrush(QColor(cor))
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
        p.setBrush(QColor("#0F141A"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(cx - r * 0.4, cy - r, r * 2, r * 2))
    return QIcon(_pixmap(size, cor, draw))


def icon_tema_light(cor: str, size: int = 20) -> QIcon:
    """Sol pra 'ir pro claro'."""
    def draw(p, s):
        import math
        cx = cy = s / 2
        r = s * 0.18
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
        for i in range(8):
            ang = i * math.pi / 4
            x1 = cx + math.cos(ang) * r * 1.6
            y1 = cy + math.sin(ang) * r * 1.6
            x2 = cx + math.cos(ang) * r * 2.3
            y2 = cy + math.sin(ang) * r * 2.3
            p.drawLine(int(x1), int(y1), int(x2), int(y2))
    return QIcon(_pixmap(size, cor, draw))
