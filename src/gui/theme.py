"""Tema visual profissional (dark modern) para a aplicação."""

COLORS = {
    "bg_0": "#0F1218",
    "bg_1": "#151A22",
    "bg_2": "#1C2230",
    "bg_3": "#252C3D",
    "border": "#2A3244",
    "border_soft": "#1F2634",
    "text": "#E6E9F0",
    "text_muted": "#8892A6",
    "accent": "#4F8CFF",
    "accent_hover": "#6BA0FF",
    "accent_pressed": "#3D74E0",
    "success": "#3BD787",
    "warning": "#F5B851",
    "danger": "#F26B6B",
}


QSS = f"""
* {{
    font-family: "Segoe UI", "Inter", "SF Pro Text", sans-serif;
    font-size: 13px;
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
    font-size: 16px;
    font-weight: 600;
    padding: 24px 20px 8px 20px;
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
    font-size: 22px;
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
    border: 1px solid {COLORS["border_soft"]};
    border-radius: 10px;
}}

/* ---------- Inputs ---------- */
QLineEdit, QDateEdit, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {COLORS["bg_2"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 8px 10px;
    color: {COLORS["text"]};
    selection-background-color: {COLORS["accent"]};
}}
QLineEdit:focus, QDateEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {COLORS["accent"]};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background: {COLORS["bg_2"]};
    border: 1px solid {COLORS["border"]};
    selection-background-color: {COLORS["accent"]};
    padding: 4px;
}}

/* ---------- Buttons ---------- */
QPushButton {{
    background: {COLORS["bg_3"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 6px;
    padding: 8px 16px;
    color: {COLORS["text"]};
    font-weight: 500;
}}
QPushButton:hover {{
    background: {COLORS["bg_2"]};
    border-color: {COLORS["accent"]};
}}
QPushButton:disabled {{
    color: {COLORS["text_muted"]};
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

/* ---------- Table ---------- */
QTableView, QTableWidget {{
    background: {COLORS["bg_1"]};
    alternate-background-color: {COLORS["bg_2"]};
    gridline-color: {COLORS["border_soft"]};
    border: 1px solid {COLORS["border_soft"]};
    border-radius: 8px;
    selection-background-color: {COLORS["accent"]};
    selection-color: white;
}}
QHeaderView::section {{
    background: {COLORS["bg_2"]};
    color: {COLORS["text_muted"]};
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid {COLORS["border_soft"]};
    font-weight: 600;
    font-size: 11px;
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
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {COLORS["bg_3"]};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLORS["border"]};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
}}
QScrollBar::handle:horizontal {{
    background: {COLORS["bg_3"]};
    border-radius: 5px;
    min-width: 30px;
}}

/* ---------- Progress ---------- */
QProgressBar {{
    background: {COLORS["bg_2"]};
    border: 1px solid {COLORS["border_soft"]};
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
    background: rgba(79, 140, 255, 0.15);
    color: {COLORS["accent"]};
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel[badge="sucesso"] {{
    background: rgba(59, 215, 135, 0.15);
    color: {COLORS["success"]};
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
}}
QLabel[badge="falha"] {{
    background: rgba(242, 107, 107, 0.15);
    color: {COLORS["danger"]};
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
}}

/* ---------- Log console ---------- */
QPlainTextEdit#LogConsole {{
    background: {COLORS["bg_0"]};
    border: 1px solid {COLORS["border_soft"]};
    border-radius: 8px;
    font-family: "JetBrains Mono", "Cascadia Code", "Consolas", monospace;
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
"""
