from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QSize, Qt, QThread
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QSizePolicy, QSpacerItem, QVBoxLayout, QWidget
)

from ..core.logger import log
from ..core.mapping import MappingRepository
from ..core.models import Imposto, Lancamento
from ..core.settings_store import SettingsStore
from .preview_table import PreviewTable
from .setup_dialog import SetupDialog
from .theme import QSS
from .workers import ExtracaoWorker, LoteWorker


NAV_ITEMS = [
    ("dashboard", "Lançamento"),
    ("mapeamento", "De-Para"),
    ("configuracoes", "Configurações"),
]


class MainWindow(QMainWindow):
    def __init__(self, settings: SettingsStore, mapping: MappingRepository, mapping_path: Path):
        super().__init__()
        self.settings = settings
        self.mapping = mapping
        self.mapping_path = mapping_path
        self.setWindowTitle("Lançamento Automático — TOTVS")
        self.resize(1200, 780)
        self.setMinimumSize(1000, 640)
        self.setStyleSheet(QSS)

        self._thread: QThread | None = None
        self._worker_extracao: ExtracaoWorker | None = None
        self._worker_lote: LoteWorker | None = None
        self._arquivo_selecionado: Path | None = None
        self._lancamentos: list[Lancamento] = []

        self._montar_ui()
        self._verificar_setup()

    # ---------------- UI ----------------

    def _montar_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._montar_sidebar())
        root.addWidget(self._montar_content(), 1)

    def _montar_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(220)
        v = QVBoxLayout(side)
        v.setContentsMargins(0, 0, 0, 20)
        v.setSpacing(0)

        brand = QLabel("Lançamento")
        brand.setObjectName("SidebarBrand")
        v.addWidget(brand)

        sub = QLabel("AUTOMÁTICO · TOTVS")
        sub.setObjectName("SidebarSubtitle")
        v.addWidget(sub)

        self._nav_buttons: dict[str, QPushButton] = {}
        for key, label in NAV_ITEMS:
            btn = QPushButton(label)
            btn.setProperty("nav", True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._trocar_secao(k))
            self._nav_buttons[key] = btn
            v.addWidget(btn)

        v.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))

        rodape = QLabel("v0.1.0")
        rodape.setProperty("muted", True)
        rodape.setContentsMargins(20, 0, 20, 0)
        v.addWidget(rodape)

        return side

    def _montar_content(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("Content")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(32, 28, 32, 24)
        v.setSpacing(20)

        titulo = QLabel("Novo lote de lançamentos")
        titulo.setProperty("h1", True)
        v.addWidget(titulo)

        subtitulo = QLabel("Envie o resumo do imposto, revise os lançamentos gerados e execute no TOTVS.")
        subtitulo.setProperty("muted", True)
        v.addWidget(subtitulo)

        v.addWidget(self._card_parametros())
        v.addWidget(self._card_preview(), 1)
        v.addWidget(self._card_log())

        return wrap

    def _card_parametros(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        titulo = QLabel("1. Documento e parâmetros")
        titulo.setProperty("h2", True)
        layout.addWidget(titulo)

        linha = QHBoxLayout()
        linha.setSpacing(12)

        # imposto
        col_imp = QVBoxLayout()
        col_imp.addWidget(self._label_campo("Imposto"))
        self._combo_imposto = QComboBox()
        for chave in ("IRRF",):
            self._combo_imposto.addItem(chave)
        col_imp.addWidget(self._combo_imposto)
        linha.addLayout(col_imp)

        # data
        col_data = QVBoxLayout()
        col_data.addWidget(self._label_campo("Data de emissão / vencimento"))
        self._date_emissao = QDateEdit(QDate.currentDate())
        self._date_emissao.setDisplayFormat("dd/MM/yyyy")
        self._date_emissao.setCalendarPopup(True)
        col_data.addWidget(self._date_emissao)
        linha.addLayout(col_data)

        # arquivo
        col_arq = QVBoxLayout()
        col_arq.addWidget(self._label_campo("Documento (PDF ou imagem)"))
        arq_row = QHBoxLayout()
        self._label_arquivo = QLabel("Nenhum arquivo selecionado")
        self._label_arquivo.setProperty("muted", True)
        arq_row.addWidget(self._label_arquivo, 1)
        btn_pick = QPushButton("Selecionar…")
        btn_pick.clicked.connect(self._selecionar_arquivo)
        arq_row.addWidget(btn_pick)
        col_arq.addLayout(arq_row)
        linha.addLayout(col_arq, 1)

        layout.addLayout(linha)

        acoes = QHBoxLayout()
        acoes.addStretch(1)
        self._btn_extrair = QPushButton("Extrair com Gemini")
        self._btn_extrair.setProperty("primary", True)
        self._btn_extrair.clicked.connect(self._extrair)
        acoes.addWidget(self._btn_extrair)
        layout.addLayout(acoes)

        return card

    def _card_preview(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        cab = QHBoxLayout()
        titulo = QLabel("2. Revisão dos lançamentos")
        titulo.setProperty("h2", True)
        cab.addWidget(titulo)
        cab.addStretch(1)

        self._label_resumo = QLabel("—")
        self._label_resumo.setProperty("muted", True)
        cab.addWidget(self._label_resumo)
        layout.addLayout(cab)

        self._tabela = PreviewTable()
        layout.addWidget(self._tabela, 1)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        acoes = QHBoxLayout()

        self._chk_confirmar_auto = QCheckBox(
            "Confirmar automaticamente (o robô aperta o + ao final de cada lançamento)"
        )
        confirmar_padrao = bool(self.settings.get("rpa.confirmar_automaticamente", True))
        self._chk_confirmar_auto.setChecked(confirmar_padrao)
        self._chk_confirmar_auto.stateChanged.connect(self._on_toggle_confirmar_auto)
        acoes.addWidget(self._chk_confirmar_auto)

        acoes.addStretch(1)

        self._btn_cancelar = QPushButton("Cancelar execução")
        self._btn_cancelar.setProperty("danger", True)
        self._btn_cancelar.setVisible(False)
        self._btn_cancelar.clicked.connect(self._cancelar)
        acoes.addWidget(self._btn_cancelar)

        self._btn_executar = QPushButton("Executar no TOTVS")
        self._btn_executar.setProperty("primary", True)
        self._btn_executar.setEnabled(False)
        self._btn_executar.clicked.connect(self._executar)
        acoes.addWidget(self._btn_executar)
        layout.addLayout(acoes)

        return card

    def _card_log(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(8)

        cab = QHBoxLayout()
        titulo = QLabel("Log")
        titulo.setProperty("h2", True)
        cab.addWidget(titulo)
        cab.addStretch(1)
        btn_limpar = QPushButton("Limpar")
        btn_limpar.clicked.connect(lambda: self._log.clear())
        cab.addWidget(btn_limpar)
        layout.addLayout(cab)

        self._log = QPlainTextEdit()
        self._log.setObjectName("LogConsole")
        self._log.setReadOnly(True)
        self._log.setFixedHeight(140)
        layout.addWidget(self._log)

        return card

    def _label_campo(self, texto: str) -> QLabel:
        lb = QLabel(texto)
        lb.setProperty("muted", True)
        return lb

    # ---------------- Setup ----------------

    def _verificar_setup(self) -> None:
        if not self.settings.get("gemini_api_key"):
            self._abrir_setup(inicial=True)

    def _abrir_setup(self, inicial: bool = False) -> None:
        dlg = SetupDialog(self, current_key=self.settings.get("gemini_api_key", ""))
        dlg.setStyleSheet(QSS)
        if dlg.exec():
            self.settings.set("gemini_api_key", dlg.chave())
            self._log_line("✓ Chave da API Gemini salva")
        elif inicial:
            self._log_line("⚠ Sem chave configurada — extração ficará indisponível")

    # ---------------- Ações ----------------

    def _trocar_secao(self, chave: str) -> None:
        for k, btn in self._nav_buttons.items():
            btn.setProperty("active", k == chave)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        if chave == "configuracoes":
            self._abrir_setup()
        elif chave == "mapeamento":
            QMessageBox.information(
                self, "De-Para",
                f"O de-para está em:\n{self.mapping_path}\n\n"
                "Edite o arquivo JSON e use 'Recarregar' abaixo.",
            )

    def _selecionar_arquivo(self) -> None:
        ultimo = self.settings.get("ultima_pasta_upload", "") or str(Path.home())
        arquivo, _ = QFileDialog.getOpenFileName(
            self, "Selecionar documento",
            ultimo,
            "Documentos (*.pdf *.png *.jpg *.jpeg *.webp)",
        )
        if not arquivo:
            return
        p = Path(arquivo)
        self._arquivo_selecionado = p
        self.settings.set("ultima_pasta_upload", str(p.parent))
        self._label_arquivo.setText(p.name)
        self._log_line(f"→ Arquivo selecionado: {p.name}")

    def _imposto_atual(self) -> Imposto:
        return self.mapping.imposto(self._combo_imposto.currentText())

    def _extrair(self) -> None:
        if self._arquivo_selecionado is None:
            QMessageBox.warning(self, "Atenção", "Selecione um documento primeiro.")
            return
        api_key = self.settings.get("gemini_api_key", "")
        if not api_key:
            QMessageBox.warning(self, "Chave ausente", "Configure a chave da API Gemini antes de continuar.")
            self._abrir_setup(inicial=False)
            return

        self._btn_extrair.setEnabled(False)
        self._label_resumo.setText("Extraindo…")

        qd = self._date_emissao.date().toPython()
        emissao = date(qd.year, qd.month, qd.day)

        worker = ExtracaoWorker(
            arquivo=self._arquivo_selecionado,
            api_key=api_key,
            modelo=self.settings.get("gemini_model", "gemini-2.0-flash-exp"),
            imposto=self._imposto_atual(),
            mapping=self.mapping,
            data_emissao=emissao,
        )
        worker.log_line.connect(self._log_line)
        worker.finished.connect(self._on_extraido)
        worker.error.connect(self._on_erro_extracao)

        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker_extracao = worker
        thread.start()

    def _on_extraido(self, lancamentos: list, nao_resolvidas: list) -> None:
        self._btn_extrair.setEnabled(True)
        self._lancamentos = lancamentos
        self._tabela.carregar(lancamentos)
        total_valor = sum(l.valor for l in lancamentos)
        valor_fmt = f"{total_valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        self._label_resumo.setText(
            f"{len(lancamentos)} lançamentos · R$ {valor_fmt}"
            + (f"  ·  ⚠ {len(nao_resolvidas)} não resolvidas" if nao_resolvidas else "")
        )
        self._btn_executar.setEnabled(bool(lancamentos))

    def _on_erro_extracao(self, msg: str) -> None:
        self._btn_extrair.setEnabled(True)
        self._label_resumo.setText("Falha na extração")
        QMessageBox.critical(self, "Erro na extração", msg)

    def _executar(self) -> None:
        if not self._lancamentos:
            return
        resp = QMessageBox.question(
            self, "Confirmar execução",
            f"{len(self._lancamentos)} lançamentos serão lançados no TOTVS.\n\n"
            "A tela 'Inclusão de Títulos' precisa estar aberta e em branco.\n"
            "Não use o mouse ou teclado durante a execução.\n\nContinuar?",
        )
        if resp != QMessageBox.Yes:
            return

        self._btn_executar.setEnabled(False)
        self._btn_extrair.setEnabled(False)
        self._btn_cancelar.setVisible(True)
        self._progress.setVisible(True)
        self._progress.setMaximum(len(self._lancamentos))
        self._progress.setValue(0)

        worker = LoteWorker(self._lancamentos, self.settings.data)
        worker.log_line.connect(self._log_line)
        worker.progresso.connect(self._on_progresso)
        worker.lancamento_atualizado.connect(self._tabela.atualizar_linha)
        worker.pedir_confirmacao_manual.connect(self._on_pedir_confirmacao_manual)
        worker.finished.connect(self._on_lote_finalizado)
        worker.error.connect(self._on_erro_lote)

        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker_lote = worker
        thread.start()

    def _on_progresso(self, i: int, total: int, msg: str) -> None:
        self._progress.setValue(i + 1)
        self._progress.setFormat(f"{i + 1}/{total} · {msg}")

    def _on_lote_finalizado(self, sucessos: int, falhas: int) -> None:
        self._btn_executar.setEnabled(True)
        self._btn_extrair.setEnabled(True)
        self._btn_cancelar.setVisible(False)
        self._progress.setVisible(False)
        self._log_line(f"■ Lote finalizado: {sucessos} sucessos, {falhas} falhas")
        QMessageBox.information(
            self, "Lote finalizado",
            f"Sucessos: {sucessos}\nFalhas: {falhas}",
        )

    def _on_erro_lote(self, msg: str) -> None:
        self._btn_executar.setEnabled(True)
        self._btn_extrair.setEnabled(True)
        self._btn_cancelar.setVisible(False)
        self._progress.setVisible(False)
        QMessageBox.critical(self, "Erro no lote", msg)

    def _cancelar(self) -> None:
        if self._worker_lote:
            self._worker_lote.cancelar()
            self._log_line("⏹ Cancelamento solicitado…")

    def _on_toggle_confirmar_auto(self, state: int) -> None:
        ativo = bool(state)
        self.settings.set("rpa.confirmar_automaticamente", ativo)
        self._log_line(
            "✓ Confirmação automática ativada — robô aperta + sozinho"
            if ativo else
            "✎ Modo revisão manual — robô vai parar antes do + e esperar você"
        )

    def _on_pedir_confirmacao_manual(self, index: int, resumo: str) -> None:
        """Chamado quando o worker termina de preencher e espera o operador."""
        if not self._worker_lote:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Revisão manual — confirme no TOTVS")
        box.setIcon(QMessageBox.Question)
        box.setText(
            f"Lançamento preenchido:\n\n{resumo}\n\n"
            "Confira os campos no TOTVS e aperte o + para gravar.\n"
            "Depois escolha:"
        )
        btn_continuar = box.addButton("Próximo lançamento", QMessageBox.AcceptRole)
        btn_parar = box.addButton("Parar lote", QMessageBox.RejectRole)
        box.setDefaultButton(btn_continuar)
        box.exec()
        prosseguir = box.clickedButton() is btn_continuar
        self._worker_lote.responder_confirmacao(prosseguir)

    def _log_line(self, msg: str) -> None:
        from datetime import datetime
        self._log.appendPlainText(f"[{datetime.now():%H:%M:%S}] {msg}")
        log.info(msg)
