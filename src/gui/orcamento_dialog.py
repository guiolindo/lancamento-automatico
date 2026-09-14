"""
Módulo Orçamento — Notas Fiscais de Despesa (build-95, primeira versão).

Dialog dedicado pra automatizar o form TOTVS "Notas Fiscais de Despesa"
com templates de fornecedores recorrentes. Cada template define TODOS os
campos fixos do formulário; só 3 variáveis por nota (número, data
emissão, valor) — que o operador cola de um Excel ou o app extrai de um
PDF via Gemini.

Escopo do build-95 (esta primeira versão):
- UI completa: combo fornecedor, grid, drag-drop de PDF, botão extrair.
- Parser Gemini de NFS-e multi-página em 1 request só.
- Botão "Executar no TOTVS" DESABILITADO com aviso — RPA é build-96.

Escopo dos próximos builds:
- build-96: `rpa_orcamento.py` executa uma nota isolada.
- build-97: lote de N, auto-detect visual dos campos, resumo.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QDate, QEasingCurve, QPropertyAnimation, Qt, QThread, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.logger import log
from ..core.settings_store import SettingsStore
from .widgets import DateEditFast


def _formatar_moeda(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _carregar_templates() -> dict:
    """Localiza o mapeamento_orcamento.json com fallback (mesmo pattern
    do mapeamento.json principal)."""
    import sys
    candidatos = [
        Path(sys.argv[0]).resolve().parent / "mapeamento_orcamento.json",
        Path(sys.argv[0]).resolve().parent / "config" / "mapeamento_orcamento.json",
        Path(__file__).resolve().parent.parent / "config" / "mapeamento_orcamento.json",
    ]
    for c in candidatos:
        if c.exists():
            with open(c, "r", encoding="utf-8") as f:
                return json.load(f)
    log.error("mapeamento_orcamento.json não encontrado em nenhum caminho")
    return {"templates": {}}


class ExtratorNfseThread(QThread):
    """Worker thread pro parser Gemini. Não bloqueia UI."""
    concluido = Signal(list)   # lista de notas
    falhou = Signal(str)

    def __init__(self, pdf: Path, api_key: str, modelo: str):
        super().__init__()
        self._pdf = pdf
        self._api_key = api_key
        self._modelo = modelo

    def run(self) -> None:
        try:
            from ..core.gemini_client import GeminiClient
            client = GeminiClient(self._api_key, self._modelo)
            notas = client.extrair_notas_nfse(self._pdf)
            self.concluido.emit(notas)
        except BaseException as e:  # noqa: BLE001
            log.exception("ExtratorNfseThread falhou")
            self.falhou.emit(f"{type(e).__name__}: {e}")


class OrcamentoDialog(QDialog):
    COLS = ["#", "Pág.", "Número NF", "Data Emissão", "Valor (R$)", "Status"]

    def __init__(self, settings: SettingsStore, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Auto Conferi — Orçamento (Notas Fiscais de Despesa)")
        self.setMinimumSize(1080, 700)
        self.setAcceptDrops(True)

        self._pdf_selecionado: Path | None = None
        self._extrator: ExtratorNfseThread | None = None
        self._templates = _carregar_templates().get("templates", {})

        self._montar_ui()

    # ---------- UI ----------

    def _montar_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(14)

        # Cabeçalho
        titulo = QLabel("Notas Fiscais de Despesa — Orçamento")
        titulo.setStyleSheet("font-size: 20px; font-weight: 700; letter-spacing: -0.3px;")
        root.addWidget(titulo)

        sub = QLabel(
            "Escolha o fornecedor, arraste um PDF com as notas (ou clique em "
            "'Selecionar PDF') e clique em 'Extrair'. Só 3 campos por nota mudam "
            "— o resto vem do template."
        )
        sub.setStyleSheet("color: #94A3B8; font-size: 12px;")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # Toolbar
        toolbar = QFrame()
        toolbar.setProperty("card", True)
        tl = QVBoxLayout(toolbar)
        tl.setContentsMargins(14, 10, 14, 10)
        tl.setSpacing(8)

        r1 = QHBoxLayout()
        r1.setSpacing(10)
        r1.addWidget(self._campo_inline("FORNECEDOR"))
        self._combo_forn = QComboBox()
        for chave, cfg in sorted(self._templates.items()):
            rot = f"{chave}  ({cfg.get('descricao', '')[:40]})"
            self._combo_forn.addItem(rot, chave)
        self._combo_forn.setMinimumWidth(240)
        r1.addWidget(self._combo_forn)

        r1.addSpacing(12)
        self._btn_pick = QPushButton("Selecionar PDF")
        self._btn_pick.setProperty("ghost", True)
        self._btn_pick.clicked.connect(self._selecionar_pdf)
        r1.addWidget(self._btn_pick)

        self._lbl_pdf = QLabel("Nenhum PDF · arraste um aqui")
        self._lbl_pdf.setStyleSheet("color: #B7C2CF; font-size: 12px;")
        r1.addWidget(self._lbl_pdf, 1)

        self._btn_extrair = QPushButton("Extrair notas do PDF")
        self._btn_extrair.setProperty("primary", True)
        self._btn_extrair.setEnabled(False)
        self._btn_extrair.setMinimumWidth(170)
        self._btn_extrair.clicked.connect(self._extrair)
        r1.addWidget(self._btn_extrair)
        tl.addLayout(r1)

        # Linha 2: data lançto + observação
        r2 = QHBoxLayout()
        r2.setSpacing(10)
        r2.addWidget(self._campo_inline("DATA LANÇTO"))
        self._date_lancto = DateEditFast(QDate.currentDate())
        self._date_lancto.setDisplayFormat("dd/MM/yyyy")
        self._date_lancto.setCalendarPopup(True)
        self._date_lancto.setFixedWidth(145)
        self._date_lancto.setToolTip(
            "Data de lançamento no TOTVS. Vencimento fica igual a essa data."
        )
        r2.addWidget(self._date_lancto)

        r2.addStretch(1)
        self._lbl_resumo = QLabel("0 notas · R$ 0,00")
        self._lbl_resumo.setStyleSheet(
            "font-size: 13px; color: #F5F7FA; font-weight: 600; "
            "font-family: 'Cascadia Mono', 'Consolas';"
        )
        r2.addWidget(self._lbl_resumo)
        tl.addLayout(r2)

        root.addWidget(toolbar)

        # Tabela
        self._tabela = QTableWidget()
        self._tabela.setColumnCount(len(self.COLS))
        self._tabela.setHorizontalHeaderLabels(self.COLS)
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.setAlternatingRowColors(True)
        self._tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tabela.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self._tabela.setShowGrid(False)
        h = self._tabela.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        root.addWidget(self._tabela, 1)

        # Rodapé
        rod = QHBoxLayout()
        self._lbl_status = QLabel("Pronto")
        self._lbl_status.setStyleSheet("color: #94A3B8; font-size: 11px;")
        rod.addWidget(self._lbl_status, 1)

        btn_fechar = QPushButton("Fechar")
        btn_fechar.clicked.connect(self.reject)
        rod.addWidget(btn_fechar)

        self._btn_executar = QPushButton("Executar no TOTVS")
        self._btn_executar.setProperty("brand", True)
        self._btn_executar.setMinimumWidth(200)
        self._btn_executar.setEnabled(False)
        self._btn_executar.setToolTip(
            "Automação do TOTVS Orçamento fica disponível no próximo build "
            "(96). Nesta versão você já valida os dados extraídos e prepara "
            "a lista antes de executar."
        )
        rod.addWidget(self._btn_executar)
        root.addLayout(rod)

    def _campo_inline(self, texto: str) -> QLabel:
        lb = QLabel(texto)
        lb.setStyleSheet(
            "color: #94A3B8; font-size: 10px; font-weight: 700; "
            "text-transform: uppercase; letter-spacing: 1px; padding-right: 6px;"
        )
        return lb

    # ---------- Drag & drop ----------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            caminho = Path(url.toLocalFile())
            if caminho.suffix.lower() == ".pdf":
                self._setar_pdf(caminho)
                return

    # ---------- Ações ----------

    def _selecionar_pdf(self) -> None:
        pasta = self.settings.get("ultima_pasta_upload") or str(Path.home() / "Downloads")
        arq, _ = QFileDialog.getOpenFileName(
            self, "Selecione o PDF com as notas", pasta,
            "PDF (*.pdf)"
        )
        if arq:
            self._setar_pdf(Path(arq))

    def _setar_pdf(self, caminho: Path) -> None:
        self._pdf_selecionado = caminho
        self._lbl_pdf.setText(f"📄 {caminho.name}")
        self._btn_extrair.setEnabled(True)
        self.settings.set("ultima_pasta_upload", str(caminho.parent))
        self._lbl_status.setText(f"PDF pronto pra extrair — {caminho.name}")

    def _extrair(self) -> None:
        if self._pdf_selecionado is None:
            return
        api_key = self.settings.get_gemini_api_key()
        if not api_key:
            QMessageBox.warning(
                self, "Chave ausente",
                "Configure a chave da API Gemini antes de extrair.\n\n"
                "Clique em Config na barra lateral do app."
            )
            return

        self._btn_extrair.setEnabled(False)
        self._btn_extrair.setText("Extraindo…")
        self._lbl_status.setText(
            "🤖 Enviando PDF pro Gemini — 1 request só, mesmo com 40 páginas…"
        )
        modelo = self.settings.get("gemini_model", "gemini-3.5-flash-lite")

        self._extrator = ExtratorNfseThread(self._pdf_selecionado, api_key, modelo)
        self._extrator.concluido.connect(self._on_extraido)
        self._extrator.falhou.connect(self._on_falhou)
        self._extrator.start()

    def _on_extraido(self, notas: list) -> None:
        self._btn_extrair.setEnabled(True)
        self._btn_extrair.setText("Extrair notas do PDF")
        self._popular_grid(notas)
        n = len(notas)
        total = sum(n_.get("valor", 0.0) for n_ in notas)
        self._lbl_resumo.setText(f"{n} nota(s) · {_formatar_moeda(total)}")
        self._lbl_status.setText(
            f"✓ {n} nota(s) extraída(s). Revise e clique em Executar "
            "(disponível no próximo build)."
        )

    def _on_falhou(self, msg: str) -> None:
        self._btn_extrair.setEnabled(True)
        self._btn_extrair.setText("Extrair notas do PDF")
        self._lbl_status.setText("❌ Falha na extração — veja o log")
        QMessageBox.critical(
            self, "Falha na extração",
            f"Não consegui extrair as notas do PDF:\n\n{msg}\n\n"
            "Se o problema persistir, verifique se o PDF está legível "
            "(scan borrado, girado, etc.)."
        )

    def _popular_grid(self, notas: list) -> None:
        self._tabela.setRowCount(len(notas))
        for i, n in enumerate(notas):
            it_num = QTableWidgetItem(str(i + 1))
            it_num.setFlags(it_num.flags() & ~Qt.ItemIsEditable)
            it_num.setTextAlignment(Qt.AlignCenter)
            self._tabela.setItem(i, 0, it_num)

            it_pag = QTableWidgetItem(str(n.get("pagina", i + 1)))
            it_pag.setFlags(it_pag.flags() & ~Qt.ItemIsEditable)
            it_pag.setTextAlignment(Qt.AlignCenter)
            self._tabela.setItem(i, 1, it_pag)

            self._tabela.setItem(i, 2, QTableWidgetItem(n.get("numero", "")))

            data_txt = n.get("data_emissao", "")
            # Formata YYYY-MM-DD → DD/MM/YYYY se válido
            try:
                d = datetime.strptime(data_txt, "%Y-%m-%d").date()
                data_txt = d.strftime("%d/%m/%Y")
            except (ValueError, TypeError):
                pass
            self._tabela.setItem(i, 3, QTableWidgetItem(data_txt))

            valor = n.get("valor", 0.0) or 0.0
            it_val = QTableWidgetItem(f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            it_val.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._tabela.setItem(i, 4, it_val)

            faltando = not n.get("numero") or not data_txt or valor <= 0
            status = "Revisar" if faltando else "Pronta"
            it_st = QTableWidgetItem(status)
            it_st.setFlags(it_st.flags() & ~Qt.ItemIsEditable)
            it_st.setTextAlignment(Qt.AlignCenter)
            self._tabela.setItem(i, 5, it_st)

    # ---------- Fade-in ----------

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.setWindowOpacity(0.0)
        self._fade = QPropertyAnimation(self, b"windowOpacity")
        self._fade.setDuration(200)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.InOutQuad)
        self._fade.start()
