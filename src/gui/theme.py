"""Tema visual — duas paletas (dark/light) + build_qss()."""

from __future__ import annotations


PALETTE_DARK = {
    "bg_0":         "#0F1218",   # background da janela
    "bg_1":         "#161B23",   # sidebar, cards
    "bg_2":         "#1F2530",   # inputs, headers de tabela
    "bg_3":         "#2A3140",   # botões default, elementos elevados
    "border":       "#2E3646",
    "border_soft":  "#232A38",
    "text":         "#F1F5F9",
    "text_muted":   "#9AA5B8",
    "text_disabled":"#5B6577",
    "accent":       "#3B82F6",   # azul principal (ação)
    "accent_hover": "#60A5FA",
    "accent_pressed":"#2563EB",
    "success":      "#22C55E",
    "warning":      "#F59E0B",
    "danger":       "#EF4444",
    "sombra":       "0, 0, 0",   # base RGB pra rgba(sombra, alpha)
}

PALETTE_LIGHT = {
    "bg_0":         "#F5F7FB",
    "bg_1":         "#FFFFFF",
    "bg_2":         "#F1F4F9",
    "bg_3":         "#E4E9F2",
    "border":       "#D5DBE5",
    "border_soft":  "#E7EBF2",
    "text":         "#0F172A",
    "text_muted":   "#5A6478",
    "text_disabled":"#98A1B2",
    "accent":       "#2563EB",
    "accent_hover": "#1D4ED8",
    "accent_pressed":"#1E40AF",
    "success":      "#15803D",
    "warning":      "#B45309",
    "danger":       "#B91C1C",
    "sombra":       "15, 23, 42",
}


