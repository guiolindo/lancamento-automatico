from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QDate, QSize, Qt, QThread
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSpacerItem,
    QVBoxLayout, QWidget
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
from .theme import qss
from .updater_bar import UpdaterBar
from .workers import ExtracaoWorker, LoteWorker


# Cada item de nav: (chave, ícone Unicode, tooltip)
NAV_ITEMS = [
    ("dashboard",     "📊", "Novo Lote"),
    ("mapeamento",    "🏢", "Filiais (De-Para)"),
    ("configuracoes", "⚙",  "Configurações"),
]

NOME_SECAO = {
    "dashboard":     "Novo Lote",
    "mapeamento":    "Filiais (De-Para)",
    "configuracoes": "Configurações",
}


class MainWindow(QMainWindow):
    def __init__(self, settings: SettingsStore, mapping: MappingRepository, mapping_path: Path):
        super().__init__()
        self.settings = settings
        self.mapping = mapping
        self.mapping_path = mapping_path
        self.setWindowTitle("Lançamento Automático — TOTVS")
        self.resize(1320, 840)
        self.setMinimumSize(1040, 680)
        self._tema = self.settings.get("tema", "escuro") or "escuro"
        self.setStyleSheet(qss(self._tema))

        self._thread: QThread | None = None
        self._worker_extracao: ExtracaoWorker | None = None
        self._worker_lote: LoteWorker | None = None
        self._arquivo_selecionado: Path | None = None
        self._lancamentos: list[Lancamento] = []
        self._calibracao = calib_store.carregar()
        self._eventos: list[str] = []

        self._montar_ui()
        self._verificar_setup()

    # ---------------- UI ----------------

    def _buscar_asset(self, relativo: str) -> Path | None:
        import sys
        candidatos = [
            Path(__file__).resolve().parent.parent / "assets" / relativo,
            Path(sys.executable).resolve().parent / "src" / "assets" / relativo,
            Path(sys.executable).resolve().parent / "assets" / relativo,
        ]
        for c in candidatos:
            if c.exists():
                return c
        return None

    def _montar_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._montar_sidebar())
        root.addWidget(self._montar_shell(), 1)

    # -------- Sidebar fina (só ícones) --------

    def _montar_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(64)
        v = QVBoxLayout(side)
        v.setContentsMargins(0, 0, 0, 12)
        v.setSpacing(0)

        # Logo Economart pequena no topo
        logo_path = self._buscar_asset("branding/logo_simbolo.png")
        if logo_path:
            logo = QLabel()
            logo.setObjectName("SidebarLogo")
            pm = QPixmap(str(logo_path))
            logo.setPixmap(pm.scaled(36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            logo.setAlignment(Qt.AlignCenter)
            v.addWidget(logo)

        # Ícones de nav
        self._nav_buttons: dict[str, QPushButton] = {}
        for key, icon, tip in NAV_ITEMS:
            btn = QPushButton(icon)
            btn.setProperty("navIcon", True)
            btn.setToolTip(tip)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._trocar_secao(k))
            self._nav_buttons[key] = btn
            v.addWidget(btn)

        self._nav_buttons["dashboard"].setProperty("active", True)
        v.addStretch(1)

        # Toggle de tema pequeno no rodapé
        self._btn_tema = QPushButton()
        self._btn_tema.setProperty("navIcon", True)
        self._btn_tema.setCursor(Qt.PointingHandCursor)
        self._btn_tema.clicked.connect(self._toggle_tema)
        self._atualizar_texto_tema()
        v.addWidget(self._btn_tema)

        return side

    def _atualizar_texto_tema(self) -> None:
        if self._tema == "claro":
            self._btn_tema.setText("🌙")
            self._btn_tema.setToolTip("Mudar pra modo escuro")
        else:
            self._btn_tema.setText("☀")
            self._btn_tema.setToolTip("Mudar pra modo claro")

    def _toggle_tema(self) -> None:
        self._tema = "claro" if self._tema == "escuro" else "escuro"
        self.settings.set("tema", self._tema)
        self.setStyleSheet(qss(self._tema))
        self._atualizar_texto_tema()

    # -------- Shell: topbar + content --------

    def _montar_shell(self) -> QWidget:
        shell = QWidget()
        lay = QVBoxLayout(shell)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Barra de atualização (escondida por padrão, aparece no topo
        # quando o operador clica Atualizar)
        self._updater_bar = UpdaterBar()
        lay.addWidget(self._updater_bar)

        lay.addWidget(self._montar_topbar())
        lay.addWidget(self._montar_content(), 1)

        return shell

    def _montar_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("Topbar")
        bar.setFixedHeight(56)
        h = QHBoxLayout(bar)
        h.setContentsMargins(28, 0, 28, 0)
        h.setSpacing(8)

        # Breadcrumb: Home › Novo Lote
        lb_home = QLabel("Início")
        lb_home.setProperty("breadcrumb", True)
        h.addWidget(lb_home)

        lb_sep = QLabel("›")
        lb_sep.setProperty("breadcrumb", True)
        h.addWidget(lb_sep)

        self._lb_secao = QLabel(NOME_SECAO["dashboard"])
        self._lb_secao.setProperty("breadcrumbActive", True)
        h.addWidget(self._lb_secao)

        h.addStretch(1)

        # Ações rápidas do topbar
        self._lbl_status_calib_top = QLabel()
        self._lbl_status_calib_top.setProperty("muted", True)
        h.addWidget(self._lbl_status_calib_top)
        self._atualizar_status_calibracao()

        self._btn_atualizar = QPushButton("Atualizar")
        self._btn_atualizar.setProperty("ghost", True)
        self._btn_atualizar.setToolTip("Verificar se há uma versão nova no GitHub")
        self._btn_atualizar.setCursor(Qt.PointingHandCursor)
        self._btn_atualizar.clicked.connect(self._verificar_atualizacao)
        h.addWidget(self._btn_atualizar)

        return bar

    # -------- Content --------

    def _montar_content(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("Content")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(20)

        # Título de página
        titulo_wrap = QVBoxLayout()
        titulo_wrap.setSpacing(4)
        kicker = QLabel("AUTOMAÇÃO FISCAL")
        kicker.setProperty("sectionKicker", True)
        titulo_wrap.addWidget(kicker)
        titulo = QLabel("Novo lote de lançamentos")
        titulo.setProperty("h1", True)
        titulo_wrap.addWidget(titulo)
        sub = QLabel("Extraia, revise e execute os lançamentos no TOTVS em um só fluxo.")
        sub.setProperty("subtle", True)
        titulo_wrap.addWidget(sub)
        v.addLayout(titulo_wrap)

        # Grid de KPIs (4 cards)
        v.addWidget(self._grid_kpis())

        # Área principal em 2 colunas: Novo Lote (grande) + Atividade
        col2 = QHBoxLayout()
        col2.setSpacing(16)
        col2.addWidget(self._card_novo_lote(), 3)
        col2.addWidget(self._card_atividade(), 1)
        v.addLayout(col2, 1)

        return wrap

    # -------- KPIs --------

    def _grid_kpis(self) -> QWidget:
        wrap = QWidget()
        grid = QGridLayout(wrap)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(14)

        self._kpi_qtd, k1 = self._kpi_card("Lançamentos", "0", "Preparados nesta sessão", highlight=True)
        self._kpi_valor, k2 = self._kpi_card("Valor total", "R$ 0,00", "Soma do lote atual")
        self._kpi_calibr, k3 = self._kpi_card("Detecção", "Visão auto", "Sem calibração manual")
        self._kpi_ultima, k4 = self._kpi_card("Última execução", "—", "Aguardando primeiro lote")

        for i, k in enumerate([k1, k2, k3, k4]):
            grid.addWidget(k, 0, i)
            grid.setColumnStretch(i, 1)
        return wrap

    def _kpi_card(self, rotulo: str, valor: str, hint: str, highlight: bool = False) -> tuple[QLabel, QFrame]:
        card = QFrame()
        card.setProperty("kpi", True)
        if highlight:
            card.setProperty("highlight", True)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(4)

        lb_rot = QLabel(rotulo)
        lb_rot.setProperty("kpiLabel", True)
        lay.addWidget(lb_rot)

        lb_val = QLabel(valor)
        lb_val.setProperty("kpiValueOrange" if highlight else "kpiValue", True)
        lay.addWidget(lb_val)

        lb_hint = QLabel(hint)
        lb_hint.setProperty("kpiHint", True)
        lay.addWidget(lb_hint)
        return lb_val, card

    # -------- Card 'Novo Lote' (form + tabela + ações) --------

    def _card_novo_lote(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        v = QVBoxLayout(card)
        v.setContentsMargins(24, 22, 24, 20)
        v.setSpacing(18)

        # Header interno
        head = QHBoxLayout()
        head.setSpacing(10)
        h2 = QLabel("Fluxo do lote")
        h2.setProperty("h2", True)
        head.addWidget(h2)

        self._label_status_revisao = QLabel("Aguardando documento")
        self._label_status_revisao.setProperty("badge", "pendente")
        head.addWidget(self._label_status_revisao)

        head.addStretch(1)

        self._chk_apenas_primeiro = QCheckBox("Testar só o 1º")
        self._chk_apenas_primeiro.setChecked(False)
        self._chk_apenas_primeiro.setToolTip(
            "Executa só o primeiro lançamento — pra validar antes do lote inteiro."
        )
        head.addWidget(self._chk_apenas_primeiro)

        self._chk_confirmar_auto = QCheckBox("Confirmar '+' automático")
        confirmar_padrao = bool(self.settings.get("rpa.confirmar_automaticamente", True))
        self._chk_confirmar_auto.setChecked(confirmar_padrao)
        self._chk_confirmar_auto.stateChanged.connect(self._on_toggle_confirmar_auto)
        head.addWidget(self._chk_confirmar_auto)

        v.addLayout(head)

        # STEP 1: Documento e parâmetros
        v.addWidget(self._step_titulo(1, "Selecione o documento"))
        v.addLayout(self._linha_documento())

        # STEP 2: Tabela de revisão
        v.addWidget(self._step_titulo(2, "Revise os lançamentos"))
        self._tabela = PreviewTable()
        self._tabela.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._tabela.setMinimumHeight(220)
        v.addWidget(self._tabela, 1)

        # STEP 3: Executar
        v.addWidget(self._step_titulo(3, "Execute no TOTVS"))
        rodape = QHBoxLayout()
        rodape.setSpacing(10)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setMinimumWidth(180)
        rodape.addWidget(self._progress, 1)
        rodape.addStretch(1)

        self._btn_calibrar = QPushButton("Recalibrar")
        self._btn_calibrar.setProperty("ghost", True)
        self._btn_calibrar.setToolTip(
            "Só se o auto-detect falhar (versão nova do TOTVS)."
        )
        self._btn_calibrar.clicked.connect(self._abrir_calibracao)
        rodape.addWidget(self._btn_calibrar)

        self._btn_cancelar = QPushButton("Cancelar")
        self._btn_cancelar.setProperty("danger", True)
        self._btn_cancelar.setVisible(False)
        self._btn_cancelar.clicked.connect(self._cancelar)
        rodape.addWidget(self._btn_cancelar)

        self._btn_executar = QPushButton("▶  Executar no TOTVS")
        self._btn_executar.setProperty("brand", True)
        self._btn_executar.setMinimumWidth(220)
        self._btn_executar.setEnabled(False)
        self._btn_executar.clicked.connect(self._executar)
        rodape.addWidget(self._btn_executar)

        v.addLayout(rodape)
        return card

    def _step_titulo(self, numero: int, texto: str) -> QWidget:
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        num = QLabel(str(numero))
        num.setProperty("stepNum", True)
        num.setFixedWidth(26)
        h.addWidget(num)
        lb = QLabel(texto)
        lb.setProperty("h3", True)
        h.addWidget(lb)
        h.addStretch(1)
        return wrap

    def _linha_documento(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        # Imposto
        col_imp = QVBoxLayout()
        col_imp.setSpacing(4)
        col_imp.addWidget(self._campo_inline("Imposto"))
        self._combo_imposto = QComboBox()
        self._combo_imposto.addItem("IRRF")
        self._combo_imposto.setMinimumWidth(140)
        col_imp.addWidget(self._combo_imposto)
        row.addLayout(col_imp)

        # Data
        col_data = QVBoxLayout()
        col_data.setSpacing(4)
        col_data.addWidget(self._campo_inline("Data de referência"))
        self._date_emissao = QDateEdit(QDate.currentDate())
        self._date_emissao.setDisplayFormat("dd/MM/yyyy")
        self._date_emissao.setCalendarPopup(True)
        self._date_emissao.setMinimumWidth(150)
        col_data.addWidget(self._date_emissao)
        row.addLayout(col_data)

        # Arquivo
        col_arq = QVBoxLayout()
        col_arq.setSpacing(4)
        col_arq.addWidget(self._campo_inline("Documento (PDF ou imagem)"))
        arq_row = QHBoxLayout()
        arq_row.setSpacing(8)
        self._label_arquivo = QLabel("Nenhum arquivo selecionado")
        self._label_arquivo.setProperty("muted", True)
        self._label_arquivo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._label_arquivo.setMinimumWidth(80)
        arq_row.addWidget(self._label_arquivo, 1)
        btn_pick = QPushButton("Selecionar…")
        btn_pick.setMinimumWidth(110)
        btn_pick.clicked.connect(self._selecionar_arquivo)
        arq_row.addWidget(btn_pick)
        col_arq.addLayout(arq_row)
        row.addLayout(col_arq, 1)

        # Extrair (primário azul)
        col_btn = QVBoxLayout()
        col_btn.setSpacing(4)
        col_btn.addWidget(QLabel(""))  # spacer p/ alinhar com label acima
        self._btn_extrair = QPushButton("Extrair com Gemini")
        self._btn_extrair.setProperty("primary", True)
        self._btn_extrair.setMinimumWidth(200)
        self._btn_extrair.clicked.connect(self._extrair)
        col_btn.addWidget(self._btn_extrair)
        row.addLayout(col_btn)

        return row

    def _campo_inline(self, texto: str) -> QLabel:
        lb = QLabel(texto)
        lb.setProperty("inlineLabel", True)
        return lb

    # -------- Card 'Atividade' (log) --------

    def _card_atividade(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        card.setMinimumWidth(280)
        card.setMaximumWidth(360)
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 22, 20, 20)
        v.setSpacing(12)

        cab = QHBoxLayout()
        h2 = QLabel("Atividade")
        h2.setProperty("h2", True)
        cab.addWidget(h2)
        cab.addStretch(1)
        btn_limpar = QPushButton("Limpar")
        btn_limpar.setProperty("iconOnly", True)
        btn_limpar.setText("×")
        btn_limpar.setToolTip("Limpar log")
        btn_limpar.clicked.connect(lambda: (self._log.clear(), self._eventos.clear()))
        cab.addWidget(btn_limpar)
        v.addLayout(cab)

        self._log = QPlainTextEdit()
        self._log.setObjectName("LogConsole")
        self._log.setReadOnly(True)
        v.addWidget(self._log, 1)

        return card

    # ---------------- Setup ----------------

    def _verificar_setup(self) -> None:
        if not self.settings.get("gemini_api_key"):
            self._abrir_setup(inicial=True)
        # Check de atualização automático no boot — 2s depois pra dar tempo
        # da janela renderizar antes do modal aparecer.
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, self._check_atualizacao_boot)

    def _check_atualizacao_boot(self) -> None:
        """Verifica update no boot em background. Se tem, dispara modal
        obrigatório (só botão Sim — sem escapatória)."""
        import threading
        from ..core import updater
        from ..main import BUILD_MARKER

        def worker():
            info = updater.check(BUILD_MARKER)
            if info and info.tem_atualizacao:
                # Volta pro main thread pra mostrar o modal
                from PySide6.QtCore import QMetaObject, Qt as _Qt
                # Invoca via slot (setter em property funciona bem pra passar dado
                # simples). Simpler: usar singleShot com closure.
                from PySide6.QtCore import QTimer as _QT
                _QT.singleShot(0, lambda: self._modal_obrigatorio(info))

        threading.Thread(target=worker, daemon=True).start()

    def _modal_obrigatorio(self, info) -> None:
        """Mostra modal 'Nova versão disponível — Sim, atualizar' sem
        botão de dispensar. Único jeito de sair sem atualizar é fechar
        a janela do Windows (X). Toda vez que abrir volta o aviso."""
        tam_mb = info.asset_tamanho / (1024 * 1024)
        box = QMessageBox(self)
        box.setWindowTitle("Atualização obrigatória")
        box.setIcon(QMessageBox.Warning)
        box.setText(
            "<b>Nova versão do app disponível.</b><br><br>"
            f"Atual: <code>{info.build_marker_local}</code><br>"
            f"Nova:  <code>{info.build_marker_remoto}</code><br><br>"
            "Atualizações podem trazer <b>filial nova, imposto novo ou "
            "correção crítica</b>. Esse tipo de app não pode ficar "
            "desatualizado.<br><br>"
            f"O download tem {tam_mb:.1f} MB e roda em segundo plano — "
            "você continua trabalhando enquanto baixa. Depois o app "
            "aplica sozinho na próxima abertura."
        )
        botao_sim = box.addButton("Sim, atualizar agora", QMessageBox.AcceptRole)
        box.setDefaultButton(botao_sim)
        # Nada de Cancel/Depois — só sai fechando pelo X.
        box.exec()
        if box.clickedButton() is botao_sim:
            self._log_line(f"→ Baixando atualização {info.build_marker_remoto}…")
            self._updater_bar.iniciar(info)

    def _abrir_setup(self, inicial: bool = False) -> None:
        dlg = SetupDialog(self, current_key=self.settings.get("gemini_api_key", ""))
        dlg.setStyleSheet(qss(self._tema))
        if dlg.exec():
            self.settings.set("gemini_api_key", dlg.chave())
            self._log_line("✓ Chave da API Gemini salva")
        elif inicial:
            self._log_line("⚠ Sem chave configurada — extração ficará indisponível")

    def _atualizar_status_calibracao(self) -> None:
        if not hasattr(self, "_lbl_status_calib_top"):
            return
        if self._calibracao.esta_completa():
            self._lbl_status_calib_top.setText("● TOTVS calibração manual salva")
            self._lbl_status_calib_top.setStyleSheet("color:#22C55E; font-size:11px;")
        else:
            self._lbl_status_calib_top.setText("● Auto-detect visual ativo")
            self._lbl_status_calib_top.setStyleSheet("color:#FF6900; font-size:11px;")

    # ---------------- Ações ----------------

    def _trocar_secao(self, chave: str) -> None:
        for k, btn in self._nav_buttons.items():
            btn.setProperty("active", k == chave)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._lb_secao.setText(NOME_SECAO.get(chave, chave))
        if chave == "configuracoes":
            self._abrir_setup()
        elif chave == "mapeamento":
            dlg = DeParaDialog(self.mapping, self.mapping_path, self)
            dlg.setStyleSheet(qss(self._tema))
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
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _on_extraido(self, lancamentos: list, nao_resolvidas: list) -> None:
        self._btn_extrair.setEnabled(True)
        self._lancamentos = lancamentos
        self._tabela.carregar(lancamentos)
        total = sum(l.valor for l in lancamentos)
        self._kpi_qtd.setText(str(len(lancamentos)))
        self._kpi_valor.setText(self._formatar_moeda(total))
        if nao_resolvidas:
            self._set_status_revisao("falha", f"{len(nao_resolvidas)} filial(is) não resolvidas")
        else:
            self._set_status_revisao("sucesso", "Pronto pra executar")
        self._btn_executar.setEnabled(bool(lancamentos))

    def _on_erro_extracao(self, msg: str) -> None:
        self._btn_extrair.setEnabled(True)
        self._set_status_revisao("falha", "Falha na extração")
        QMessageBox.critical(self, "Erro na extração", msg)

    def _abrir_calibracao(self) -> None:
        dlg = CalibracaoDialog(self._calibracao, self)
        dlg.setStyleSheet(qss(self._tema))
        if dlg.exec():
            self._calibracao = dlg.calibracao()
            calib_store.salvar(self._calibracao)
            self._log_line(f"OK Calibração salva ({len(self._calibracao.campos)} campos)")
            self._atualizar_status_calibracao()

    def _executar(self) -> None:
        if not self._lancamentos:
            return
        resp = QMessageBox.question(
            self, "Confirmar execução",
            f"{len(self._lancamentos)} lançamentos serão lançados no TOTVS.\n\n"
            "A tela 'Inclusão de Títulos' precisa estar aberta e em branco.\n"
            "Não use mouse/teclado durante a execução.\n\n"
            "🛑 Emergência: tecla END a qualquer momento.\n\n"
            "Continuar?",
        )
        if resp != QMessageBox.Yes:
            return

        self._btn_executar.setEnabled(False)
        self._btn_extrair.setEnabled(False)
        self._btn_cancelar.setVisible(True)
        self._progress.setVisible(True)
        self._set_status_revisao("andamento", "Executando…")
        self._log_line(">> INICIANDO EXECUCAO — END = emergencia")

        lancamentos_exec = self._lancamentos
        if self._chk_apenas_primeiro.isChecked() and lancamentos_exec:
            lancamentos_exec = [lancamentos_exec[0]]
            self._log_line(
                f"i Modo teste: só o 1o ({lancamentos_exec[0].filial_nome} / "
                f"{lancamentos_exec[0].tipo_folha})"
            )

        self._progress.setMaximum(len(lancamentos_exec))
        self._progress.setValue(0)

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
        self._kpi_ultima.setText(datetime.now().strftime("%H:%M"))
        self._log_line(f"# Lote finalizado: {sucessos} sucessos, {falhas} falhas")
        QMessageBox.information(self, "Lote finalizado", f"Sucessos: {sucessos}\nFalhas: {falhas}")

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
            "✓ Confirmação automática ativada"
            if ativo else
            "✎ Modo revisão manual"
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
        box.addButton("Parar lote", QMessageBox.RejectRole)
        box.setDefaultButton(btn_continuar)
        box.exec()
        prosseguir = box.clickedButton() is btn_continuar
        self._worker_lote.responder_confirmacao(prosseguir)

    def _log_line(self, msg: str) -> None:
        self._log.appendPlainText(f"[{datetime.now():%H:%M:%S}] {msg}")
        log.info(msg)

    # ---------------- Atualizador ----------------

    def _verificar_atualizacao(self) -> None:
        """Consulta GitHub e oferece baixar se tem versão nova."""
        from ..core import updater
        from ..main import BUILD_MARKER
        self._btn_atualizar.setEnabled(False)
        self._btn_atualizar.setText("Verificando…")
        # Feito no main thread mesmo — request rápido (15s timeout)
        try:
            info = updater.check(BUILD_MARKER)
        finally:
            self._btn_atualizar.setEnabled(True)
            self._btn_atualizar.setText("Atualizar")

        if info is None:
            QMessageBox.information(
                self, "Atualização",
                "Não consegui consultar o GitHub agora — pode ser conexão ou "
                "ainda não tem release publicada.",
            )
            return
        if not info.tem_atualizacao:
            QMessageBox.information(
                self, "Atualização",
                f"Você já tá na versão mais recente.\n\nLocal: {info.build_marker_local}",
            )
            return

        # Tem update
        tam_mb = info.asset_tamanho / (1024 * 1024)
        resp = QMessageBox.question(
            self, "Nova versão disponível",
            f"Versão nova encontrada:\n\n"
            f"Atual:  {info.build_marker_local}\n"
            f"Nova:   {info.build_marker_remoto}\n\n"
            f"Tamanho do download: {tam_mb:.1f} MB\n\n"
            "O app vai baixar em segundo plano e aplicar na PRÓXIMA vez que "
            "você abrir. Você pode continuar usando normalmente.\n\n"
            "Baixar agora?",
        )
        if resp != QMessageBox.Yes:
            return
        self._log_line(f"→ Baixando atualização {info.build_marker_remoto}…")
        self._updater_bar.iniciar(info)
