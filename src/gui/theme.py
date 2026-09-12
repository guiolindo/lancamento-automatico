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


# ---- Cores da marca Auto Conferi (build-73) ----
# Duas identidades intencionalmente diferentes por tema:
#   DARK  → verde-fisco (Receita Federal, contador, planilha noturna) +
#           âmbar-carimbo como brand secundária (selo/documento oficial).
#   LIGHT → azul-marinho tradicional (planilha SAP, TOTVS legado) +
#           bordô-registro como brand secundária.
# Zero azul-índigo Tailwind, zero teal SaaS.
# Aliases BRAND_TEAL/BRAND_INDIGO/BRAND_ORANGE/BRAND_BLUE apontam agora
# pros novos valores; nome dos aliases é histórico, não descreve mais a
# cor. Código novo deve puxar direto de PALETTE_DARK["accent"] etc.
BRAND_TEAL         = "#B45309"   # âmbar-carimbo (secundária no dark)
BRAND_TEAL_HOVER   = "#D97706"
BRAND_INDIGO       = "#15803D"   # verde-fisco (primária no dark)
BRAND_INDIGO_HOVER = "#16A34A"
BRAND_INDIGO_PRESSED = "#14532D"
BRAND_ORANGE       = BRAND_TEAL
BRAND_ORANGE_HOVER = BRAND_TEAL_HOVER
BRAND_ORANGE_SOFT  = "rgba(180, 83, 9, 0.16)"
BRAND_BLUE         = BRAND_INDIGO
BRAND_BLUE_HOVER   = BRAND_INDIGO_HOVER
BRAND_BLUE_PRESSED = BRAND_INDIGO_PRESSED


# Paleta DARK — verde-fisco (Receita/contador) + âmbar-carimbo.
# Sai completamente do azul: sem petróleo, sem índigo, sem teal.
PALETTE_DARK = {
    "bg_0":         "#0F141A",
    "bg_1":         "#171E26",
    "bg_2":         "#202A35",
    "bg_3":         "#2B3949",
    "border":       "#344252",
    "border_soft":  "#273340",
    "text":         "#F5F7FA",
    "text_muted":   "#B7C2CF",
    "text_disabled":"#718096",
    "accent":       "#15803D",   # verde-fisco (ação primária)
    "accent_hover": "#16A34A",
    "accent_pressed":"#14532D",
    # 'brand_orange' (nome histórico): agora é âmbar-carimbo — remete
    # a selo/documento oficial impresso. Complementa o verde-fisco.
    "brand_orange":       "#B45309",   # âmbar-carimbo (brand secundária)
    "brand_orange_hover": "#D97706",
    "brand_orange_soft":  "rgba(180, 83, 9, 0.18)",
    "brand_blue":         "#15803D",   # alias legado → verde
    # 'success' fica num verde CLARO pra distinguir do accent verde-fisco
    # escuro. Sem esse offset, badge de sucesso somia visualmente ao lado
    # do botão primário.
    "success":      "#4ADE80",
    "warning":      "#FCD34D",
    "danger":       "#EF4444",
}

