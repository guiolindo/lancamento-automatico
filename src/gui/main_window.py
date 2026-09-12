from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QDate, QRect, QSize, Qt, QThread
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSpacerItem,
    QVBoxLayout, QWidget
)

from . import icons as _icons

from ..core import calibracao as calib_store
from ..core.logger import log
from ..core.mapping import MappingRepository
from ..core.models import Imposto, Lancamento
from ..core.settings_store import SettingsStore
from .calibracao_dialog import CalibracaoDialog
from .depara_dialog import DeParaDialog
from .hud_execucao import HudExecucao
from .preview_table import PreviewTable
from .setup_dialog import SetupDialog
from .theme import qss
from .updater_bar import UpdaterBar
from .workers import ExtracaoWorker, LoteWorker


# Cada item de nav: (chave, icon_factory_name, rótulo, tooltip)
NAV_ITEMS = [
    ("dashboard",     "icon_lote",     "Novo lote", "Preparar e executar novo lote"),
    ("mapeamento",    "icon_filiais",  "Filiais",   "Editar de-para de filiais"),
    ("configuracoes", "icon_config",   "Config",    "Chave da API e configurações"),
    ("sobre",         "icon_sobre",    "Sobre",     "Sobre o Auto Conferi"),
]

NOME_SECAO = {
    "dashboard":     "Novo lote",
    "mapeamento":    "Filiais (De-Para)",
    "configuracoes": "Configurações",
}


