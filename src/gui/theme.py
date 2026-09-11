"""Tema visual — ferramenta profissional de operação fiscal (dark)."""

COLORS = {
    "bg_0": "#171A1F",
    "bg_1": "#20252D",
    "bg_2": "#282F3A",
    "bg_3": "#2F3644",
    "border": "#353D4A",
    "border_soft": "#2A313D",
    "text": "#F1F5F9",
    "text_muted": "#A8B3C2",
    "text_disabled": "#667085",
    "accent": "#2563EB",
    "accent_hover": "#3B82F6",
    "accent_pressed": "#1D4ED8",
    "success": "#16A34A",
    "warning": "#D97706",
    "danger": "#DC2626",
}


QSS = f"""
* {{
    font-family: "Segoe UI Variable", "Segoe UI", "Inter", sans-serif;
    font-size: 14px;
    color: {COLORS["text"]};
}}

QMainWindow, QDialog {{
    background: {COLORS["bg_0"]};
}}

/* ---------- Sidebar ---------- */
#Sidebar {{
    background: {COLORS["bg_1"]};
    border-right: 1px solid {COLORS["border_soft"]};
}}
#SidebarBrand {{
    color: {COLORS["text"]};
    font-size: 18px;
    font-weight: 600;
    padding: 24px 20px 4px 20px;
}}
#SidebarSubtitle {{
    color: {COLORS["text_muted"]};
    font-size: 11px;
    padding: 0 20px 24px 20px;
    letter-spacing: 0.5px;
}}
QPushButton[nav="true"] {{
    background: transparent;
    color: {COLORS["text_muted"]};
    border: none;
    text-align: left;
    padding: 10px 20px;
    font-size: 13px;
    border-left: 3px solid transparent;
}}
QPushButton[nav="true"]:hover {{
    background: {COLORS["bg_2"]};
    color: {COLORS["text"]};
}}
QPushButton[nav="true"][active="true"] {{
    background: {COLORS["bg_2"]};
    color: {COLORS["text"]};
    border-left: 3px solid {COLORS["accent"]};
    font-weight: 500;
}}

/* ---------- Content ---------- */
#Content {{
    background: {COLORS["bg_0"]};
}}
QLabel[h1="true"] {{
    font-size: 20px;
    font-weight: 600;
    color: {COLORS["text"]};
}}
QLabel[h2="true"] {{
    font-size: 15px;
    font-weight: 600;
    color: {COLORS["text"]};
}}
QLabel[muted="true"] {{
    color: {COLORS["text_muted"]};
    font-size: 12px;
}}

/* ---------- Cards ---------- */
QFrame[card="true"] {{
    background: {COLORS["bg_1"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
}}
QFrame[cardFooter="true"] {{
    background: {COLORS["bg_0"]};
    border-top: 1px solid {COLORS["border_soft"]};
    border-bottom-left-radius: 7px;
    border-bottom-right-radius: 7px;
}}

/* ---------- KPI Cards ---------- */
QFrame[kpi="true"] {{
    background: {COLORS["bg_1"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
}}
QLabel[kpiValue="true"] {{
    font-size: 22px;
    font-weight: 700;
    color: {COLORS["text"]};
}}

/* ---------- Toolbar ---------- */
QFrame[toolbar="true"] {{
    background: {COLORS["bg_1"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
}}
QLabel[inlineLabel="true"] {{
    color: {COLORS["text_muted"]};
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding-right: 2px;
}}
QFrame#Divisor {{
    background: {COLORS["border"]};
    border: none;
}}
QFrame#DivisorH {{
    background: {COLORS["border_soft"]};
    border: none;
}}

/* ---------- Inputs ---------- */
QLineEdit, QDateEdit, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {COLORS["bg_2"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 8px 10px;
    min-height: 18px;
    color: {COLORS["text"]};
    selection-background-color: {COLORS["accent"]};
    selection-color: white;
}}
QLineEdit:focus, QDateEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {COLORS["accent"]};
}}
QLineEdit:disabled, QComboBox:disabled {{
    color: {COLORS["text_disabled"]};
    background: {COLORS["bg_1"]};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background: {COLORS["bg_2"]};
    border: 1px solid {COLORS["border"]};
    selection-background-color: {COLORS["accent"]};
    selection-color: white;
    padding: 4px;
}}

/* ---------- Buttons ---------- */
QPushButton {{
    background: {COLORS["bg_2"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 9px 16px;
    color: {COLORS["text"]};
    font-size: 14px;
    font-weight: 600;
    min-height: 20px;
}}
QPushButton:hover {{
    background: {COLORS["bg_3"]};
    border-color: {COLORS["border"]};
}}
QPushButton:pressed {{
    background: {COLORS["bg_1"]};
}}
QPushButton:disabled {{
    color: {COLORS["text_disabled"]};
    background: {COLORS["bg_1"]};
    border-color: {COLORS["border_soft"]};
}}
QPushButton[primary="true"] {{
    background: {COLORS["accent"]};
    color: white;
    border: 1px solid {COLORS["accent"]};
}}
QPushButton[primary="true"]:hover {{
    background: {COLORS["accent_hover"]};
    border-color: {COLORS["accent_hover"]};
}}
QPushButton[primary="true"]:pressed {{
    background: {COLORS["accent_pressed"]};
}}
QPushButton[danger="true"] {{
    background: {COLORS["danger"]};
    color: white;
    border: 1px solid {COLORS["danger"]};
}}
QPushButton[danger="true"]:hover {{
    background: #EF4444;
    border-color: #EF4444;
}}

/* ---------- Table ---------- */
QTableView, QTableWidget {{
    background: {COLORS["bg_1"]};
    alternate-background-color: {COLORS["bg_2"]};
    gridline-color: {COLORS["border_soft"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    selection-background-color: {COLORS["accent"]};
    selection-color: white;
    font-size: 13px;
}}
QHeaderView::section {{
    background: {COLORS["bg_2"]};
    color: {COLORS["text_muted"]};
    padding: 9px 10px;
    border: none;
    border-bottom: 1px solid {COLORS["border"]};
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QTableView::item, QTableWidget::item {{
    padding: 8px 10px;
    border-bottom: 1px solid {COLORS["border_soft"]};
}}

/* ---------- Scroll ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {COLORS["border"]};
    border-radius: 6px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #4B5563;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
}}
QScrollBar::handle:horizontal {{
    background: {COLORS["border"]};
    border-radius: 6px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #4B5563;
}}

/* ---------- Progress ---------- */
QProgressBar {{
    background: {COLORS["bg_2"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    height: 10px;
    text-align: center;
    color: {COLORS["text"]};
}}
QProgressBar::chunk {{
    background: {COLORS["accent"]};
    border-radius: 5px;
}}

/* ---------- Status badges ---------- */
QLabel[badge="pendente"] {{
    background: {COLORS["bg_3"]};
    color: {COLORS["text_muted"]};
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel[badge="andamento"] {{
    background: rgba(37, 99, 235, 0.15);
    color: {COLORS["accent_hover"]};
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel[badge="sucesso"] {{
    background: rgba(22, 163, 74, 0.15);
    color: #22C55E;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel[badge="falha"] {{
    background: rgba(220, 38, 38, 0.15);
    color: #EF4444;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
}}

/* ---------- Log console ---------- */
QPlainTextEdit#LogConsole {{
    background: {COLORS["bg_0"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
    color: {COLORS["text_muted"]};
}}

/* ---------- CheckBox ---------- */
QCheckBox {{
    color: {COLORS["text"]};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {COLORS["border"]};
    background: {COLORS["bg_2"]};
}}
QCheckBox::indicator:checked {{
    background: {COLORS["accent"]};
    border-color: {COLORS["accent"]};
}}
QCheckBox::indicator:hover {{
    border-color: {COLORS["accent"]};
}}

/* ---------- ToolTip ---------- */
QToolTip {{
    background: {COLORS["bg_3"]};
    color: {COLORS["text"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 4px;
    padding: 6px 8px;
}}
"""