# Paleta LIGHT — planilha corporativa (SAP/TOTVS legado).
# Azul-marinho tradicional (não Tailwind blue-500), branco puro no
# conteúdo, bordô-registro como secundária.
PALETTE_LIGHT = {
    "bg_0":         "#F3F5F7",
    "bg_1":         "#FFFFFF",
    "bg_2":         "#EAEEF2",
    "bg_3":         "#DCE3EA",
    "border":       "#B8C2CC",
    "border_soft":  "#D6DDE3",
    "text":         "#0F172A",
    "text_muted":   "#475569",
    "text_disabled":"#94A3B8",
    "accent":       "#1E3A5F",   # azul-marinho tradicional (SAP/Excel)
    "accent_hover": "#2A4B7A",
    "accent_pressed":"#14284A",
    "brand_orange":       "#7C2D12",   # bordô-registro (secundária)
    "brand_orange_hover": "#9A3412",
    "brand_orange_soft":  "rgba(124, 45, 18, 0.10)",
    "brand_blue":         "#1E3A5F",
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
QPushButton[navItem="true"] {{
    background: transparent;
    color: {p["text_muted"]};
    border: none;
    border-left: 2px solid transparent;
    text-align: left;
    padding: 9px 16px;
    font-size: 13px;
    font-weight: 500;
    min-height: 32px;
}}
QPushButton[navItem="true"]:hover {{
    background: {p["bg_2"]};
    color: {p["text"]};
}}
QPushButton[navItem="true"][active="true"] {{
    background: {p["bg_2"]};
    color: {p["accent"]};
    border-left: 2px solid {p["accent"]};
    font-weight: 600;
}}
QPushButton[iconOnly="true"] {{
    background: transparent;
    border: 1px solid transparent;
    color: {p["text_muted"]};
    padding: 6px 8px;
    font-size: 14px;
    min-height: 20px;
    min-width: 20px;
    border-radius: 3px;
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
    border-radius: 6px;
}}
QFrame[cardFooter="true"] {{
    background: {p["bg_0"]};
    border-top: 1px solid {p["border_soft"]};
    border-bottom-left-radius: 5px;
    border-bottom-right-radius: 5px;
}}

/* ---------- KPI Cards ---------- */
QFrame[kpi="true"] {{
    background: {p["bg_1"]};
    border: 1px solid {p["border_soft"]};
    border-radius: 6px;
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
    border-radius: 4px;
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
    border-radius: 4px;
}}

/* ---------- Buttons ---------- */
QPushButton {{
    background: {p["bg_2"]};
    border: 1px solid {p["border"]};
    border-radius: 4px;
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
    border-radius: 4px;
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

/* ---------- Calendar popup (QDateEdit) ----------
 * QCalendarWidget usa um QTableView interno. Sem overrides explícitos,
 * a regra global QTableView::item da PreviewTable (padding 9px 12px)
 * vazava pro popup interno, empurrando datas de 2 dígitos (10+) pra
 * fora da célula — o popup mostrava só dias 1-9. Aqui damos padding
 * compacto e cell width justo pro calendário. NUNCA use chaves
 * literais nesse comentário: o QSS está dentro de f-string Python e
 * chaves não escapadas quebram o parser (build-74 explodiu por isso). */
QCalendarWidget QAbstractItemView {{
    background: {p["bg_1"]};
    selection-background-color: {p["accent"]};
    selection-color: white;
    outline: 0;
    border: none;
    font-size: 12px;
}}
QCalendarWidget QAbstractItemView:enabled {{
    color: {p["text"]};
}}
QCalendarWidget QAbstractItemView:disabled {{
    color: {p["text_disabled"]};
}}
QCalendarWidget QTableView {{
    background: {p["bg_1"]};
    border: none;
    gridline-color: transparent;
    alternate-background-color: {p["bg_1"]};
}}
QCalendarWidget QTableView::item {{
    padding: 2px 4px;
    border-bottom: none;
    min-width: 24px;
}}
QCalendarWidget QHeaderView::section {{
    background: {p["bg_2"]};
    color: {p["text_muted"]};
    padding: 4px 4px;
    border: none;
    font-weight: 700;
    font-size: 10px;
    text-transform: none;
    letter-spacing: 0;
}}
QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background: {p["bg_2"]};
    border-bottom: 1px solid {p["border_soft"]};
}}
QCalendarWidget QToolButton {{
    background: transparent;
    color: {p["text"]};
    border: none;
    padding: 6px 10px;
    font-weight: 600;
    font-size: 12px;
}}
QCalendarWidget QToolButton:hover {{
    background: {p["bg_3"]};
    border-radius: 3px;
}}
QCalendarWidget QToolButton::menu-indicator {{
    image: none;
}}
QCalendarWidget QSpinBox {{
    background: {p["bg_2"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    border-radius: 3px;
    padding: 2px 4px;
    min-height: 18px;
}}

/* ---------- Scroll ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 6px 0;
}}
QScrollBar::handle:vertical {{
    background: {p["border"]};
    border-radius: 3px;
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
    border-radius: 3px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {p["brand_orange"]};
}}

/* ---------- Progress ---------- */
QProgressBar {{
    background: {p["bg_2"]};
    border: 1px solid {p["border_soft"]};
    border-radius: 3px;
    height: 10px;
    text-align: center;
    color: {p["text"]};
    font-size: 11px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                 stop:0 {p["brand_orange"]}, stop:1 {p["accent"]});
    border-radius: 2px;
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
    border-radius: 4px;
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
    border-radius: 4px;
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
