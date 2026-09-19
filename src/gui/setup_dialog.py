from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget
)


class SetupDialog(QDialog):
    """Diálogo de primeira execução — pede chave da API Gemini.

    Segurança (build-85): a chave NUNCA aparece na UI, nem via botão
    "Mostrar". Uma vez configurada, o campo mostra apenas um placeholder
    "chave configurada — deixe em branco pra manter, digite pra
    substituir". Isso impede que alguém com acesso momentâneo ao PC
    consiga ler a chave e abusar de conta paga.

    Storage: cifrada com Windows DPAPI (ver core/secret_store.py).
    """

    def __init__(self, parent: QWidget | None = None, chave_ja_configurada: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Configuração inicial")
        self.setModal(True)
        self.setMinimumWidth(520)

        self._chave_ja_configurada = chave_ja_configurada
        self._manter_atual = chave_ja_configurada  # muda pra False se usuário digitar

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        titulo = QLabel("Configuração do Auto Conferi")
        titulo.setProperty("h1", True)
        layout.addWidget(titulo)

        desc = QLabel(
            "Chave da API do Google Gemini — usada pra extrair os "
            "lançamentos dos relatórios. É armazenada <b>criptografada</b> "
            "no seu perfil (Windows DPAPI): só o seu usuário nessa máquina "
            "consegue descriptografar. Nem eu (o app) consigo ler ela sem "
            "estar rodando aqui."
        )
        desc.setWordWrap(True)
        desc.setProperty("muted", True)
        layout.addWidget(desc)

        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 8)
        form.setSpacing(10)

        self._input_key = QLineEdit()
        self._input_key.setEchoMode(QLineEdit.Password)
        if chave_ja_configurada:
            self._input_key.setPlaceholderText(
                "•••••••••  chave já configurada — deixe em branco pra manter"
            )
        else:
            self._input_key.setPlaceholderText("AIza…")
        # Se o usuário digitar QUALQUER coisa, deixa de "manter atual"
        self._input_key.textEdited.connect(self._on_editou)
        form.addRow(QLabel("Chave da API Gemini:"), self._input_key)

        layout.addLayout(form)

        # Aviso de segurança sutil, no lugar do antigo botão "Mostrar chave"
        aviso = QLabel(
            "🔒 Por segurança, a chave nunca é exibida depois de salva. "
            "Se precisar trocar, cole a nova aqui."
        )
        aviso.setStyleSheet(
            "color: #94A3B8; font-size: 11px; padding: 4px 0;"
        )
        aviso.setWordWrap(True)
        layout.addWidget(aviso)

        botoes = QVBoxLayout()
        botoes.setSpacing(8)
        self._btn_salvar = QPushButton(
            "Salvar" if chave_ja_configurada else "Salvar e continuar"
        )
        self._btn_salvar.setProperty("primary", True)
        self._btn_salvar.clicked.connect(self._salvar)
        botoes.addWidget(self._btn_salvar)

        rot_pular = "Fechar" if chave_ja_configurada else "Configurar depois"
        self._btn_pular = QPushButton(rot_pular)
        self._btn_pular.clicked.connect(self.reject)
        botoes.addWidget(self._btn_pular)

        layout.addStretch(1)
        layout.addLayout(botoes)

    def _on_editou(self, texto: str) -> None:
        # Assim que o usuário edita, entende-se que quer substituir
        self._manter_atual = False

    def _salvar(self) -> None:
        # Se o campo veio vazio E já tinha chave configurada → mantém
        # a atual (accept mas sem substituir). Se veio vazio E não
        # tinha nada, foca o campo (não deixa salvar em branco).
        texto = self._input_key.text().strip()
        if not texto:
            if self._chave_ja_configurada:
                # manter_atual já é True (usuário não editou)
                self.accept()
            else:
                self._input_key.setFocus()
            return
        self.accept()

    def chave(self) -> str:
        """Chave nova digitada. Vazia significa 'manter a atual'."""
        return self._input_key.text().strip()

    def substituir(self) -> bool:
        """True se o usuário digitou uma chave nova. False se manter."""
        return not self._manter_atual and bool(self.chave())

    def showEvent(self, event) -> None:  # noqa: N802 (Qt convention)
        super().showEvent(event)
        self.setWindowOpacity(0.0)
        self._fade = QPropertyAnimation(self, b"windowOpacity")
        self._fade.setDuration(200)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.InOutQuad)
        self._fade.start()
