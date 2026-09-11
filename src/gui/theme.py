"""Tema visual — identidade Economart, duas paletas (dark/light).

Cores da marca extraídas do wordmark:
    Laranja Economart: #FF6900
    Azul Economart:    #004D96

Uso:
    - Azul primário = ações principais (Extrair, Executar)
    - Laranja = destaques de valor/número, hover states secundários,
      indicador de nav ativo, cor viva pros KPIs
"""

from __future__ import annotations


# ---- Cores da marca (fixas em ambos os temas) ----
BRAND_ORANGE       = "#FF6900"
BRAND_ORANGE_HOVER = "#FF7A1A"
BRAND_ORANGE_SOFT  = "rgba(255, 105, 0, 0.14)"
BRAND_BLUE         = "#004D96"
BRAND_BLUE_HOVER   = "#0060B8"
BRAND_BLUE_PRESSED = "#003D7A"


PALETTE_DARK = {
    "bg_0":         "#0B0F17",   # background da janela (bem escuro)
    "bg_1":         "#141926",   # cards, sidebar
    "bg_2":         "#1E2536",   # inputs, headers de tabela
    "bg_3":         "#2A3346",   # hover, elementos elevados
    "border":       "#2F3852",
    "border_soft":  "#222A3D",
    "text":         "#F0F4FA",
    "text_muted":   "#8996AE",
    "text_disabled":"#4F5A72",
    # Ações principais = azul Economart adaptado (mais claro pro dark contrastar)
    "accent":       "#3B82F6",
    "accent_hover": "#5B96F8",
    "accent_pressed":"#2563EB",
    "brand_orange": BRAND_ORANGE,
    "brand_orange_hover": BRAND_ORANGE_HOVER,
    "brand_orange_soft":  BRAND_ORANGE_SOFT,
    "brand_blue":         BRAND_BLUE,
    "success":      "#22C55E",
    "warning":      "#F59E0B",
    "danger":       "#EF4444",
}

PALETTE_LIGHT = {
    "bg_0":         "#F5F7FB",
    "bg_1":         "#FFFFFF",
    "bg_2":         "#F1F4F9",
    "bg_3":         "#E7EBF2",
    "border":       "#D5DBE5",
    "border_soft":  "#EAEEF4",
    "text":         "#0F172A",
    "text_muted":   "#5A6478",
    "text_disabled":"#9AA3B4",
    # No tema claro o azul primário é o azul Economart puro
    "accent":       BRAND_BLUE,
    "accent_hover": BRAND_BLUE_HOVER,
    "accent_pressed":BRAND_BLUE_PRESSED,
    "brand_orange": BRAND_ORANGE,
    "brand_orange_hover": BRAND_ORANGE_HOVER,
    "brand_orange_soft":  BRAND_ORANGE_SOFT,
    "brand_blue":         BRAND_BLUE,
    "success":      "#15803D",
    "warning":      "#B45309",
    "danger":       "#B91C1C",
}


