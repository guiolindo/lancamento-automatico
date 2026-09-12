from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget
)


class SetupDialog(QDialog):
    """Diálogo de primeira execução — pede chave da API Gemini."""

    def __init__(self, parent: QWidget | None = None, current_key: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Configuração inicial")
        self.setModal(True)
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        titulo = QLabel("Bem-vindo ao Auto Conferi")
        titulo.setProperty("h1", True)
        layout.addWidget(titulo)

        desc = QLabel(
            "Para começar, cole sua chave da API do Google Gemini. Ela fica "
            "armazenada localmente no seu perfil e nunca é enviada a "
            "outro serviço."
        )
        desc.setWordWrap(True)
        desc.setProperty("muted", True)
        layout.addWidget(desc)

        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 8)
        form.setSpacing(10)

        self._input_key = QLineEdit(current_key)
        self._input_key.setEchoMode(QLineEdit.Password)
        self._input_key.setPlaceholderText("AIza...")
        form.addRow(QLabel("Chave da API Gemini:"), self._input_key)

        layout.addLayout(form)

        self._toggle_visibility = QPushButton("Mostrar chave")
        self._toggle_visibility.setCheckable(True)
        self._toggle_visibility.toggled.connect(self._alternar_visibilidade)
        layout.addWidget(self._toggle_visibility, alignment=Qt.AlignRight)

        botoes = QVBoxLayout()
        botoes.setSpacing(8)
        self._btn_salvar = QPushButton("Salvar e continuar")
        self._btn_salvar.setProperty("primary", True)
        self._btn_salvar.clicked.connect(self._salvar)
        botoes.addWidget(self._btn_salvar)

        self._btn_pular = QPushButton("Configurar depois")
        self._btn_pular.clicked.connect(self.reject)
        botoes.addWidget(self._btn_pular)

        layout.addStretch(1)
        layout.addLayout(botoes)

    def _alternar_visibilidade(self, checked: bool) -> None:
        self._input_key.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        self._toggle_visibility.setText("Ocultar chave" if checked else "Mostrar chave")

    def _salvar(self) -> None:
        if not self._input_key.text().strip():
            self._input_key.setFocus()
            return
        self.accept()

    def chave(self) -> str:
        return self._input_key.text().strip()
