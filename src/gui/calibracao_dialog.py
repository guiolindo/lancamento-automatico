"""
Diálogo de calibração da tela do TOTVS.

Para cada campo mostra uma linha:
    [Rótulo]  [x, y]  [Capturar]

Ao clicar Capturar, mostra countdown de 3s durante o qual o usuário
posiciona o mouse sobre o campo real do TOTVS. Ao término, captura a
posição absoluta do mouse e converte pra offset relativo ao canto
superior-esquerdo da janela TOTVS.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QVBoxLayout
)

from ..core.calibracao import CAMPOS, Calibracao


class CalibracaoDialog(QDialog):
    def __init__(self, calibracao: Calibracao, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibrar campos do TOTVS")
        self.setMinimumWidth(560)
        self._calibracao = Calibracao(
            titulo_janela=calibracao.titulo_janela,
            campos=dict(calibracao.campos),
        )
        self._linhas: dict[str, tuple[QLabel, QPushButton]] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        titulo = QLabel("Calibrar posições dos campos")
        titulo.setProperty("h1", True)
        root.addWidget(titulo)

        instr = QLabel(
            "1. Abra a tela <b>Inclusão de Títulos</b> do TOTVS (em branco).\n"
            "2. Para cada linha abaixo, clique em <b>Capturar</b>, e depois tem "
            "3 segundos para <b>passar o mouse por cima do campo do TOTVS</b>. "
            "O app grava a posição.\n"
            "3. Feche este diálogo em <b>Salvar</b> ao concluir todos os campos."
        )
        instr.setWordWrap(True)
        instr.setProperty("muted", True)
        root.addWidget(instr)

        grid = QGridLayout()
        grid.setSpacing(8)
        for i, (chave, rotulo, _is_btn) in enumerate(CAMPOS):
            lbl_nome = QLabel(rotulo)
            lbl_pos = QLabel(self._formatar_pos(chave))
            lbl_pos.setMinimumWidth(90)
            lbl_pos.setAlignment(Qt.AlignCenter)
            lbl_pos.setProperty("muted", True)
            btn = QPushButton("Capturar")
            btn.clicked.connect(lambda _=False, k=chave: self._iniciar_captura(k))

            grid.addWidget(lbl_nome, i, 0)
            grid.addWidget(lbl_pos, i, 1)
            grid.addWidget(btn, i, 2)
            self._linhas[chave] = (lbl_pos, btn)
        root.addLayout(grid)

        self._status = QLabel("")
        self._status.setProperty("muted", True)
        self._status.setAlignment(Qt.AlignCenter)
        root.addWidget(self._status)

        acoes = QHBoxLayout()
        acoes.addStretch(1)
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.clicked.connect(self.reject)
        acoes.addWidget(btn_cancelar)

        self._btn_salvar = QPushButton("Salvar")
        self._btn_salvar.setProperty("primary", True)
        self._btn_salvar.clicked.connect(self._salvar)
        acoes.addWidget(self._btn_salvar)
        root.addLayout(acoes)

    def _formatar_pos(self, chave: str) -> str:
        pos = self._calibracao.campos.get(chave)
        return f"{pos[0]}, {pos[1]}" if pos else "—"

    def _iniciar_captura(self, chave: str) -> None:
        # Countdown 3s. Durante ele o usuário posiciona o mouse sobre o campo.
        self._segundos_restantes = 3
        self._chave_atual = chave
        self._status.setText(
            f"Passe o mouse sobre '{self._rotulo(chave)}' no TOTVS — "
            f"capturando em {self._segundos_restantes}..."
        )
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_captura)
        self._timer.start(1000)

    def _rotulo(self, chave: str) -> str:
        for k, r, _ in CAMPOS:
            if k == chave:
                return r
        return chave

    def _tick_captura(self) -> None:
        self._segundos_restantes -= 1
        if self._segundos_restantes > 0:
            self._status.setText(
                f"Passe o mouse sobre '{self._rotulo(self._chave_atual)}' — "
                f"capturando em {self._segundos_restantes}..."
            )
            return
        self._timer.stop()
        self._capturar_agora()

    def _capturar_agora(self) -> None:
        try:
            import pyautogui
            import pygetwindow as gw
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Erro", f"Não foi possível ler o mouse/janela: {e}")
            return

        # Posição atual do mouse.
        mx, my = pyautogui.position()

        # Localiza a janela do TOTVS pelo título parcial.
        titulo = self._calibracao.titulo_janela
        try:
            janelas = [w for w in gw.getAllWindows() if titulo.lower() in (w.title or "").lower()]
        except Exception:  # noqa: BLE001
            janelas = []
        if not janelas:
            QMessageBox.warning(
                self, "Janela não encontrada",
                f"Não consegui encontrar uma janela com título contendo '{titulo}'. "
                "Verifique se a tela 'Inclusão de Títulos' está aberta.",
            )
            self._status.setText("Falhou — janela do TOTVS não encontrada")
            return

        win = janelas[0]
        wx, wy = win.left, win.top
        offset = (int(mx - wx), int(my - wy))
        self._calibracao.campos[self._chave_atual] = offset

        lbl, _btn = self._linhas[self._chave_atual]
        lbl.setText(self._formatar_pos(self._chave_atual))
        self._status.setText(
            f"✓ {self._rotulo(self._chave_atual)}: capturado em ({mx}, {my}) — "
            f"offset ({offset[0]}, {offset[1]})"
        )

    def _salvar(self) -> None:
        falta = self._calibracao.falta_calibrar()
        if falta:
            resp = QMessageBox.question(
                self, "Calibração incompleta",
                f"Ainda faltam {len(falta)} campo(s). Salvar assim mesmo?",
            )
            if resp != QMessageBox.Yes:
                return
        self.accept()

    def calibracao(self) -> Calibracao:
        return self._calibracao
