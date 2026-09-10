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
    QDialog, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QMessageBox, QPushButton, QVBoxLayout
)

from ..core.calibracao import CAMPOS, CAMPOS_OPCIONAIS, Calibracao


_TODOS_CAMPOS = CAMPOS + CAMPOS_OPCIONAIS


class CalibracaoDialog(QDialog):
    def __init__(self, calibracao: Calibracao, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibrar campos do TOTVS")
        self.setMinimumWidth(560)
        self._calibracao = Calibracao(
            titulo_janela=calibracao.titulo_janela,
            campos=dict(calibracao.campos),
            cores=dict(calibracao.cores),
        )
        self._linhas: dict[str, tuple[QLabel, QPushButton]] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        titulo = QLabel("Calibrar posições dos campos")
        titulo.setProperty("h1", True)
        root.addWidget(titulo)

        instr = QLabel(
            "<b>1.</b> Abra a tela <b>Inclusão de Títulos</b> do TOTVS (em branco).<br>"
            "<b>2.</b> No campo abaixo, informe um trecho do <b>título da janela</b> "
            "que aparece na sua barra de tarefas. Se não souber, clique em "
            "<b>Listar janelas</b> pra ver todas as janelas abertas agora.<br>"
            "<b>3.</b> Para cada linha, clique em <b>Capturar</b>, você tem 3 segundos "
            "para posicionar o mouse sobre o campo do TOTVS.<br>"
            "<b>4.</b> Feche em <b>Salvar</b> ao concluir."
        )
        instr.setWordWrap(True)
        instr.setProperty("muted", True)
        root.addWidget(instr)

        # Título da janela
        linha_titulo = QHBoxLayout()
        linha_titulo.addWidget(QLabel("Título da janela do TOTVS:"))
        self._input_titulo = QLineEdit(self._calibracao.titulo_janela)
        self._input_titulo.textChanged.connect(self._on_titulo_alterado)
        linha_titulo.addWidget(self._input_titulo, 1)
        btn_listar = QPushButton("Listar janelas")
        btn_listar.clicked.connect(self._listar_janelas)
        linha_titulo.addWidget(btn_listar)
        root.addLayout(linha_titulo)

        grid = QGridLayout()
        grid.setSpacing(8)
        for i, (chave, rotulo, _is_btn) in enumerate(_TODOS_CAMPOS):
            lbl_nome = QLabel(rotulo)
            if chave in ("popup_indicador", "popup_ok"):
                lbl_nome.setProperty("muted", True)
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

        dica_popup = QLabel(
            "<i>Dica: para calibrar os campos do POPUP, provoque um erro "
            "de duplicidade no TOTVS (tente lançar um Nro.Documento que "
            "já existe). Com o popup 'Atenção' visível, capture os dois "
            "campos opcionais acima. Isso é opcional mas RECOMENDADO — "
            "sem eles o robô não detecta duplicidade em modo RemoteApp.</i>"
        )
        dica_popup.setWordWrap(True)
        dica_popup.setProperty("muted", True)
        root.addWidget(dica_popup)

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

    def _on_titulo_alterado(self, txt: str) -> None:
        self._calibracao.titulo_janela = txt.strip()

    def _listar_janelas(self) -> None:
        try:
            import pygetwindow as gw
            titulos = sorted({(w.title or "").strip() for w in gw.getAllWindows() if (w.title or "").strip()})
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Erro", f"Não foi possível listar janelas: {e}")
            return

        if not titulos:
            QMessageBox.information(self, "Janelas", "Nenhuma janela visível encontrada.")
            return

        titulo, ok = QInputDialog.getItem(
            self, "Selecionar janela do TOTVS",
            "Escolha a janela do TOTVS (ou parte do título):",
            titulos, 0, True,
        )
        if ok and titulo:
            self._input_titulo.setText(titulo.strip())

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
        for k, r, _ in _TODOS_CAMPOS:
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

        mx, my = pyautogui.position()

        titulo = (self._calibracao.titulo_janela or "").strip()
        janelas = []
        if titulo:
            try:
                janelas = [w for w in gw.getAllWindows() if titulo.lower() in (w.title or "").lower()]
            except Exception:  # noqa: BLE001
                janelas = []

        if not janelas:
            resp = QMessageBox.question(
                self, "Janela não encontrada",
                f"Não achei janela com título contendo '{titulo}'.\n\n"
                "Você quer salvar como coordenada ABSOLUTA (0,0 do "
                "canto da tela)? Se a janela do TOTVS não se mover, funciona igual.\n\n"
                "Sim = salva absoluto (não usa offset da janela)\n"
                "Não = cancela essa captura, ajuste o título e tente de novo",
            )
            if resp != QMessageBox.Yes:
                self._status.setText("Captura cancelada — corrija o título e tente de novo")
                return
            offset = (int(mx), int(my))
            self._calibracao.titulo_janela = ""  # marca modo absoluto
            self._input_titulo.setText("")
        else:
            win = janelas[0]
            offset = (int(mx - win.left), int(my - win.top))

        self._calibracao.campos[self._chave_atual] = offset

        # Para popup_indicador, também guarda a cor RGB do pixel — o robô
        # compara essa cor em runtime pra detectar o popup.
        if self._chave_atual == "popup_indicador":
            try:
                rgb = pyautogui.pixel(mx, my)
                self._calibracao.cores["popup_indicador"] = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
            except Exception:  # noqa: BLE001
                pass

        lbl, _btn = self._linhas[self._chave_atual]
        lbl.setText(self._formatar_pos(self._chave_atual))
        modo = "absoluto" if not janelas else f"offset ({offset[0]}, {offset[1]})"
        extra = ""
        if self._chave_atual == "popup_indicador" and "popup_indicador" in self._calibracao.cores:
            r, g, b = self._calibracao.cores["popup_indicador"]
            extra = f" | cor RGB ({r},{g},{b})"
        self._status.setText(
            f"OK {self._rotulo(self._chave_atual)}: mouse em ({mx}, {my}) - {modo}{extra}"
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