def build_qss(p: dict) -> str:
    """Gera o stylesheet completo a partir de uma paleta."""
    return f"""
* {{
    font-family: "Segoe UI Variable", "Segoe UI", "Inter", "SF Pro Text", sans-serif;
    font-size: 14px;
    color: {p["text"]};
}}

QMainWindow, QDialog {{
    background: {p["bg_0"]};
}}

/* ---------- Sidebar ---------- */
#Sidebar {{
    background: {p["bg_1"]};
    border-right: 1px solid {p["border_soft"]};
}}
#SidebarBrand {{
    color: {p["text"]};
    font-size: 18px;
    font-weight: 600;
    padding: 24px 20px 2px 20px;
}}
#SidebarSubtitle {{
    color: {p["text_muted"]};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.2px;
    padding: 0 20px 24px 20px;
}}
QPushButton[nav="true"] {{
    background: transparent;
    color: {p["text_muted"]};
    border: none;
    text-align: left;
    padding: 11px 20px;
    font-size: 13px;
    border-left: 3px solid transparent;
    min-height: 22px;
}}
QPushButton[nav="true"]:hover {{
    background: {p["bg_2"]};
    color: {p["text"]};
}}
QPushButton[nav="true"][active="true"] {{
    background: {p["bg_2"]};
    color: {p["text"]};
    border-left: 3px solid {p["accent"]};
    font-weight: 600;
}}
QPushButton[themetoggle="true"] {{
    background: transparent;
    color: {p["text_muted"]};
    border: 1px solid {p["border"]};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
    text-align: left;
    min-height: 18px;
}}
QPushButton[themetoggle="true"]:hover {{
    background: {p["bg_2"]};
    color: {p["text"]};
    border-color: {p["accent"]};
}}

/* ---------- Content ---------- */
#Content {{
    background: {p["bg_0"]};
}}
QLabel[h1="true"] {{
    font-size: 22px;
    font-weight: 700;
    color: {p["text"]};
}}
QLabel[h2="true"] {{
    font-size: 15px;
    font-weight: 600;
    color: {p["text"]};
}}
QLabel[muted="true"] {{
    color: {p["text_muted"]};
    font-size: 12px;
}}

/* ---------- Cards ---------- */
QFrame[card="true"] {{
    background: {p["bg_1"]};
    border: 1px solid {p["border_soft"]};
    border-radius: 10px;
}}
QFrame[cardFooter="true"] {{
    background: {p["bg_0"]};
    border-top: 1px solid {p["border_soft"]};
    border-bottom-left-radius: 9px;
    border-bottom-right-radius: 9px;
}}

/* ---------- KPI Cards ---------- */
QFrame[kpi="true"] {{
    background: {p["bg_1"]};
    border: 1px solid {p["border_soft"]};
    border-radius: 10px;
}}
QLabel[kpiValue="true"] {{
    font-size: 24px;
    font-weight: 700;
    color: {p["text"]};
}}

/* ---------- Toolbar ---------- */
QFrame[toolbar="true"] {{
    background: {p["bg_1"]};
    border: 1px solid {p["border_soft"]};
    border-radius: 10px;
}}
QLabel[inlineLabel="true"] {{
    color: {p["text_muted"]};
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.0px;
    padding-right: 2px;
}}
QFrame#Divisor {{
    background: {p["border"]};
    border: none;
}}
QFrame#DivisorH {{
    background: {p["border_soft"]};
    border: none;
}}

/* ---------- Inputs ---------- */
QLineEdit, QDateEdit, QComboBox, QPlainTextEdit, QTextEdit, QSpinBox {{
    background: {p["bg_2"]};
    border: 1px solid {p["border"]};
    border-radius: 6px;
    padding: 7px 10px;
    min-height: 18px;
    color: {p["text"]};
    selection-background-color: {p["accent"]};
    selection-color: white;
}}
QLineEdit:focus, QDateEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus {{
    border: 1px solid {p["accent"]};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
    color: {p["text_disabled"]};
    background: {p["bg_1"]};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
    subcontrol-position: center right;
    padding-right: 6px;
}}
QComboBox QAbstractItemView {{
    background: {p["bg_2"]};
    border: 1px solid {p["border"]};
    selection-background-color: {p["accent"]};
    selection-color: white;
    padding: 4px;
    outline: 0;
}}

/* ---------- Buttons ---------- */
QPushButton {{
    background: {p["bg_2"]};
    border: 1px solid {p["border"]};
    border-radius: 6px;
    padding: 8px 16px;
    color: {p["text"]};
    font-size: 13px;
    font-weight: 600;
    min-height: 20px;
}}
QPushButton:hover {{
    background: {p["bg_3"]};
    border-color: {p["border"]};
}}
QPushButton:pressed {{
    background: {p["bg_1"]};
}}
QPushButton:disabled {{
    color: {p["text_disabled"]};
    background: {p["bg_1"]};
    border-color: {p["border_soft"]};
}}
QPushButton[primary="true"] {{
    background: {p["accent"]};
    color: white;
    border: 1px solid {p["accent"]};
}}
QPushButton[primary="true"]:hover {{
    background: {p["accent_hover"]};
    border-color: {p["accent_hover"]};
}}
QPushButton[primary="true"]:pressed {{
    background: {p["accent_pressed"]};
}}
QPushButton[danger="true"] {{
    background: {p["danger"]};
    color: white;
    border: 1px solid {p["danger"]};
}}
QPushButton[danger="true"]:hover {{
    background: {p["danger"]};
    border-color: {p["danger"]};
}}

/* ---------- Table ---------- */
QTableView, QTableWidget {{
    background: {p["bg_1"]};
    alternate-background-color: {p["bg_2"]};
    gridline-color: {p["border_soft"]};
    border: 1px solid {p["border_soft"]};
    border-radius: 8px;
    selection-background-color: {p["accent"]};
    selection-color: white;
    font-size: 13px;
}}
QHeaderView::section {{
    background: {p["bg_2"]};
    color: {p["text_muted"]};
    padding: 10px 12px;
    border: none;
    border-bottom: 1px solid {p["border_soft"]};
    font-weight: 700;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QTableView::item, QTableWidget::item {{
    padding: 8px 10px;
    border-bottom: 1px solid {p["border_soft"]};
}}

/* ---------- Scroll ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 4px 0;
}}
QScrollBar::handle:vertical {{
    background: {p["border"]};
    border-radius: 6px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {p["accent"]};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 0 4px;
}}
QScrollBar::handle:horizontal {{
    background: {p["border"]};
    border-radius: 6px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {p["accent"]};
}}

/* ---------- Progress ---------- */
QProgressBar {{
    background: {p["bg_2"]};
    border: 1px solid {p["border_soft"]};
    border-radius: 6px;
    height: 10px;
    text-align: center;
    color: {p["text"]};
    font-size: 11px;
}}
QProgressBar::chunk {{
    background: {p["accent"]};
    border-radius: 5px;
}}

/* ---------- Status badges ---------- */
QLabel[badge="pendente"] {{
    background: {p["bg_3"]};
    color: {p["text_muted"]};
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel[badge="andamento"] {{
    background: rgba(59, 130, 246, 0.18);
    color: {p["accent_hover"]};
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel[badge="sucesso"] {{
    background: rgba(34, 197, 94, 0.18);
    color: {p["success"]};
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel[badge="falha"] {{
    background: rgba(239, 68, 68, 0.18);
    color: {p["danger"]};
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
}}

/* ---------- Log console ---------- */
QPlainTextEdit#LogConsole {{
    background: {p["bg_0"]};
    border: 1px solid {p["border_soft"]};
    border-radius: 8px;
    font-family: "Cascadia Mono", "Consolas", "Menlo", monospace;
    font-size: 12px;
    color: {p["text_muted"]};
    padding: 8px;
}}

/* ---------- CheckBox ---------- */
QCheckBox {{
    color: {p["text"]};
    spacing: 8px;
    font-size: 12px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {p["border"]};
    background: {p["bg_2"]};
}}
QCheckBox::indicator:checked {{
    background: {p["accent"]};
    border-color: {p["accent"]};
}}
QCheckBox::indicator:hover {{
    border-color: {p["accent"]};
}}

/* ---------- ToolTip ---------- */
QToolTip {{
    background: {p["bg_3"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ---------- Filial Row (DeParaDialog) ---------- */
QFrame[filialRow="true"] {{
    background: {p["bg_1"]};
    border: 1px solid {p["border_soft"]};
    border-radius: 8px;
    padding: 0;
}}
QFrame[filialRow="true"]:hover {{
    border-color: {p["border"]};
}}
"""


def qss(tema: str = "escuro") -> str:
    """Retorna o QSS de acordo com o tema ('escuro' ou 'claro')."""
    p = PALETTE_LIGHT if tema == "claro" else PALETTE_DARK
    return build_qss(p)


# Compat: código legado que importa `QSS` recebe o dark padrão.
QSS = qss("escuro")
COLORS = PALETTE_DARK