def build_qss(p: dict) -> str:
    return f"""
* {{
    font-family: "Segoe UI Variable", "Segoe UI", "Inter", "SF Pro Text", sans-serif;
    font-size: 14px;
    color: {p["text"]};
}}

QMainWindow, QDialog {{
    background: {p["bg_0"]};
}}

/* ---------- Sidebar fina só com ícones ---------- */
#Sidebar {{
    background: {p["bg_1"]};
    border-right: 1px solid {p["border_soft"]};
}}
#SidebarLogo {{
    padding: 16px 12px 12px 12px;
    qproperty-alignment: 'AlignCenter';
}}
QPushButton[navIcon="true"] {{
    background: transparent;
    color: {p["text_muted"]};
    border: none;
    padding: 12px 0;
    font-size: 20px;
    min-width: 40px;
    min-height: 40px;
    border-left: 3px solid transparent;
    border-radius: 0;
}}
QPushButton[navIcon="true"]:hover {{
    background: {p["bg_2"]};
    color: {p["text"]};
}}
QPushButton[navIcon="true"][active="true"] {{
    background: {p["bg_2"]};
    color: {p["brand_orange"]};
    border-left: 3px solid {p["brand_orange"]};
}}
QPushButton[iconOnly="true"] {{
    background: transparent;
    border: 1px solid transparent;
    color: {p["text_muted"]};
    padding: 6px 8px;
    font-size: 14px;
    min-height: 20px;
    min-width: 20px;
    border-radius: 6px;
}}
QPushButton[iconOnly="true"]:hover {{
    background: {p["bg_2"]};
    color: {p["text"]};
    border-color: {p["border"]};
}}

/* ---------- Topbar ---------- */
#Topbar {{
    background: {p["bg_0"]};
    border-bottom: 1px solid {p["border_soft"]};
}}
QLabel[breadcrumb="true"] {{
    color: {p["text_muted"]};
    font-size: 12px;
}}
QLabel[breadcrumbActive="true"] {{
    color: {p["text"]};
    font-size: 12px;
    font-weight: 600;
}}

/* ---------- Content ---------- */
#Content {{
    background: {p["bg_0"]};
}}
QLabel[h1="true"] {{
    font-size: 26px;
    font-weight: 700;
    color: {p["text"]};
    letter-spacing: -0.4px;
}}
QLabel[h2="true"] {{
    font-size: 14px;
    font-weight: 700;
    color: {p["text_muted"]};
    text-transform: uppercase;
    letter-spacing: 1px;
}}
QLabel[h3="true"] {{
    font-size: 16px;
    font-weight: 600;
    color: {p["text"]};
}}
QLabel[muted="true"] {{
    color: {p["text_muted"]};
    font-size: 12px;
}}
QLabel[subtle="true"] {{
    color: {p["text_muted"]};
    font-size: 13px;
}}

/* ---------- Cards ---------- */
QFrame[card="true"] {{
    background: {p["bg_1"]};
    border: 1px solid {p["border_soft"]};
    border-radius: 12px;
}}
QFrame[cardFooter="true"] {{
    background: {p["bg_0"]};
    border-top: 1px solid {p["border_soft"]};
    border-bottom-left-radius: 11px;
    border-bottom-right-radius: 11px;
}}

/* ---------- KPI Cards (com destaque laranja Economart) ---------- */
QFrame[kpi="true"] {{
    background: {p["bg_1"]};
    border: 1px solid {p["border_soft"]};
    border-radius: 12px;
}}
QFrame[kpi="true"][highlight="true"] {{
    border: 1px solid {p["brand_orange"]};
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                 stop:0 {p["bg_1"]}, stop:1 {p["bg_1"]});
}}
QLabel[kpiLabel="true"] {{
    color: {p["text_muted"]};
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
}}
QLabel[kpiValue="true"] {{
    font-size: 28px;
    font-weight: 800;
    color: {p["text"]};
    letter-spacing: -0.5px;
}}
QLabel[kpiValueOrange="true"] {{
    font-size: 28px;
    font-weight: 800;
    color: {p["brand_orange"]};
    letter-spacing: -0.5px;
}}
QLabel[kpiHint="true"] {{
    color: {p["text_muted"]};
    font-size: 11px;
}}

/* ---------- Section header (dentro de cards) ---------- */
QLabel[sectionKicker="true"] {{
    color: {p["brand_orange"]};
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
}}

/* ---------- Step (numerado dentro do card principal) ---------- */
QLabel[stepNum="true"] {{
    background: {p["brand_orange_soft"]};
    color: {p["brand_orange"]};
    border-radius: 12px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
    min-width: 16px;
    max-width: 24px;
    qproperty-alignment: 'AlignCenter';
}}

QLabel[inlineLabel="true"] {{
    color: {p["text_muted"]};
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.2px;
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
    border-radius: 8px;
    padding: 9px 12px;
    min-height: 20px;
    color: {p["text"]};
    selection-background-color: {p["accent"]};
    selection-color: white;
}}
QLineEdit:focus, QDateEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus {{
    border: 1px solid {p["brand_orange"]};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
    color: {p["text_disabled"]};
    background: {p["bg_1"]};
}}
QComboBox::drop-down {{
    border: none;
    width: 26px;
    subcontrol-position: center right;
    padding-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: {p["bg_2"]};
    border: 1px solid {p["border"]};
    selection-background-color: {p["accent"]};
    selection-color: white;
    padding: 4px;
    outline: 0;
    border-radius: 8px;
}}

/* ---------- Buttons ---------- */
QPushButton {{
    background: {p["bg_2"]};
    border: 1px solid {p["border"]};
    border-radius: 8px;
    padding: 9px 18px;
    color: {p["text"]};
    font-size: 13px;
    font-weight: 600;
    min-height: 22px;
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
QPushButton[brand="true"] {{
    background: {p["brand_orange"]};
    color: white;
    border: 1px solid {p["brand_orange"]};
    padding: 11px 22px;
    font-weight: 700;
}}
QPushButton[brand="true"]:hover {{
    background: {p["brand_orange_hover"]};
    border-color: {p["brand_orange_hover"]};
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
QPushButton[ghost="true"] {{
    background: transparent;
    border: 1px solid {p["border"]};
    color: {p["text"]};
}}
QPushButton[ghost="true"]:hover {{
    background: {p["bg_2"]};
    border-color: {p["brand_orange"]};
    color: {p["brand_orange"]};
}}

/* ---------- Table ---------- */
QTableView, QTableWidget {{
    background: {p["bg_1"]};
    alternate-background-color: {p["bg_2"]};
    gridline-color: {p["border_soft"]};
    border: 1px solid {p["border_soft"]};
    border-radius: 10px;
    selection-background-color: {p["accent"]};
    selection-color: white;
    font-size: 13px;
}}
QHeaderView::section {{
    background: {p["bg_2"]};
    color: {p["text_muted"]};
    padding: 12px 12px;
    border: none;
    border-bottom: 1px solid {p["border_soft"]};
    font-weight: 700;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1.2px;
}}
QTableView::item, QTableWidget::item {{
    padding: 9px 12px;
    border-bottom: 1px solid {p["border_soft"]};
}}

/* ---------- Scroll ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 6px 0;
}}
QScrollBar::handle:vertical {{
    background: {p["border"]};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {p["brand_orange"]};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0 6px;
}}
QScrollBar::handle:horizontal {{
    background: {p["border"]};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {p["brand_orange"]};
}}

/* ---------- Progress ---------- */
QProgressBar {{
    background: {p["bg_2"]};
    border: 1px solid {p["border_soft"]};
    border-radius: 8px;
    height: 10px;
    text-align: center;
    color: {p["text"]};
    font-size: 11px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                 stop:0 {p["brand_orange"]}, stop:1 {p["accent"]});
    border-radius: 7px;
}}

/* ---------- Status badges (pill) ---------- */
QLabel[badge="pendente"] {{
    background: {p["bg_3"]};
    color: {p["text_muted"]};
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel[badge="andamento"] {{
    background: {p["brand_orange_soft"]};
    color: {p["brand_orange"]};
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel[badge="sucesso"] {{
    background: rgba(34, 197, 94, 0.16);
    color: {p["success"]};
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 700;
}}
QLabel[badge="falha"] {{
    background: rgba(239, 68, 68, 0.16);
    color: {p["danger"]};
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 700;
}}

/* ---------- Log console ---------- */
QPlainTextEdit#LogConsole {{
    background: {p["bg_0"]};
    border: 1px solid {p["border_soft"]};
    border-radius: 10px;
    font-family: "Cascadia Mono", "Consolas", "Menlo", monospace;
    font-size: 12px;
    color: {p["text_muted"]};
    padding: 10px;
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
    background: {p["brand_orange"]};
    border-color: {p["brand_orange"]};
}}
QCheckBox::indicator:hover {{
    border-color: {p["brand_orange"]};
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
    border-radius: 10px;
}}
QFrame[filialRow="true"]:hover {{
    border-color: {p["brand_orange"]};
}}
"""


def qss(tema: str = "escuro") -> str:
    p = PALETTE_LIGHT if tema == "claro" else PALETTE_DARK
    return build_qss(p)


QSS = qss("escuro")
COLORS = PALETTE_DARK
