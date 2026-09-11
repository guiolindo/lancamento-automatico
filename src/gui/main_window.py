from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QThread
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QSizePolicy, QSpacerItem, QVBoxLayout, QWidget
)

from ..core import calibracao as calib_store
from ..core.logger import log
from ..core.mapping import MappingRepository
from ..core.models import Imposto, Lancamento
from ..core.settings_store import SettingsStore
from .calibracao_dialog import CalibracaoDialog
from .depara_dialog import DeParaDialog
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
        self.resize(1280, 820)
        self.setMinimumSize(1080, 680)
        self.setStyleSheet(QSS)

        self._thread: QThread | None = None
        self._worker_extracao: ExtracaoWorker | None = None
        self._worker_lote: LoteWorker | None = None
        self._arquivo_selecionado: Path | None = None
        self._lancamentos: list[Lancamento] = []
        self._calibracao = calib_store.carregar()

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
        side.setFixedWidth(224)
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
        # marca primeiro como ativo
        self._nav_buttons["dashboard"].setProperty("active", True)

        v.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # Status calibração
        self._lbl_status_calib = QLabel()
        self._lbl_status_calib.setProperty("muted", True)
        self._lbl_status_calib.setContentsMargins(20, 8, 20, 4)
        self._lbl_status_calib.setWordWrap(True)
        v.addWidget(self._lbl_status_calib)
        self._atualizar_status_calibracao()

        rodape = QLabel("v0.1.0  ·  build 35")
        rodape.setProperty("muted", True)
        rodape.setContentsMargins(20, 0, 20, 0)
        v.addWidget(rodape)

        return side

    def _montar_content(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("Content")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(28, 24, 28, 20)
        v.setSpacing(16)

        # ---- Header: título + KPIs
        v.addLayout(self._header_kpis())

        # ---- Barra fina de parâmetros
        v.addWidget(self._toolbar_parametros())

        # ---- Tabela dominante (stretch=1)
        v.addWidget(self._card_preview(), 1)

        # ---- Log rodapé compacto
        v.addWidget(self._card_log())

        return wrap

    # ---------------- Header + KPIs ----------------

    def _header_kpis(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)

        col = QVBoxLayout()
        col.setSpacing(2)
        titulo = QLabel("Novo lote de lançamentos")
        titulo.setProperty("h1", True)
        col.addWidget(titulo)
        sub = QLabel("Envie o resumo do imposto, revise os lançamentos gerados e execute no TOTVS.")
        sub.setProperty("muted", True)
        col.addWidget(sub)
        row.addLayout(col, 1)

        self._kpi_qtd, kpi_qtd_card = self._kpi_card("Lançamentos", "0")
        self._kpi_valor, kpi_valor_card = self._kpi_card("Valor total (R$)", "0,00")
        row.addWidget(kpi_qtd_card)
        row.addWidget(kpi_valor_card)
        return row

    def _kpi_card(self, rotulo: str, valor: str) -> tuple[QLabel, QFrame]:
        card = QFrame()
        card.setProperty("kpi", True)
        card.setMinimumWidth(180)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(2)
        lb_rot = QLabel(rotulo)
        lb_rot.setProperty("muted", True)
        lay.addWidget(lb_rot)
        lb_val = QLabel(valor)
        lb_val.setProperty("kpiValue", True)
        lay.addWidget(lb_val)
        return lb_val, card

    # ---------------- Toolbar parâmetros ----------------

    def _toolbar_parametros(self) -> QFrame:
        bar = QFrame()
        bar.setProperty("toolbar", True)
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(14)

        # Imposto
        row.addWidget(self._campo_inline("Imposto"))
        self._combo_imposto = QComboBox()
        self._combo_imposto.addItem("IRRF")
        self._combo_imposto.setFixedWidth(120)
        row.addWidget(self._combo_imposto)

        row.addWidget(self._divisor_vertical())

        # Data
        row.addWidget(self._campo_inline("Data"))
        self._date_emissao = QDateEdit(QDate.currentDate())
        self._date_emissao.setDisplayFormat("dd/MM/yyyy")
        self._date_emissao.setCalendarPopup(True)
        self._date_emissao.setFixedWidth(140)
        row.addWidget(self._date_emissao)

        row.addWidget(self._divisor_vertical())

        # Arquivo
        row.addWidget(self._campo_inline("Documento"))
        self._label_arquivo = QLabel("Nenhum arquivo selecionado")
        self._label_arquivo.setProperty("muted", True)
        self._label_arquivo.setMinimumWidth(200)
        row.addWidget(self._label_arquivo, 1)
        btn_pick = QPushButton("Selecionar…")
        btn_pick.clicked.connect(self._selecionar_arquivo)
        row.addWidget(btn_pick)

        # Extrair (primário à direita)
        self._btn_extrair = QPushButton("Extrair com Gemini")
        self._btn_extrair.setProperty("primary", True)
        self._btn_extrair.clicked.connect(self._extrair)
        row.addWidget(self._btn_extrair)

        return bar

    def _campo_inline(self, texto: str) -> QLabel:
        lb = QLabel(texto)
        lb.setProperty("muted", True)
        lb.setProperty("inlineLabel", True)
        return lb

    def _divisor_vertical(self) -> QFrame:
        div = QFrame()
        div.setObjectName("Divisor")
        div.setFixedSize(1, 24)
        return div

    # ---------------- Preview (a tabela) ----------------

    def _card_preview(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # cabeçalho interno
        cab = QHBoxLayout()
        cab.setContentsMargins(20, 14, 20, 12)
        cab.setSpacing(10)
        titulo = QLabel("Revisão dos lançamentos")
        titulo.setProperty("h2", True)
        cab.addWidget(titulo)

        self._label_status_revisao = QLabel("Aguardando extração")
        self._label_status_revisao.setProperty("badge", "pendente")
        cab.addWidget(self._label_status_revisao)

        cab.addStretch(1)

        self._chk_confirmar_auto = QCheckBox(
            "Confirmar '+' automaticamente"
        )
        confirmar_padrao = bool(self.settings.get("rpa.confirmar_automaticamente", True))
        self._chk_confirmar_auto.setChecked(confirmar_padrao)
        self._chk_confirmar_auto.stateChanged.connect(self._on_toggle_confirmar_auto)
        cab.addWidget(self._chk_confirmar_auto)

        self._chk_apenas_primeiro = QCheckBox("Testar só o 1º")
        self._chk_apenas_primeiro.setChecked(True)
        self._chk_apenas_primeiro.setToolTip(
            "Executa apenas o primeiro lançamento — ideal pra validar calibração."
        )
        cab.addWidget(self._chk_apenas_primeiro)

        layout.addLayout(cab)

        # separador horizontal
        sep = QFrame()
        sep.setObjectName("DivisorH")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # tabela — coração do produto, ocupa tudo
        self._tabela = PreviewTable()
        self._tabela.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._tabela, 1)

        # rodapé de ações
        rodape_wrap = QFrame()
        rodape_wrap.setProperty("cardFooter", True)
        rodape = QHBoxLayout(rodape_wrap)
        rodape.setContentsMargins(20, 12, 20, 14)
        rodape.setSpacing(10)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setMinimumWidth(240)
        rodape.addWidget(self._progress, 1)

        rodape.addStretch(1)

        self._btn_calibrar = QPushButton("Recalibrar (opcional)")
        self._btn_calibrar.setToolTip(
            "O app detecta as posições automaticamente por visão computacional. "
            "Use isso só se o auto-detect falhar (versão nova do TOTVS, layout muito diferente)."
        )
        self._btn_calibrar.clicked.connect(self._abrir_calibracao)
        rodape.addWidget(self._btn_calibrar)

        self._btn_cancelar = QPushButton("Cancelar execução")
        self._btn_cancelar.setProperty("danger", True)
        self._btn_cancelar.setVisible(False)
        self._btn_cancelar.clicked.connect(self._cancelar)
        rodape.addWidget(self._btn_cancelar)

        self._btn_executar = QPushButton("▶  Executar no TOTVS")
        self._btn_executar.setProperty("primary", True)
        self._btn_executar.setEnabled(False)
        self._btn_executar.setMinimumWidth(200)
        self._btn_executar.clicked.connect(self._executar)
        rodape.addWidget(self._btn_executar)

        layout.addWidget(rodape_wrap)
        return card

    # ---------------- Log ----------------

    def _card_log(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        card.setFixedHeight(150)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 10, 20, 12)
        layout.setSpacing(6)

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
        layout.addWidget(self._log, 1)

        return card

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

    def _atualizar_status_calibracao(self) -> None:
        if self._calibracao.esta_completa():
            self._lbl_status_calib.setText("● Calibração manual salva")
            self._lbl_status_calib.setStyleSheet("color:#22C55E; font-size:11px;")
        else:
            self._lbl_status_calib.setText("● Detecção automática (visão)")
            self._lbl_status_calib.setStyleSheet("color:#3B82F6; font-size:11px;")

    # ---------------- Ações ----------------

    def _trocar_secao(self, chave: str) -> None:
        for k, btn in self._nav_buttons.items():
            btn.setProperty("active", k == chave)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        if chave == "configuracoes":
            self._abrir_setup()
        elif chave == "mapeamento":
            dlg = DeParaDialog(self.mapping, self.mapping_path, self)
            dlg.setStyleSheet(QSS)
            if dlg.exec():
                self._log_line("✓ De-Para atualizado e recarregado")

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
        self._label_arquivo.setProperty("muted", False)
        self._label_arquivo.style().unpolish(self._label_arquivo)
        self._label_arquivo.style().polish(self._label_arquivo)
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
        self._set_status_revisao("andamento", "Extraindo…")

        qd = self._date_emissao.date().toPython()
        emissao = date(qd.year, qd.month, qd.day)

        worker = ExtracaoWorker(
            arquivo=self._arquivo_selecionado,
            api_key=api_key,
            modelo=self.settings.get("gemini_model", "gemini-3.5-flash-lite"),
            imposto=self._imposto_atual(),
            mapping=self.mapping,
            data_emissao=emissao,
        )
        worker.log_line.connect(self._log_line)
        worker.finished.connect(self._on_extraido)
        worker.error.connect(self._on_erro_extracao)

        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker_extracao = worker
        thread.start()

    def _set_status_revisao(self, badge: str, texto: str) -> None:
        self._label_status_revisao.setProperty("badge", badge)
        self._label_status_revisao.setText(texto)
        self._label_status_revisao.style().unpolish(self._label_status_revisao)
        self._label_status_revisao.style().polish(self._label_status_revisao)

    def _formatar_moeda(self, valor: float) -> str:
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _on_extraido(self, lancamentos: list, nao_resolvidas: list) -> None:
        self._btn_extrair.setEnabled(True)
        self._lancamentos = lancamentos
        self._tabela.carregar(lancamentos)
        total = sum(l.valor for l in lancamentos)
        self._kpi_qtd.setText(str(len(lancamentos)))
        self._kpi_valor.setText(self._formatar_moeda(total))
        if nao_resolvidas:
            self._set_status_revisao("falha", f"{len(nao_resolvidas)} filial(is) não resolvida(s)")
        else:
            self._set_status_revisao("sucesso", "Pronto para executar")
        self._btn_executar.setEnabled(bool(lancamentos))

    def _on_erro_extracao(self, msg: str) -> None:
        self._btn_extrair.setEnabled(True)
        self._set_status_revisao("falha", "Falha na extração")
        QMessageBox.critical(self, "Erro na extração", msg)

    def _abrir_calibracao(self) -> None:
        dlg = CalibracaoDialog(self._calibracao, self)
        dlg.setStyleSheet(QSS)
        if dlg.exec():
            self._calibracao = dlg.calibracao()
            calib_store.salvar(self._calibracao)
            self._log_line(
                f"OK Calibração salva ({len(self._calibracao.campos)} campos)"
            )
            self._atualizar_status_calibracao()

    def _set_topo(self, on: bool) -> None:
        """DESABILITADO — setWindowFlags reparenta o handle nativo e quebra
        o QThread que é iniciado logo depois."""
        pass

    def _executar(self) -> None:
        if not self._lancamentos:
            return
        # Não bloqueia mais por calibração incompleta — o worker tenta visão
        # computacional primeiro (auto-detect). Só cai na calibração manual
        # se a visão falhar E o operador não tiver calibrado nada antes.
        resp = QMessageBox.question(
            self, "Confirmar execução",
            f"{len(self._lancamentos)} lançamentos serão lançados no TOTVS.\n\n"
            "A tela 'Inclusão de Títulos' precisa estar aberta e em branco.\n"
            "Não use o mouse ou teclado durante a execução.\n\n"
            "🛑 Parada de emergência: aperte a tecla END a qualquer momento.\n"
            "🛑 Também funciona: arrastar o mouse pro CANTO SUPERIOR ESQUERDO da tela.\n\n"
            "Continuar?",
        )
        if resp != QMessageBox.Yes:
            return

        self._btn_executar.setEnabled(False)
        self._btn_extrair.setEnabled(False)
        self._btn_cancelar.setVisible(True)
        self._progress.setVisible(True)
        self._set_status_revisao("andamento", "Executando…")
        self._log_line(">> INICIANDO EXECUCAO NO TOTVS (build 35) — END = emergencia")

        lancamentos_exec = self._lancamentos
        if self._chk_apenas_primeiro.isChecked() and lancamentos_exec:
            lancamentos_exec = [lancamentos_exec[0]]
            self._log_line(
                f"i Modo teste: apenas o 1o lançamento ({lancamentos_exec[0].filial_nome} / "
                f"{lancamentos_exec[0].tipo_folha})"
            )

        self._progress.setMaximum(len(lancamentos_exec))
        self._progress.setValue(0)

        log.info("_executar: criando LoteWorker")
        worker = LoteWorker(lancamentos_exec, self.settings.data, self._calibracao)
        worker.log_line.connect(self._log_line)
        worker.progresso.connect(self._on_progresso)
        worker.lancamento_atualizado.connect(self._tabela.atualizar_linha)
        worker.pedir_confirmacao_manual.connect(self._on_pedir_confirmacao_manual)
        worker.finished.connect(self._on_lote_finalizado)
        worker.error.connect(self._on_erro_lote)

        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        thread.started.connect(lambda: log.info("QThread.started fired"))
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
        if falhas == 0:
            self._set_status_revisao("sucesso", f"{sucessos} lançados")
        else:
            self._set_status_revisao("falha", f"{sucessos} ok · {falhas} falha(s)")
        self._log_line(f"# Lote finalizado: {sucessos} sucessos, {falhas} falhas")
        QMessageBox.information(
            self, "Lote finalizado",
            f"Sucessos: {sucessos}\nFalhas: {falhas}",
        )

    def _on_erro_lote(self, msg: str) -> None:
        self._btn_executar.setEnabled(True)
        self._btn_extrair.setEnabled(True)
        self._btn_cancelar.setVisible(False)
        self._progress.setVisible(False)
        self._set_status_revisao("falha", "Erro no lote")
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
