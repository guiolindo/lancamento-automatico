"""
Módulo Orçamento — Notas Fiscais de Despesa (build-96, versão completa).

Dialog dedicado pra automatizar o form TOTVS "Notas Fiscais de Despesa"
com templates de fornecedores recorrentes. Cada template define TODOS os
campos fixos do formulário; só 3 variáveis por nota (número, data
emissão, valor) — que o operador cola de um Excel ou o app extrai de um
PDF via Gemini.

Build-96:
- RPA operacional: preenche aba Nota + detecta duplicidade + F2 + aba
  Financeiro + aba Contabilização + "+" + "Autorizar".
- Duplicidade: nunca inventa número (é nota fiscal real). Marca IGNORADA
  e segue para a próxima.
- Size check: PDF >18MB pede pra compactar antes de mandar (evita
  incorporar biblioteca de PDF pesada no bundle; user usa Smallpdf).
- Botão "Executar no TOTVS" habilitado após extração + calibração.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QThread, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core import calibracao_orcamento as calib_orc_store
from ..core.logger import log
from ..core.models import NotaDespesa, StatusLancamento
from ..core.settings_store import SettingsStore
from .widgets import DateEditFast
from .workers import LoteOrcamentoWorker, rodar_em_thread


# Limite prático pro inline_data do Gemini (base64 infla ~1.37x; o teto real
# é ~20MB de payload). Deixamos folga pra prompt + estruturas do JSON.
PDF_MAX_MB_INLINE = 18


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
    """Worker thread pro parser Gemini. Não bloqueia UI. Suporta 2 tipos
    de extração: 'nfse' (NFS-e do OTIMO) e 'dae' (guias ICMS Bahia)."""
    concluido = Signal(list)   # lista de dicts
    falhou = Signal(str)

    def __init__(self, pdf: Path, api_key: str, modelo: str, tipo_extracao: str = "nfse"):
        super().__init__()
        self._pdf = pdf
        self._api_key = api_key
        self._modelo = modelo
        self._tipo = tipo_extracao

    def run(self) -> None:
        try:
            from ..core.gemini_client import GeminiClient
            client = GeminiClient(self._api_key, self._modelo)
            if self._tipo == "dae":
                itens = client.extrair_daes(self._pdf)
            else:
                itens = client.extrair_notas_nfse(self._pdf)
            self.concluido.emit(itens)
        except BaseException as e:  # noqa: BLE001
            log.exception("ExtratorNfseThread falhou")
            self.falhou.emit(f"{type(e).__name__}: {e}")


def _carregar_cnpjs_filiais() -> dict:
    """Localiza cnpjs_filiais.json — mesma pattern do mapeamento."""
    import sys
    candidatos = [
        Path(sys.argv[0]).resolve().parent / "cnpjs_filiais.json",
        Path(sys.argv[0]).resolve().parent / "config" / "cnpjs_filiais.json",
        Path(__file__).resolve().parent.parent / "config" / "cnpjs_filiais.json",
    ]
    for c in candidatos:
        if c.exists():
            with open(c, "r", encoding="utf-8") as f:
                return json.load(f).get("cnpjs", {})
    log.error("cnpjs_filiais.json não encontrado em nenhum caminho")
    return {}


class OrcamentoPage(QWidget):
    """Página do módulo Orçamento — embarcada no main_window como seção,
    não mais dialog modal (build-99). O user relatou UX ruim: dialog abria
    janela separada 'a nada com nada'. Agora vive dentro do shell com
    sidebar + topbar, ganha log integrado e visual coerente."""
    COLS_NFSE = ["#", "Pág.", "Número NF", "Data Emissão", "Valor (R$)", "Status"]
    COLS_DAE  = ["#", "Pág.", "Nº Série DAE", "Filial", "Tipo", "Vencimento", "Valor (R$)", "Status"]

    def __init__(self, settings: SettingsStore, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setAcceptDrops(True)

        self._pdf_selecionado: Path | None = None
        self._extrator: ExtratorNfseThread | None = None
        self._templates = _carregar_templates().get("templates", {})
        self._cnpjs_filiais = _carregar_cnpjs_filiais()
        self._notas: list[NotaDespesa] = []
        self._calibracao = calib_orc_store.carregar()
        self._worker: LoteOrcamentoWorker | None = None
        self._thread: QThread | None = None

        self._montar_ui()
        self._atualizar_estado_executar()

    # ---------- UI ----------

    def _montar_ui(self) -> None:
        root = QVBoxLayout(self)
        # Padding coerente com o dashboard (mesmo 24/16 do _montar_content).
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

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
        self._combo_forn.currentIndexChanged.connect(self._on_template_mudou)
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

        # Linha 2: data lançto + resumo
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

        # Tabela — cabeçalho reconfigurado dinamicamente por template
        # (NFS-e usa 6 colunas; DAE usa 8 — adiciona Filial / Tipo / Vencimento).
        self._tabela = QTableWidget()
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.setAlternatingRowColors(True)
        self._tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tabela.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self._tabela.setShowGrid(False)
        self._tabela.itemChanged.connect(self._on_item_editado)
        self._cols_atual = self.COLS_NFSE
        self._aplicar_colunas(self.COLS_NFSE)
        root.addWidget(self._tabela, 1)

        # Rodapé
        rod = QHBoxLayout()
        self._lbl_status = QLabel("Pronto")
        self._lbl_status.setStyleSheet("color: #94A3B8; font-size: 11px;")
        rod.addWidget(self._lbl_status, 1)

        self._btn_cancelar = QPushButton("Cancelar lote")
        self._btn_cancelar.setVisible(False)
        self._btn_cancelar.clicked.connect(self._cancelar_lote)
        rod.addWidget(self._btn_cancelar)

        self._btn_calibrar = QPushButton("Calibrar tela")
        self._btn_calibrar.setProperty("ghost", True)
        self._btn_calibrar.setToolTip(
            "Calibrar posições dos campos da tela 'Notas Fiscais de Despesa'.\n"
            "Necessário na primeira execução — o TOTVS roda em RemoteApp e "
            "precisa saber onde cada campo está na tela."
        )
        self._btn_calibrar.clicked.connect(self._calibrar_tela)
        rod.addWidget(self._btn_calibrar)

        self._btn_executar = QPushButton("Executar no TOTVS")
        self._btn_executar.setProperty("brand", True)
        self._btn_executar.setMinimumWidth(200)
        self._btn_executar.setEnabled(False)
        self._btn_executar.clicked.connect(self._executar_lote)
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
        # Size check antes de aceitar. Se >18MB, orienta usuário a compactar.
        # Não embutimos compactador no app (evita puxar PyMuPDF/pikepdf ~50MB,
        # amplia superfície AV e aumenta bundle). Smallpdf/iLovePDF fazem
        # o serviço numa aba do navegador.
        try:
            tam_mb = caminho.stat().st_size / (1024 * 1024)
        except OSError:
            tam_mb = 0.0
        if tam_mb > PDF_MAX_MB_INLINE:
            resp = QMessageBox.warning(
                self,
                "PDF muito grande",
                f"O PDF tem {tam_mb:.1f} MB, mas o limite do Gemini "
                f"por request é ~{PDF_MAX_MB_INLINE} MB.\n\n"
                "Compacte o PDF antes de mandar. Opções rápidas:\n"
                "  • smallpdf.com/compress-pdf\n"
                "  • ilovepdf.com/compress_pdf\n\n"
                "Escolha 'Compressão recomendada' (não a extrema — pode "
                "perder legibilidade). Depois arraste o PDF compactado aqui.\n\n"
                "Continuar mesmo assim? (vai falhar com erro do Gemini)",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if resp == QMessageBox.No:
                return

        self._pdf_selecionado = caminho
        self._lbl_pdf.setText(f"📄 {caminho.name}  ({tam_mb:.1f} MB)")
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
        self._btn_executar.setEnabled(False)
        self._lbl_status.setText(
            "🤖 Enviando PDF pro Gemini — 1 request só, mesmo com 40 páginas…"
        )
        modelo = self.settings.get("gemini_model", "gemini-2.5-flash-lite")

        template_chave = self._combo_forn.currentData()
        template = self._templates.get(template_chave) or {}
        tipo_extracao = template.get("tipo_extracao", "nfse")

        self._extrator = ExtratorNfseThread(
            self._pdf_selecionado, api_key, modelo, tipo_extracao=tipo_extracao,
        )
        self._extrator.concluido.connect(self._on_extraido)
        self._extrator.falhou.connect(self._on_falhou)
        self._extrator.start()

    def _on_extraido(self, itens: list) -> None:
        self._btn_extrair.setEnabled(True)
        self._btn_extrair.setText("Extrair notas do PDF")

        template_chave = self._combo_forn.currentData() or ""
        template = self._templates.get(template_chave) or {}
        tipo_extracao = template.get("tipo_extracao", "nfse")
        data_lancto = self._date_lancto.date().toPython()

        self._notas = []
        if tipo_extracao == "dae":
            self._notas = self._converter_daes(itens, template_chave, data_lancto)
        else:
            self._notas = self._converter_nfse(itens, template_chave, data_lancto)

        self._popular_grid()
        self._atualizar_resumo()
        n = len(self._notas)
        self._lbl_status.setText(
            f"✓ {n} item(ns) extraído(s). Revise valores duvidosos e clique em Executar."
        )
        self._atualizar_estado_executar()

    def _converter_nfse(self, notas_dict: list, template_chave: str, data_lancto: date) -> list:
        out = []
        for i, n in enumerate(notas_dict):
            data_emi = None
            data_txt = str(n.get("data_emissao", "")).strip()
            if data_txt:
                for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
                    try:
                        data_emi = datetime.strptime(data_txt, fmt).date()
                        break
                    except ValueError:
                        pass
            out.append(NotaDespesa(
                pagina=int(n.get("pagina", i + 1)),
                numero=str(n.get("numero", "")).strip(),
                data_emissao=data_emi,
                valor=float(n.get("valor") or 0.0),
                data_lancto=data_lancto,
                template_chave=template_chave,
            ))
        return out

    def _converter_daes(self, daes: list, template_chave: str, data_lancto: date) -> list:
        out = []
        for i, d in enumerate(daes):
            venc = None
            venc_txt = str(d.get("vencimento", "")).strip()
            if venc_txt:
                for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
                    try:
                        venc = datetime.strptime(venc_txt, fmt).date()
                        break
                    except ValueError:
                        pass
            cnpj = str(d.get("cnpj", "")).strip()
            filial_info = self._cnpjs_filiais.get(cnpj)
            filial_codigo = int(filial_info["codigo"]) if filial_info else None
            filial_nome = filial_info["nome"] if filial_info else ""
            out.append(NotaDespesa(
                pagina=int(d.get("pagina", i + 1)),
                numero=str(d.get("numero_serie", "")).strip(),
                data_emissao=None,  # DAE não tem emissão explícita — RPA usa data_lancto
                valor=float(d.get("valor") or 0.0),
                data_lancto=data_lancto,
                template_chave=template_chave,
                cnpj=cnpj,
                tipo_dae=str(d.get("tipo", "")).strip() or None,
                vencimento_dae=venc,
                filial_codigo=filial_codigo,
                filial_nome=filial_nome,
            ))
        return out

    def _on_falhou(self, msg: str) -> None:
        self._btn_extrair.setEnabled(True)
        self._btn_extrair.setText("Extrair notas do PDF")
        self._lbl_status.setText("❌ Falha na extração — veja o log")
        QMessageBox.critical(
            self, "Falha na extração",
            f"Não consegui extrair as notas do PDF:\n\n{msg}\n\n"
            "Se o problema persistir, verifique se o PDF está legível "
            "(scan borrado, girado, etc.) e se não excede ~18 MB."
        )

    def _on_template_mudou(self) -> None:
        """Trocou de fornecedor no combo — se o tipo de extração é
        diferente, reconfigura o cabeçalho da grid (NFS-e vs DAE)."""
        tipo = self._tipo_atual()
        cols = self.COLS_DAE if tipo == "dae" else self.COLS_NFSE
        if cols is not self._cols_atual:
            self._aplicar_colunas(cols)
        # Ao mudar de template, limpar notas antigas evita confusão
        if self._notas:
            self._notas = []
            self._tabela.setRowCount(0)
            self._atualizar_resumo()
            self._atualizar_estado_executar()

    def _aplicar_colunas(self, cols: list) -> None:
        """Reconfigura o cabeçalho da tabela pro layout do tipo atual
        (NFS-e ou DAE). Chamado no início e sempre que o template selecionado
        muda de tipo_extracao."""
        self._cols_atual = cols
        self._tabela.setColumnCount(len(cols))
        self._tabela.setHorizontalHeaderLabels(cols)
        h = self._tabela.horizontalHeader()
        # coluna # e Pág. compactas; última (Status) compacta; resto stretch
        for i in range(len(cols)):
            if i in (0, 1, len(cols) - 1):
                h.setSectionResizeMode(i, QHeaderView.ResizeToContents)
            else:
                h.setSectionResizeMode(i, QHeaderView.Stretch)

    def _tipo_atual(self) -> str:
        chave = self._combo_forn.currentData() or ""
        tmpl = self._templates.get(chave) or {}
        return tmpl.get("tipo_extracao", "nfse")

    def _fmt_valor(self, v: float) -> str:
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _popular_grid(self) -> None:
        tipo = self._tipo_atual()
        cols = self.COLS_DAE if tipo == "dae" else self.COLS_NFSE
        if cols is not self._cols_atual:
            self._aplicar_colunas(cols)

        self._tabela.blockSignals(True)
        try:
            self._tabela.setRowCount(len(self._notas))
            for i, n in enumerate(self._notas):
                self._popular_linha(i, n, tipo)
                self._atualizar_status_celula(i)
        finally:
            self._tabela.blockSignals(False)

    def _popular_linha(self, i: int, n: NotaDespesa, tipo: str) -> None:
        it_num = QTableWidgetItem(str(i + 1))
        it_num.setFlags(it_num.flags() & ~Qt.ItemIsEditable)
        it_num.setTextAlignment(Qt.AlignCenter)
        self._tabela.setItem(i, 0, it_num)

        it_pag = QTableWidgetItem(str(n.pagina))
        it_pag.setFlags(it_pag.flags() & ~Qt.ItemIsEditable)
        it_pag.setTextAlignment(Qt.AlignCenter)
        self._tabela.setItem(i, 1, it_pag)

        # Número
        self._tabela.setItem(i, 2, QTableWidgetItem(n.numero))

        if tipo == "dae":
            # Filial
            fil_txt = f"{n.filial_codigo} — {n.filial_nome}" if n.filial_codigo else "?"
            it_f = QTableWidgetItem(fil_txt)
            it_f.setFlags(it_f.flags() & ~Qt.ItemIsEditable)
            self._tabela.setItem(i, 3, it_f)
            # Tipo
            tipo_txt = {"regime_normal": "Regime Normal",
                        "adic_fundo_pobreza": "Adic. Fundo Pobreza"}.get(n.tipo_dae or "", "?")
            it_t = QTableWidgetItem(tipo_txt)
            it_t.setFlags(it_t.flags() & ~Qt.ItemIsEditable)
            self._tabela.setItem(i, 4, it_t)
            # Vencimento
            venc_txt = n.vencimento_dae.strftime("%d/%m/%Y") if n.vencimento_dae else ""
            self._tabela.setItem(i, 5, QTableWidgetItem(venc_txt))
            # Valor
            it_val = QTableWidgetItem(self._fmt_valor(n.valor))
            it_val.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._tabela.setItem(i, 6, it_val)
        else:
            data_txt = n.data_emissao.strftime("%d/%m/%Y") if n.data_emissao else ""
            self._tabela.setItem(i, 3, QTableWidgetItem(data_txt))
            it_val = QTableWidgetItem(self._fmt_valor(n.valor))
            it_val.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._tabela.setItem(i, 4, it_val)

    def _atualizar_status_celula(self, i: int) -> None:
        n = self._notas[i]
        if n.status == StatusLancamento.SUCESSO:
            txt = "✓ OK"
        elif n.status == StatusLancamento.FALHA:
            txt = f"✗ {n.erro or 'Falha'}"
        elif n.status == StatusLancamento.IGNORADO:
            txt = f"⊘ {n.motivo_ignorado or 'Ignorada'}"
        elif n.status == StatusLancamento.EM_ANDAMENTO:
            txt = "⋯ em curso"
        else:
            if self._tipo_atual() == "dae":
                faltando = (not n.numero) or (n.filial_codigo is None) or (not n.tipo_dae) or (n.valor <= 0)
            else:
                faltando = (not n.numero) or (n.data_emissao is None) or (n.valor <= 0)
            txt = "Revisar" if faltando else "Pronta"
        it = QTableWidgetItem(txt)
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        it.setTextAlignment(Qt.AlignCenter)
        # Status vai na ÚLTIMA coluna do layout atual
        self._tabela.setItem(i, len(self._cols_atual) - 1, it)

    def _on_item_editado(self, item: QTableWidgetItem) -> None:
        """Sincroniza edições manuais da grid com self._notas. Só campos
        editáveis (número, data emissão, valor no NFSe; número, vencimento
        e valor no DAE)."""
        row = item.row()
        col = item.column()
        if row >= len(self._notas):
            return
        n = self._notas[row]
        txt = item.text().strip()
        tipo = self._tipo_atual()

        if col == 2:
            n.numero = txt
        elif tipo == "dae":
            if col == 5:  # vencimento
                for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                    try:
                        n.vencimento_dae = datetime.strptime(txt, fmt).date()
                        break
                    except ValueError:
                        pass
            elif col == 6:  # valor
                try:
                    n.valor = float(txt.replace(".", "").replace(",", "."))
                except ValueError:
                    pass
        else:
            if col == 3:  # data emissão
                for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                    try:
                        n.data_emissao = datetime.strptime(txt, fmt).date()
                        break
                    except ValueError:
                        pass
            elif col == 4:  # valor
                try:
                    n.valor = float(txt.replace(".", "").replace(",", "."))
                except ValueError:
                    pass

        self._tabela.blockSignals(True)
        try:
            self._atualizar_status_celula(row)
        finally:
            self._tabela.blockSignals(False)
        self._atualizar_resumo()

    def _atualizar_resumo(self) -> None:
        n = len(self._notas)
        total = sum(nt.valor for nt in self._notas if nt.status != StatusLancamento.IGNORADO)
        self._lbl_resumo.setText(f"{n} nota(s) · {_formatar_moeda(total)}")

    def _atualizar_estado_executar(self) -> None:
        """Habilita Executar sempre que tiver notas — a visão automática
        (build-97) tenta preencher os campos sozinha no início do lote, e
        se falhar, cai na calibração manual salva. Só bloqueia se
        NENHUM caminho estiver disponível: sem visão E sem calib salva."""
        tem_notas = len(self._notas) > 0
        self._btn_executar.setEnabled(tem_notas)
        if not tem_notas:
            self._btn_executar.setToolTip("Extraia notas de um PDF primeiro.")
        elif not self._calibracao.esta_completa():
            self._btn_executar.setToolTip(
                "Execução vai tentar auto-detecção visual da tela TOTVS.\n"
                "Se falhar, use 'Calibrar tela' pra calibrar manualmente."
            )
        else:
            self._btn_executar.setToolTip(
                "Executa o lote no TOTVS. Tecla END aborta emergencial."
            )

    # ---------- Execução do lote ----------

    def _executar_lote(self) -> None:
        # Só lança itens com dados válidos e ainda pendentes.
        tipo = self._tipo_atual()
        if tipo == "dae":
            pendentes = [
                (i, n) for i, n in enumerate(self._notas)
                if n.status == StatusLancamento.PENDENTE
                and n.numero and n.filial_codigo and n.tipo_dae and n.valor > 0
            ]
            criterio = "número da DAE, CNPJ resolvido (filial), tipo (regime normal / adic pobreza) e valor"
        else:
            pendentes = [
                (i, n) for i, n in enumerate(self._notas)
                if n.status == StatusLancamento.PENDENTE
                and n.numero and n.data_emissao and n.valor > 0
            ]
            criterio = "número, data de emissão e valor"
        if not pendentes:
            QMessageBox.information(
                self, "Nada pra lançar",
                f"Não há itens pendentes com dados completos.\n\n"
                f"Preencha {criterio} pra cada linha 'Revisar' antes de executar."
            )
            return

        template_chave = self._combo_forn.currentData()
        template = self._templates.get(template_chave)
        if not template:
            QMessageBox.critical(
                self, "Template não encontrado",
                f"O template '{template_chave}' não está no mapeamento_orcamento.json."
            )
            return

        resp = QMessageBox.question(
            self,
            "Confirmar execução",
            f"Lançar {len(pendentes)} nota(s) no TOTVS usando o template "
            f"'{template_chave}'?\n\n"
            "• Duplicadas serão IGNORADAS (nunca inventamos número).\n"
            "• Tecla END aborta o lote a qualquer momento.\n"
            "• O TOTVS deve estar aberto na tela 'Notas Fiscais de Despesa'.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return

        # Atualiza data_lancto de todas as notas com o valor atual do campo
        data_lancto_atual = self._date_lancto.date().toPython()
        for _, n in pendentes:
            n.data_lancto = data_lancto_atual

        notas_lote = [n for _, n in pendentes]

        settings_dict = {
            "delays": self.settings.get("delays") or {},
            "rpa": self.settings.get("rpa") or {},
        }

        self._worker = LoteOrcamentoWorker(
            notas_lote, template, settings_dict, self._calibracao,
        )
        self._worker.log_line.connect(self._on_log_worker)
        self._worker.progresso.connect(self._on_progresso_worker)
        self._worker.nota_atualizada.connect(self._on_nota_atualizada)
        self._worker.finished.connect(self._on_finished_worker)
        self._worker.error.connect(self._on_erro_worker)

        self._btn_executar.setEnabled(False)
        self._btn_extrair.setEnabled(False)
        self._btn_cancelar.setVisible(True)
        self._lbl_status.setText("Executando… (END = emergência)")

        self._thread = rodar_em_thread(self._worker)

    def _calibrar_tela(self) -> None:
        from .calibracao_dialog import CalibracaoDialog
        from ..core.calibracao_orcamento import CAMPOS as CAMPOS_ORC, CAMPOS_OPCIONAIS as OPC_ORC

        dlg = CalibracaoDialog(
            self._calibracao,
            parent=self,
            titulo_janela_default="Orçamento",
            campos_obrigatorios=CAMPOS_ORC,
            campos_opcionais=OPC_ORC,
            rotulo_tela="Notas Fiscais de Despesa",
        )
        if dlg.exec() == QDialog.Accepted:
            self._calibracao = dlg.calibracao()
            calib_orc_store.salvar(self._calibracao)
            self._atualizar_estado_executar()
            self._lbl_status.setText(
                f"✓ Calibração salva ({len(self._calibracao.campos)} campos)."
            )

    def _cancelar_lote(self) -> None:
        if self._worker is not None:
            self._worker.cancelar()
            self._btn_cancelar.setEnabled(False)
            self._lbl_status.setText("Cancelando…")

    def _on_log_worker(self, msg: str) -> None:
        self._lbl_status.setText(msg[:180])

    def _on_progresso_worker(self, i: int, total: int, msg: str) -> None:
        self._lbl_status.setText(f"[{i+1}/{total}] {msg}")

    def _on_nota_atualizada(self, i: int) -> None:
        # Encontra o índice na tabela — worker recebe a sub-lista de pendentes,
        # mas mutamos os mesmos objetos NotaDespesa referenciados em self._notas.
        # Basta redesenhar todos os status.
        self._tabela.blockSignals(True)
        try:
            for j in range(len(self._notas)):
                self._atualizar_status_celula(j)
        finally:
            self._tabela.blockSignals(False)

    def _on_finished_worker(self, sucessos: int, falhas: int, ignoradas: int) -> None:
        self._btn_executar.setEnabled(True)
        self._btn_extrair.setEnabled(True)
        self._btn_cancelar.setEnabled(True)
        self._btn_cancelar.setVisible(False)
        total = sucessos + falhas + ignoradas
        self._lbl_status.setText(
            f"Concluído — {sucessos} OK · {falhas} falhas · {ignoradas} ignoradas (de {total})"
        )
        QMessageBox.information(
            self, "Lote concluído",
            f"Lote finalizado:\n\n"
            f"  ✓ Sucesso: {sucessos}\n"
            f"  ✗ Falhas: {falhas}\n"
            f"  ⊘ Ignoradas (já lançadas): {ignoradas}\n\n"
            "Notas com falha ficam na grid pra você conferir e refazer manualmente."
        )

    def _on_erro_worker(self, msg: str) -> None:
        self._btn_executar.setEnabled(True)
        self._btn_extrair.setEnabled(True)
        self._btn_cancelar.setVisible(False)
        self._lbl_status.setText("Erro — veja o diálogo")
        QMessageBox.critical(self, "Erro no lote Orçamento", msg)

    # ---------- Ciclo de vida ----------

    def encerrar_threads(self) -> None:
        """Chamada pelo main_window ao fechar. Cancela lote em curso."""
        if self._worker is not None:
            try:
                self._worker.cancelar()
            except Exception:  # noqa: BLE001
                pass


# Compat: código antigo pode importar OrcamentoDialog — apontamos pra Page.
OrcamentoDialog = OrcamentoPage
