"""
Diálogo de calibração da tela do TOTVS.

Para cada campo mostra uma linha:
    [Rótulo]  [x, y]  [Capturar]

Ao clicar Capturar, mostra countdown de 3s durante o qual o usuário
posiciona o mouse sobre o campo real do TOTVS. Ao término, captura a
posição absoluta do mouse e converte pra offset relativo ao canto
superior-esquerdo da janela TOTVS.

Título da janela é FIXO = 'Operador Financeiro' (o app sempre chama
assim). Se por acaso mudar de nome no futuro, edite manualmente em
~/.lancamento-automatico/calibracao.json.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget
)

from ..core.calibracao import CAMPOS, CAMPOS_OPCIONAIS


_TODOS_CAMPOS = CAMPOS + CAMPOS_OPCIONAIS


class CalibracaoDialog(QDialog):
    def __init__(
        self,
        calibracao,
        parent=None,
        titulo_janela_default: str = "Operador Financeiro",
        campos_obrigatorios: list | None = None,
        campos_opcionais: list | None = None,
        rotulo_tela: str = "Inclusão de Títulos",
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Calibrar campos — {rotulo_tela}")
        # Título da janela: default 'Operador Financeiro'. Para Orçamento
        # (build-96) passamos 'Orçamento' como default.
        self._campos_lista = (campos_obrigatorios or CAMPOS) + (campos_opcionais or CAMPOS_OPCIONAIS)
        self._campos_opcionais_keys = {c[0] for c in (campos_opcionais or CAMPOS_OPCIONAIS)}
        # Cria uma cópia do mesmo tipo do objeto de calibração recebido —
        # funciona pra Calibracao (Operador Financeiro) e CalibracaoOrcamento
        # (build-96) sem acoplamento.
        klass = type(calibracao)
        self._calibracao = klass(
            titulo_janela=calibracao.titulo_janela or titulo_janela_default,
            campos=dict(calibracao.campos),
            cores=dict(calibracao.cores),
        )
        self._titulo_janela_default = titulo_janela_default
        self._rotulo_tela = rotulo_tela
        self._linhas: dict[str, tuple[QLabel, QPushButton]] = {}

        # Dialog fica dentro do tamanho da tela disponível (sem barra de tarefas).
        tela = QGuiApplication.primaryScreen().availableGeometry() if QGuiApplication.primaryScreen() else None
        largura_max = 620
        altura_max = 720 if tela is None else min(720, tela.height() - 60)
        self.setMinimumWidth(560)
        self.resize(largura_max, altura_max)

        # Layout raiz vertical: cabeçalho (fixo) + scroll (conteúdo) + rodapé (fixo)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(20, 16, 20, 16)
        raiz.setSpacing(10)

        titulo = QLabel("Calibrar posições dos campos")
        titulo.setProperty("h1", True)
        raiz.addWidget(titulo)

        instr = QLabel(
            f"<b>1.</b> Abra a tela <b>{self._rotulo_tela}</b> do TOTVS (em branco).<br>"
            "<b>2.</b> Para cada linha, clique em <b>Capturar</b> — você tem 3 segundos "
            "para posicionar o mouse sobre o campo do TOTVS.<br>"
            "<b>3.</b> Feche em <b>Salvar</b>."
        )
        instr.setWordWrap(True)
        instr.setProperty("muted", True)
        raiz.addWidget(instr)

        # --- área rolável no meio ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        conteudo = QWidget()
        rolavel = QVBoxLayout(conteudo)
        rolavel.setContentsMargins(0, 0, 0, 0)
        rolavel.setSpacing(8)

        grid = QGridLayout()
        grid.setSpacing(6)
        for i, (chave, rotulo, _is_btn) in enumerate(self._campos_lista):
            lbl_nome = QLabel(rotulo)
            if chave in self._campos_opcionais_keys:
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
        rolavel.addLayout(grid)

        dica_popup = QLabel(
            "<i>Dica: para calibrar os campos do POPUP, provoque um erro "
            "de duplicidade (lance um Nro.Documento que já existe). Com o "
            "popup 'Aviso' visível, capture os dois campos opcionais acima. "
            "Opcional mas recomendado.</i>"
        )
        dica_popup.setWordWrap(True)
        dica_popup.setProperty("muted", True)
        rolavel.addWidget(dica_popup)
        rolavel.addStretch(1)

        scroll.setWidget(conteudo)
        raiz.addWidget(scroll, 1)

        # --- rodapé fixo com Status + botões ---
        self._status = QLabel("")
        self._status.setProperty("muted", True)
        self._status.setAlignment(Qt.AlignCenter)
        self._status.setWordWrap(True)
        raiz.addWidget(self._status)

        acoes = QHBoxLayout()
        acoes.addStretch(1)
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.clicked.connect(self.reject)
        acoes.addWidget(btn_cancelar)

        self._btn_salvar = QPushButton("Salvar")
        self._btn_salvar.setProperty("primary", True)
        self._btn_salvar.clicked.connect(self._salvar)
        acoes.addWidget(self._btn_salvar)
        raiz.addLayout(acoes)

    def _formatar_pos(self, chave: str) -> str:
        pos = self._calibracao.campos.get(chave)
        return f"{pos[0]}, {pos[1]}" if pos else "—"

    def _iniciar_captura(self, chave: str) -> None:
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
        for k, r, _ in self._campos_lista:
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

        # Auto-detecta a janela (case-insensitive, substring — casa
        # 'Operador Financeiro (Remoto)' e variantes com sufixos também).
        titulo = self._calibracao.titulo_janela or self._titulo_janela_default
        janelas = []
        try:
            janelas = [w for w in gw.getAllWindows() if titulo.lower() in (w.title or "").lower()]
        except Exception:  # noqa: BLE001
            janelas = []

        if not janelas:
            QMessageBox.warning(
                self, "TOTVS não aberto",
                f"Não achei nenhuma janela com '{titulo}' no título. "
                "Abra o TOTVS antes de calibrar.",
            )
            self._status.setText(f"TOTVS não aberto — abra a tela '{titulo}' e tente de novo")
            return

        win = janelas[0]
        offset = (int(mx - win.left), int(my - win.top))
        self._calibracao.campos[self._chave_atual] = offset

        if self._chave_atual == "popup_indicador":
            try:
                rgb = pyautogui.pixel(mx, my)
                self._calibracao.cores["popup_indicador"] = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
            except Exception:  # noqa: BLE001
                pass

        lbl, _btn = self._linhas[self._chave_atual]
        lbl.setText(self._formatar_pos(self._chave_atual))
        extra = ""
        if self._chave_atual == "popup_indicador" and "popup_indicador" in self._calibracao.cores:
            r, g, b = self._calibracao.cores["popup_indicador"]
            extra = f" | cor RGB ({r},{g},{b})"
        self._status.setText(
            f"OK {self._rotulo(self._chave_atual)}: mouse em ({mx}, {my}) — offset "
            f"({offset[0]}, {offset[1]}) na janela '{win.title}'{extra}"
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

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.setWindowOpacity(0.0)
        self._fade = QPropertyAnimation(self, b"windowOpacity")
        self._fade.setDuration(200)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.InOutQuad)
        self._fade.start()

    def calibracao(self):
        return self._calibracao