class MainWindow(QMainWindow):
    def __init__(self, settings: SettingsStore, mapping: MappingRepository, mapping_path: Path):
        super().__init__()
        self.settings = settings
        self.mapping = mapping
        self.mapping_path = mapping_path
        self.setWindowTitle("Auto Conferi — Automação Fiscal TOTVS")
        self.setAcceptDrops(True)  # aceita drag-and-drop de arquivos
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
        self._hud: HudExecucao | None = None
        # Registra se o lote atual está usando o HUD (mono-monitor). Usado
        # em _on_pedir_confirmacao_manual pra decidir se abre QMessageBox
        # ou usa o painel do HUD.
        self._lote_com_hud = False

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
        side.setFixedWidth(184)
        v = QVBoxLayout(side)
        v.setContentsMargins(0, 20, 0, 16)
        v.setSpacing(2)

        # Cabeçalho: logo + wordmark
        head = QHBoxLayout()
        head.setContentsMargins(16, 0, 16, 16)
        head.setSpacing(10)
        logo = QLabel()
        logo_path = self._buscar_asset("branding/logo_autoconferi_48.png")
        if logo_path:
            pm = QPixmap(str(logo_path))
            logo.setPixmap(pm.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        head.addWidget(logo)

        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        brand = QLabel("Auto Conferi")
        brand.setObjectName("SidebarBrand")
        brand.setStyleSheet("font-size: 14px; font-weight: 700; color: inherit;")
        brand_col.addWidget(brand)
        tag = QLabel("fiscal · TOTVS")
        tag.setStyleSheet("font-size: 10px; color: #B7C2CF;")
        brand_col.addWidget(tag)
        head.addLayout(brand_col)
        head.addStretch(1)

        head_wrap = QWidget()
        head_wrap.setLayout(head)
        v.addWidget(head_wrap)

        # Itens de nav com ícone SVG desenhado + label
        self._nav_buttons: dict[str, QPushButton] = {}
        for key, icon_fn, rotulo, tip in NAV_ITEMS:
            btn = QPushButton("  " + rotulo)
            btn.setProperty("navItem", True)
            btn.setToolTip(tip)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setIcon(getattr(_icons, icon_fn)("#B7C2CF"))
            btn.setIconSize(QSize(16, 16))
            btn.clicked.connect(lambda _=False, k=key: self._trocar_secao(k))
            self._nav_buttons[key] = btn
            v.addWidget(btn)

        self._nav_buttons["dashboard"].setProperty("active", True)
        # Ícone do ativo na cor accent do tema atual (verde-fisco no dark,
        # navy no light).
        from .theme import PALETTE_DARK, PALETTE_LIGHT
        _p = PALETTE_LIGHT if self._tema == "claro" else PALETTE_DARK
        self._nav_buttons["dashboard"].setIcon(_icons.icon_lote(_p["accent"]))
        v.addStretch(1)

        # Toggle de tema no rodapé com ícone
        self._btn_tema = QPushButton()
        self._btn_tema.setProperty("navItem", True)
        self._btn_tema.setCursor(Qt.PointingHandCursor)
        self._btn_tema.setIconSize(QSize(16, 16))
        self._btn_tema.clicked.connect(self._toggle_tema)
        self._atualizar_texto_tema()
        v.addWidget(self._btn_tema)

        # Rodapé com versão
        from ..main import BUILD_MARKER
        versao = QLabel("v " + BUILD_MARKER.split(" ")[0])
        versao.setStyleSheet("color: #718096; font-size: 10px; padding: 8px 16px 0 16px;")
        v.addWidget(versao)

        return side

    def _atualizar_texto_tema(self) -> None:
        if self._tema == "claro":
            self._btn_tema.setText("  Modo escuro")
            self._btn_tema.setIcon(_icons.icon_tema_dark("#B7C2CF"))
            self._btn_tema.setToolTip("Mudar pra modo escuro")
        else:
            self._btn_tema.setText("  Modo claro")
            self._btn_tema.setIcon(_icons.icon_tema_light("#B7C2CF"))
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
        """Layout single-screen: stepper compacto no topo, toolbar de ação,
        resumo, tabela dominante, painel atividade lateral colapsável."""
        wrap = QFrame()
        wrap.setObjectName("Content")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(24, 16, 24, 16)
        v.setSpacing(12)

        # STEPPER: [1 Documento] → [2 Revisar] → [3 Executar]
        v.addWidget(self._stepper())

        # TOOLBAR: Selecionar arquivo | nome | Extrair | busca | filtros
        v.addWidget(self._toolbar_acoes())

        # RESUMO: contagem, valor total, alertas
        v.addWidget(self._resumo_lote())

        # Área principal: TABELA (esquerda, dominante) + ATIVIDADE (direita, colapsável)
        col2 = QHBoxLayout()
        col2.setSpacing(12)
        col2.addWidget(self._area_tabela(), 3)
        col2.addWidget(self._card_atividade(), 0)
        v.addLayout(col2, 1)

        # RODAPÉ: status esquerdo + botão Executar direito
        v.addWidget(self._rodape_executar())

        return wrap

    # ----- Componentes do layout single-screen -----

    def _stepper(self) -> QWidget:
        wrap = QFrame()
        wrap.setProperty("card", True)
        h = QHBoxLayout(wrap)
        h.setContentsMargins(16, 8, 16, 8)
        h.setSpacing(4)

        self._step_labels: list[QLabel] = []
        passos = [("1", "Documento"), ("2", "Revisar"), ("3", "Executar")]
        for i, (num, texto) in enumerate(passos):
            box = QHBoxLayout()
            box.setSpacing(8)
            lb_num = QLabel(num)
            lb_num.setProperty("stepNum", True)
            lb_num.setFixedSize(22, 22)
            lb_num.setAlignment(Qt.AlignCenter)
            box.addWidget(lb_num)
            lb_txt = QLabel(texto)
            lb_txt.setStyleSheet("font-size: 12px; font-weight: 600;")
            self._step_labels.append(lb_txt)
            box.addWidget(lb_txt)
            h.addLayout(box)
            if i < len(passos) - 1:
                sep = QLabel("›")
                sep.setStyleSheet("color: #718096; font-size: 16px; padding: 0 6px;")
                h.addWidget(sep)

        h.addStretch(1)
        # KPIs pequenos à direita
        self._kpi_qtd_label = QLabel("0 lançamentos")
        self._kpi_qtd_label.setStyleSheet("color: #B7C2CF; font-size: 12px;")
        h.addWidget(self._kpi_qtd_label)
        h.addWidget(QLabel(" · "))
        self._kpi_valor_label = QLabel("R$ 0,00")
        self._kpi_valor_label.setStyleSheet(
            "color: #F5F7FA; font-size: 13px; font-weight: 700;"
            "font-family: 'Cascadia Mono', 'Consolas';"
        )
        h.addWidget(self._kpi_valor_label)
        return wrap

    def _toolbar_acoes(self) -> QWidget:
        wrap = QFrame()
        wrap.setProperty("card", True)
        h = QHBoxLayout(wrap)
        h.setContentsMargins(14, 10, 14, 10)
        h.setSpacing(10)

        # Imposto (combo compacto)
        h.addWidget(self._campo_inline("IMPOSTO"))
        self._combo_imposto = QComboBox()
        self._combo_imposto.addItem("IRRF")
        self._combo_imposto.setFixedWidth(110)
        h.addWidget(self._combo_imposto)

        # Três datas independentes: EMISSÃO / CONTÁBIL / VENCIMENTO.
        # Preenchem os 3 campos correspondentes no TOTVS (Inclusão de
        # Títulos). Default todas = hoje; usuário edita cada uma
        # independentemente conforme a nota fiscal.
        # REGRAS DE ORDEM (TOTVS recusa se violadas — enforçadas via
        # setMinimumDate abaixo, usuário não consegue selecionar inválido):
        #   contábil >= emissão
        #   vencimento >= contábil
        # Width 145 pra dd/MM/aaaa + botão popup caberem sem cortar o ano
        # (120 estava cortando o último dígito).
        LARG_DATA = 145
        hoje = QDate.currentDate()

        h.addWidget(self._campo_inline("EMISS"))
        self._date_emissao = QDateEdit(hoje)
        self._date_emissao.setDisplayFormat("dd/MM/yyyy")
        self._date_emissao.setCalendarPopup(True)
        self._date_emissao.setFixedWidth(LARG_DATA)
        self._date_emissao.setToolTip("Data de emissão do documento")
        h.addWidget(self._date_emissao)

        h.addWidget(self._campo_inline("CONTÁB"))
        self._date_contabil = QDateEdit(hoje)
        self._date_contabil.setDisplayFormat("dd/MM/yyyy")
        self._date_contabil.setCalendarPopup(True)
        self._date_contabil.setFixedWidth(LARG_DATA)
        self._date_contabil.setMinimumDate(hoje)  # nunca antes da emissão
        self._date_contabil.setToolTip(
            "Data contábil (Inclusão no TOTVS). Nunca pode ser antes da "
            "emissão — o TOTVS recusa."
        )
        h.addWidget(self._date_contabil)

        h.addWidget(self._campo_inline("VENC"))
        self._date_vencimento = QDateEdit(hoje)
        self._date_vencimento.setDisplayFormat("dd/MM/yyyy")
        self._date_vencimento.setCalendarPopup(True)
        self._date_vencimento.setFixedWidth(LARG_DATA)
        self._date_vencimento.setMinimumDate(hoje)  # nunca antes da contábil
        self._date_vencimento.setToolTip(
            "Data de vencimento. Nunca pode ser antes da contábil — o "
            "TOTVS recusa."
        )
        h.addWidget(self._date_vencimento)

        # Enforcement das regras: quando emissão muda, contábil não pode
        # ser antes dela; quando contábil muda, vencimento não pode ser
        # antes dela. setMinimumDate impede seleção manual E o auto-bump
        # se o valor atual ficou inválido garante que os campos abaixo
        # acompanham quando o usuário anda pra frente na emissão.
        self._date_emissao.dateChanged.connect(self._on_emissao_mudou)
        self._date_contabil.dateChanged.connect(self._on_contabil_mudou)

        # Separador visual
        sep = QFrame()
        sep.setObjectName("Divisor")
        sep.setFixedSize(1, 24)
        h.addWidget(sep)

        # Arquivo
        btn_pick = QPushButton("  Selecionar arquivo")
        btn_pick.setIcon(_icons.icon_lote("#B7C2CF"))
        btn_pick.setIconSize(QSize(14, 14))
        btn_pick.setProperty("ghost", True)
        btn_pick.clicked.connect(self._selecionar_arquivo)
        h.addWidget(btn_pick)

        self._label_arquivo = QLabel("Nenhum arquivo · arraste um aqui")
        self._label_arquivo.setStyleSheet("color: #B7C2CF; font-size: 12px;")
        self._label_arquivo.setToolTip("Você pode arrastar o arquivo direto pra janela do app.")
        self._label_arquivo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._label_arquivo.setMinimumWidth(80)
        h.addWidget(self._label_arquivo, 1)

        # Extrair (primário)
        self._btn_extrair = QPushButton("Extrair dados")
        self._btn_extrair.setProperty("primary", True)
        self._btn_extrair.setMinimumWidth(150)
        self._btn_extrair.clicked.connect(self._extrair)
        h.addWidget(self._btn_extrair)

        return wrap

    def _resumo_lote(self) -> QWidget:
        wrap = QFrame()
        wrap.setStyleSheet("QFrame { background: transparent; }")
        h = QHBoxLayout(wrap)
        h.setContentsMargins(4, 0, 4, 0)
        h.setSpacing(16)

        self._label_status_revisao = QLabel("Aguardando documento")
        self._label_status_revisao.setProperty("badge", "pendente")
        h.addWidget(self._label_status_revisao)

        self._chk_apenas_primeiro = QCheckBox("Testar só o 1º")
        self._chk_apenas_primeiro.setChecked(False)
        self._chk_apenas_primeiro.setToolTip(
            "Executa só o primeiro lançamento — pra validar antes do lote inteiro."
        )
        h.addWidget(self._chk_apenas_primeiro)

        self._chk_confirmar_auto = QCheckBox("Confirmar '+' automático")
        self._chk_confirmar_auto.setChecked(
            bool(self.settings.get("rpa.confirmar_automaticamente", True))
        )
        self._chk_confirmar_auto.stateChanged.connect(self._on_toggle_confirmar_auto)
        h.addWidget(self._chk_confirmar_auto)

        h.addStretch(1)

        self._btn_calibrar = QPushButton("Recalibrar (backup)")
        self._btn_calibrar.setProperty("ghost", True)
        self._btn_calibrar.setToolTip(
            "Auto-detect via visão computacional roda automaticamente a "
            "cada lote. Use este botão só se o auto-detect falhar por "
            "mudança de tema/DPI/versão do TOTVS — a calibração salva "
            "aqui serve de fallback."
        )
        self._btn_calibrar.clicked.connect(self._abrir_calibracao)
        h.addWidget(self._btn_calibrar)

        return wrap

    def _area_tabela(self) -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        v = QVBoxLayout(card)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self._tabela = PreviewTable()
        self._tabela.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        v.addWidget(self._tabela, 1)

        return card

    def _rodape_executar(self) -> QWidget:
        wrap = QFrame()
        wrap.setStyleSheet("QFrame { background: transparent; }")
        h = QHBoxLayout(wrap)
        h.setContentsMargins(4, 0, 4, 0)
        h.setSpacing(10)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setMinimumWidth(200)
        h.addWidget(self._progress, 1)
        h.addStretch(1)

        self._btn_cancelar = QPushButton("Cancelar")
        self._btn_cancelar.setProperty("danger", True)
        self._btn_cancelar.setVisible(False)
        self._btn_cancelar.clicked.connect(self._cancelar)
        h.addWidget(self._btn_cancelar)

        self._btn_executar = QPushButton("Executar no TOTVS")
        self._btn_executar.setProperty("brand", True)
        self._btn_executar.setMinimumWidth(200)
        self._btn_executar.setEnabled(False)
        self._btn_executar.clicked.connect(self._executar)
        h.addWidget(self._btn_executar)

        return wrap

    # -------- KPIs --------

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
        # Check de atualização automático no boot — dá 4s pra janela
        # renderizar + Windows Defender fazer a checagem CRL/OCSP inicial
        # do certificado do github.com (essa demora costuma ser 5-15s na
        # primeira request HTTPS após o boot da máquina).
        from PySide6.QtCore import QTimer
        QTimer.singleShot(4000, self._check_atualizacao_boot)

    def _check_atualizacao_boot(self, tentativa: int = 1) -> None:
        """Boot check — usa o mesmo helper thread + watchdog.
        Se falhar (rede lenta na primeira request HTTPS), agenda retry
        automático. Delays entre tentativas: 30s, 60s, 120s. Após a 4ª
        tentativa, para — usuário pode acionar manualmente pelo botão."""
        from PySide6.QtCore import QTimer

        # Não intercepta o botão se manual já está rolando ou se o botão
        # está em uso pelo próprio check anterior; simplesmente agenda.
        self._btn_atualizar.setText("Verificando…")
        self._btn_atualizar.setEnabled(False)

        def on_done(info):
            self._btn_atualizar.setEnabled(True)

            if info is not None:
                # Sucesso — não precisa mais retry
                self._btn_atualizar.setText("Atualizar")
                if info.tem_atualizacao:
                    self._modal_obrigatorio(info)
                else:
                    self._log_line(f"i Versão local já é a mais recente")
                return

            # Falha — decide se agenda outra tentativa
            proximos_delays = {1: 30, 2: 60, 3: 120}
            if tentativa in proximos_delays:
                delay_s = proximos_delays[tentativa]
                self._btn_atualizar.setText("Atualizar")  # deixa neutro
                self._btn_atualizar.setToolTip(
                    f"Falha ao consultar GitHub. Tentando de novo em {delay_s}s."
                )
                self._log_line(
                    f"⚠ Tentativa {tentativa} de verificar atualização falhou — "
                    f"nova tentativa em {delay_s}s"
                )
                QTimer.singleShot(delay_s * 1000,
                                  lambda: self._check_atualizacao_boot(tentativa + 1))
            else:
                # Última tentativa também falhou — desiste, deixa manual
                self._btn_atualizar.setText("⚠ Atualizar")
                self._btn_atualizar.setToolTip(
                    "Não consegui consultar o GitHub em várias tentativas. "
                    "Clique pra tentar manualmente."
                )
                self._log_line(
                    "⚠ Todas as tentativas automáticas de verificar atualização falharam. "
                    "Use o botão Atualizar quando quiser tentar de novo."
                )

        self._rodar_check_em_thread(on_done)

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
        # Auto-detect (visão computacional em src/core/visao_totvs.py) é
        # SEMPRE tentado no início do lote, independente de calibração
        # manual. A calibração manual serve só de fallback quando a
        # visão não consegue localizar os campos.
        if not hasattr(self, "_lbl_status_calib_top"):
            return
        if self._calibracao.esta_completa():
            self._lbl_status_calib_top.setText(
                "● Auto-detect visual ativo · calibração manual como backup"
            )
            self._lbl_status_calib_top.setStyleSheet("color:#22C55E; font-size:11px;")
            self._lbl_status_calib_top.setToolTip(
                "A cada lote o app tenta detectar os campos do TOTVS "
                "automaticamente via visão computacional. Se falhar, usa "
                "a calibração manual que você já salvou."
            )
        else:
            self._lbl_status_calib_top.setText("● Auto-detect visual ativo")
            self._lbl_status_calib_top.setStyleSheet("color:#B45309; font-size:11px;")
            self._lbl_status_calib_top.setToolTip(
                "A cada lote o app tenta detectar os campos do TOTVS "
                "automaticamente via visão computacional. Sem calibração "
                "manual salva ainda — clique em 'Recalibrar' se o "
                "auto-detect falhar."
            )

    # ---------------- Ações ----------------

    def _trocar_secao(self, chave: str) -> None:
        # 'mapeamento' e 'configuracoes' abrem DIALOG — não são seções
        # separadas. Não devem tirar o 'active' do dashboard (que é a
        # única tela real). Antes ficava um estado 'fantasma' onde o
        # ícone lateral marcava selecionado mas o conteúdo era o
        # dashboard.
        if chave in ("mapeamento", "configuracoes", "sobre"):
            if chave == "configuracoes":
                self._abrir_setup()
            elif chave == "mapeamento":
                dlg = DeParaDialog(self.mapping, self.mapping_path, self)
                dlg.setStyleSheet(qss(self._tema))
                if dlg.exec():
                    self._log_line("✓ De-Para atualizado e recarregado")
            elif chave == "sobre":
                self._abrir_sobre()
            return
        # Só troca active pra chaves que são realmente seções distintas
        for k, btn in self._nav_buttons.items():
            ativo = (k == chave)
            btn.setProperty("active", ativo)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            # Repinta o ícone na cor certa (accent do tema pra ativo,
            # muted pra inativo)
            item = next((n for n in NAV_ITEMS if n[0] == k), None)
            if item:
                from .theme import PALETTE_DARK, PALETTE_LIGHT
                _p = PALETTE_LIGHT if self._tema == "claro" else PALETTE_DARK
                cor = _p["accent"] if ativo else _p["text_muted"]
                btn.setIcon(getattr(_icons, item[1])(cor))
        self._lb_secao.setText(NOME_SECAO.get(chave, chave))

    def _abrir_sobre(self) -> None:
        """Diálogo Sobre — créditos e info da versão."""
        from ..main import BUILD_MARKER
        box = QMessageBox(self)
        box.setWindowTitle("Sobre")
        box.setIcon(QMessageBox.Information)
        box.setTextFormat(Qt.RichText)
        box.setText(
            "<h3 style='margin:0 0 6px 0'>Auto Conferi</h3>"
            "<p style='color:#888;margin:0'>Automação de lançamento fiscal · "
            "integração para TOTVS/Consinco</p>"
            "<br><br>"
            f"<b>Versão:</b> <code>{BUILD_MARKER}</code><br>"
            "<b>Produzido por:</b> Guilherme Júnio<br>"
            "<br>"
            "<p style='color:#888;font-size:11px'>App portátil sem instalação · "
            "roda sem admin · atualiza automaticamente pelo GitHub.</p>"
        )
        box.setStandardButtons(QMessageBox.Ok)
        box.exec()

    def _selecionar_arquivo(self) -> None:
        # Volta ao dialog NATIVO do Windows: tem PT-BR automaticamente,
        # pré-visualização de imagens, ordenação por data, atalhos do
        # Explorer. O dialog Qt próprio (DontUseNativeDialog) que a gente
        # tinha usando pra fugir do freeze de 15s no OneDrive/AV acabou
        # travando muito mais (50s+) e ficando em inglês.
        # Se o nativo ainda travar em algum PC específico, o usuário pode
        # arrastar o arquivo direto pra janela do app (drop event).
        ultimo = self.settings.get("ultima_pasta_upload", "") or str(Path.home())
        arquivo, _ = QFileDialog.getOpenFileName(
            self, "Selecionar documento",
            ultimo,
            "Documentos (*.pdf *.png *.jpg *.jpeg *.webp);;Todos os arquivos (*.*)",
        )
        if not arquivo:
            return
        self._aceitar_arquivo(Path(arquivo))
        return

    def _aceitar_arquivo(self, p: Path) -> None:
        """Registra o arquivo escolhido (via dialog OU drop). Único lugar
        que faz o setup do label + settings + log."""
        self._arquivo_selecionado = p
        self.settings.set("ultima_pasta_upload", str(p.parent))
        self._label_arquivo.setText(p.name)
        self._label_arquivo.setStyleSheet("color: #F5F7FA; font-size: 12px;")
        self._log_line(f"→ Arquivo selecionado: {p.name}")

    # ---------------- Drag & Drop ----------------
    # Suporte a arrastar arquivo pra dentro da janela. Extensões aceitas
    # são as mesmas do dialog (.pdf, .png, .jpg, .jpeg, .webp).
    _EXTS_ACEITAS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt convention)
        md = event.mimeData()
        if md.hasUrls():
            for url in md.urls():
                if url.isLocalFile():
                    ext = Path(url.toLocalFile()).suffix.lower()
                    if ext in self._EXTS_ACEITAS:
                        event.acceptProposedAction()
                        return
        event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            p = Path(url.toLocalFile())
            if p.suffix.lower() in self._EXTS_ACEITAS and p.exists():
                self._aceitar_arquivo(p)
                event.acceptProposedAction()
                return
        event.ignore()

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

        def _to_date(q):
            d = q.toPython()
            return date(d.year, d.month, d.day)

        emissao = _to_date(self._date_emissao.date())
        contabil = _to_date(self._date_contabil.date())
        vencto = _to_date(self._date_vencimento.date())

        worker = ExtracaoWorker(
            arquivo=self._arquivo_selecionado,
            api_key=api_key,
            modelo=self.settings.get("gemini_model", "gemini-3.5-flash-lite"),
            imposto=self._imposto_atual(),
            mapping=self.mapping,
            data_emissao=emissao,
            data_contabilizacao=contabil,
            vencimento=vencto,
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
        self._kpi_qtd_label.setText(f"{len(lancamentos)} lançamento(s)")
        self._kpi_valor_label.setText(self._formatar_moeda(total))
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

        # Decide MONO vs MULTI monitor e prepara HUD se for o caso.
        # Ver ARCHITECTURE.md seção "Auto-posicionamento e HUD".
        self._lote_com_hud = False
        try:
            geo_tela_totvs = self._preparar_janela_para_execucao()
            if geo_tela_totvs is not None:
                self._log_line(
                    "i Monitor único detectado — minimizando janela e "
                    "abrindo HUD no canto superior direito"
                )
                self._hud = HudExecucao()
                self._hud.parar_clicado.connect(self._cancelar)
                self._hud.confirmacao_respondida.connect(
                    self._on_hud_confirmacao_respondida
                )
                self._hud.iniciar(len(lancamentos_exec), geo_tela_totvs)
                self._lote_com_hud = True
                self.showMinimized()
        except Exception:  # noqa: BLE001
            log.exception("Falha preparando janela pra execução — segue sem HUD")

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
        if self._hud is not None:
            self._hud.on_progresso(i, total, msg)

    def _on_lote_finalizado(self, sucessos: int, falhas: int) -> None:
        self._btn_executar.setEnabled(True)
        self._btn_extrair.setEnabled(True)
        self._btn_cancelar.setVisible(False)
        self._progress.setVisible(False)
        if falhas == 0:
            self._set_status_revisao("sucesso", f"{sucessos} lançados")
        else:
            self._set_status_revisao("falha", f"{sucessos} ok · {falhas} falha(s)")
        self._log_line(
            f"# Lote finalizado às {datetime.now():%H:%M}: {sucessos} sucessos, {falhas} falhas"
        )
        self._encerrar_hud(sucessos, falhas)
        self._restaurar_janela_pos_lote()
        QMessageBox.information(self, "Lote finalizado", f"Sucessos: {sucessos}\nFalhas: {falhas}")

    def _on_erro_lote(self, msg: str) -> None:
        self._btn_executar.setEnabled(True)
        self._btn_extrair.setEnabled(True)
        self._btn_cancelar.setVisible(False)
        self._progress.setVisible(False)
        self._set_status_revisao("falha", "Erro no lote")
        self._encerrar_hud(0, 1)
        self._restaurar_janela_pos_lote()
        QMessageBox.critical(self, "Erro no lote", msg)

    def _cancelar(self) -> None:
        if self._worker_lote:
            self._worker_lote.cancelar()
            self._log_line("⏹ Cancelamento solicitado…")

    def _on_emissao_mudou(self, nova: QDate) -> None:
        """Emissão mudou → contábil não pode mais ser antes dela.
        setMinimumDate impede seleção nova antes; se o valor atual do
        contábil ficou inválido (antes da nova emissão), pula pra ela."""
        self._date_contabil.setMinimumDate(nova)
        if self._date_contabil.date() < nova:
            self._date_contabil.setDate(nova)
            # dateChanged do contábil vai disparar em cascata e ajustar
            # o vencimento também

    def _on_contabil_mudou(self, nova: QDate) -> None:
        """Contábil mudou → vencimento não pode mais ser antes dela."""
        self._date_vencimento.setMinimumDate(nova)
        if self._date_vencimento.date() < nova:
            self._date_vencimento.setDate(nova)

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
        # Se estamos em mono-monitor com HUD ativo, usa o painel do HUD
        # em vez de abrir QMessageBox (que restauraria a janela por cima
        # do TOTVS, quebrando toda a razão de ter minimizado).
        if self._hud is not None and self._lote_com_hud:
            self._hud.pedir_confirmacao_manual(index, resumo)
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

    def _on_hud_confirmacao_respondida(self, prosseguir: bool) -> None:
        if self._worker_lote:
            self._worker_lote.responder_confirmacao(prosseguir)

    def _log_line(self, msg: str) -> None:
        self._log.appendPlainText(f"[{datetime.now():%H:%M:%S}] {msg}")
        log.info(msg)

    # ---------------- Auto-posicionamento (mono vs multi monitor) ----------------
    # Ver ARCHITECTURE.md seção "Auto-posicionamento e HUD" para o contrato.
    #
    # Regra: se o operador tem só um monitor, ao executar o lote a MainWindow
    # é minimizada e um HUD compacto aparece no canto superior direito da
    # tela — fora da região que o TOTVS está usando, mas visível pra
    # acompanhar o progresso. Em multi-monitor a janela principal fica
    # como está (num monitor, TOTVS no outro).

    def _encontrar_totvs_geometry(self) -> QRect | None:
        """Se a janela 'Operador Financeiro' estiver aberta, devolve seu
        rect na tela. Best-effort — só Windows."""
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            achado = [0]

            @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            def _cb(hwnd, _lparam):
                if not user32.IsWindowVisible(hwnd):
                    return True
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, buf, 256)
                if buf.value and "operador financeiro" in buf.value.lower():
                    achado[0] = hwnd
                    return False
                return True

            user32.EnumWindows(_cb, 0)
            hwnd = achado[0]
            if not hwnd:
                return None

            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None
            return QRect(
                rect.left, rect.top,
                rect.right - rect.left, rect.bottom - rect.top,
            )
        except Exception:  # noqa: BLE001
            return None

    def _tela_que_contem(self, geo: QRect):
        """Devolve o QScreen cujo geometry contém o centro do rect,
        ou o primário se nenhum contiver (fora de tela)."""
        centro = geo.center()
        for screen in QGuiApplication.screens():
            if screen.geometry().contains(centro):
                return screen
        return QGuiApplication.primaryScreen()

    def _preparar_janela_para_execucao(self) -> QRect | None:
        """Chamado no início de _executar(). Se detectar monitor único,
        devolve o geometry da tela pra o HUD se posicionar (e o caller
        deve minimizar a MainWindow e mostrar o HUD). Se multi-monitor,
        devolve None — nada muda."""
        screens = QGuiApplication.screens()
        # Salva estado atual pra restaurar depois do lote
        self._estado_pre_lote = {
            "maximized": self.isMaximized(),
            "geometry": self.geometry(),
        }
        if len(screens) < 2:
            # Mono: HUD vai no canto superior direito do único monitor
            return QGuiApplication.primaryScreen().availableGeometry()

        # Multi-monitor: se acharmos o TOTVS num monitor, garante que a
        # MainWindow está num monitor DIFERENTE. Se já está, nada a fazer.
        geo_totvs = self._encontrar_totvs_geometry()
        if geo_totvs is not None:
            tela_totvs = self._tela_que_contem(geo_totvs)
            tela_atual = self.screen() or QGuiApplication.primaryScreen()
            if tela_atual is tela_totvs:
                # MainWindow tá na mesma tela do TOTVS — move pra outra
                for s in screens:
                    if s is not tela_totvs:
                        self._mover_para_tela(s)
                        break
        # Multi-monitor não usa HUD
        return None

    def _mover_para_tela(self, screen) -> None:
        geo_disponivel = screen.availableGeometry()
        alvo = self.geometry()
        alvo.moveCenter(geo_disponivel.center())
        # Clamp pra caber
        if alvo.width() > geo_disponivel.width():
            alvo.setWidth(geo_disponivel.width() - 40)
        if alvo.height() > geo_disponivel.height():
            alvo.setHeight(geo_disponivel.height() - 40)
        self.setGeometry(alvo)
        self.showMaximized()

    def _encerrar_hud(self, sucessos: int, falhas: int) -> None:
        if self._hud is not None:
            try:
                self._hud.finalizar(sucessos, falhas)
            except Exception:  # noqa: BLE001
                log.exception("Falha finalizando HUD")
            # HUD se auto-fecha em 3s via QTimer; limpa referência
            self._hud = None
        self._lote_com_hud = False

    def _restaurar_janela_pos_lote(self) -> None:
        """Após o lote, se tínhamos minimizado, restaura a janela como estava."""
        estado = getattr(self, "_estado_pre_lote", None)
        if not estado:
            return
        if estado.get("maximized"):
            self.showMaximized()
        else:
            self.setGeometry(estado["geometry"])
            self.showNormal()
        self.raise_()
        self.activateWindow()
        self._estado_pre_lote = None

    # ---------------- Shutdown limpo ----------------
    # Se o usuário fechar o app OU o Windows mandar shutdown, precisamos
    # garantir que nenhum QThread/worker fique rodando — senão o processo
    # pode segurar o shutdown do Windows (ele espera timeout, mata forçado).
    def closeEvent(self, event) -> None:  # noqa: N802 (Qt convention)
        try:
            self._encerrar_threads()
        except Exception:  # noqa: BLE001
            log.exception("Erro encerrando threads no closeEvent")
        super().closeEvent(event)

    def commitData(self, sm) -> None:  # noqa: N802 (Qt session manager)
        """Chamado pelo Windows quando shutdown/logoff é iniciado.
        Não pergunta nada, deixa o Windows fechar sem bloquear."""
        try:
            self._encerrar_threads()
        except Exception:  # noqa: BLE001
            pass

    def _encerrar_threads(self) -> None:
        """Força parada limpa de qualquer worker/thread em execução."""
        # Fecha HUD se estiver aberto — ele é uma janela top-level separada
        # e não fecharia sozinho quando a MainWindow fecha.
        if self._hud is not None:
            try:
                self._hud.close()
            except Exception:  # noqa: BLE001
                pass
            self._hud = None
        # Cancela worker do lote (se rodando) — ele checka cancel a cada
        # loop e sai
        if self._worker_lote:
            try:
                self._worker_lote.cancelar()
            except Exception:  # noqa: BLE001
                pass
        # Termina QThread se ainda tá rodando (2s de timeout — se não
        # sair, força)
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            if not self._thread.wait(2000):
                log.warning("QThread não parou em 2s — terminando forçado")
                self._thread.terminate()
                self._thread.wait(1000)

    # ---------------- Atualizador ----------------

    def _rodar_check_em_thread(self, on_done) -> None:
        """Roda updater.check() em background e chama on_done(info) no main
        thread. Guarda contra checks concorrentes — se já tem um rodando,
        ignora chamada nova. Watchdog de 20s pra prevenir travar."""
        import threading
        from ..core import updater
        from ..main import BUILD_MARKER
        from PySide6.QtCore import QTimer

        if getattr(self, "_check_em_curso", False):
            return
        self._check_em_curso = True

        resultado: dict = {}

        def worker():
            try:
                resultado["info"] = updater.check(BUILD_MARKER)
            except Exception as e:  # noqa: BLE001
                log.exception("check inesperado")
                resultado["info"] = None
                resultado["erro"] = str(e)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        # Watchdog: se não terminar em 20s, assume falha
        def _finalizar():
            self._check_em_curso = False
            info = resultado.get("info")
            try:
                on_done(info)
            except Exception:  # noqa: BLE001
                log.exception("on_done falhou")

        def _tentar_finalizar():
            if not t.is_alive():
                _finalizar()
            else:
                # Ainda rodando — tenta de novo em 500ms, até watchdog
                QTimer.singleShot(500, _tentar_finalizar)

        # Watchdog absoluto: 22s max, força cleanup
        def _timeout_forcado():
            if getattr(self, "_check_em_curso", False):
                log.warning("[updater] watchdog: check demorou > 22s, dando timeout forçado")
                resultado.setdefault("info", None)
                _finalizar()

        QTimer.singleShot(500, _tentar_finalizar)
        QTimer.singleShot(22000, _timeout_forcado)

    def _verificar_atualizacao(self) -> None:
        """Botão manual 'Atualizar' no topbar."""
        if getattr(self, "_check_em_curso", False):
            return
        self._btn_atualizar.setEnabled(False)
        self._btn_atualizar.setText("Verificando…")

        def on_done(info):
            self._btn_atualizar.setEnabled(True)
            self._btn_atualizar.setText("Atualizar")
            if info is None:
                QMessageBox.information(
                    self, "Atualização",
                    "Não consegui consultar o GitHub agora. Pode ser conexão "
                    "lenta ou API temporariamente indisponível. Veja o log."
                )
                return
            if not info.tem_atualizacao:
                QMessageBox.information(
                    self, "Atualização",
                    f"Você já tá na versão mais recente.\n\nLocal: {info.build_marker_local}",
                )
                return
            self._modal_obrigatorio(info)

        self._rodar_check_em_thread(on_done)
