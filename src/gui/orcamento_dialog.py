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

from PySide6.QtCore import QDate, QEasingCurve, QPropertyAnimation, Qt, QThread, Signal
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
        self.setMinimumSize(1080, 720)
        self.setAcceptDrops(True)

        self._pdf_selecionado: Path | None = None
        self._extrator: ExtratorNfseThread | None = None
        self._templates = _carregar_templates().get("templates", {})
        self._notas: list[NotaDespesa] = []
        self._calibracao = calib_orc_store.carregar()
        self._worker: LoteOrcamentoWorker | None = None
        self._thread: QThread | None = None

        self._montar_ui()
        self._atualizar_estado_executar()

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

        # Tabela
        self._tabela = QTableWidget()
        self._tabela.setColumnCount(len(self.COLS))
        self._tabela.setHorizontalHeaderLabels(self.COLS)
        self._tabela.verticalHeader().setVisible(False)
        self._tabela.setAlternatingRowColors(True)
        self._tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tabela.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self._tabela.setShowGrid(False)
        self._tabela.itemChanged.connect(self._on_item_editado)
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

        btn_fechar = QPushButton("Fechar")
        btn_fechar.clicked.connect(self.reject)
        rod.addWidget(btn_fechar)

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

        self._extrator = ExtratorNfseThread(self._pdf_selecionado, api_key, modelo)
        self._extrator.concluido.connect(self._on_extraido)
        self._extrator.falhou.connect(self._on_falhou)
        self._extrator.start()

    def _on_extraido(self, notas_dict: list) -> None:
        self._btn_extrair.setEnabled(True)
        self._btn_extrair.setText("Extrair notas do PDF")

        # Converte pra NotaDespesa
        template_chave = self._combo_forn.currentData() or ""
        data_lancto = self._date_lancto.date().toPython()
        self._notas = []
        for i, n in enumerate(notas_dict):
            data_emi = None
            data_txt = str(n.get("data_emissao", "")).strip()
            if data_txt:
                try:
                    data_emi = datetime.strptime(data_txt, "%Y-%m-%d").date()
                except ValueError:
                    try:
                        data_emi = datetime.strptime(data_txt, "%d/%m/%Y").date()
                    except ValueError:
                        pass
            self._notas.append(NotaDespesa(
                pagina=int(n.get("pagina", i + 1)),
                numero=str(n.get("numero", "")).strip(),
                data_emissao=data_emi,
                valor=float(n.get("valor") or 0.0),
                data_lancto=data_lancto,
                template_chave=template_chave,
            ))

        self._popular_grid()
        self._atualizar_resumo()
        n = len(self._notas)
        self._lbl_status.setText(
            f"✓ {n} nota(s) extraída(s). Revise valores duvidosos e clique em Executar."
        )
        self._atualizar_estado_executar()

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

    def _popular_grid(self) -> None:
        self._tabela.blockSignals(True)
        try:
            self._tabela.setRowCount(len(self._notas))
            for i, n in enumerate(self._notas):
                it_num = QTableWidgetItem(str(i + 1))
                it_num.setFlags(it_num.flags() & ~Qt.ItemIsEditable)
                it_num.setTextAlignment(Qt.AlignCenter)
                self._tabela.setItem(i, 0, it_num)

                it_pag = QTableWidgetItem(str(n.pagina))
                it_pag.setFlags(it_pag.flags() & ~Qt.ItemIsEditable)
                it_pag.setTextAlignment(Qt.AlignCenter)
                self._tabela.setItem(i, 1, it_pag)

                self._tabela.setItem(i, 2, QTableWidgetItem(n.numero))

                data_txt = n.data_emissao.strftime("%d/%m/%Y") if n.data_emissao else ""
                self._tabela.setItem(i, 3, QTableWidgetItem(data_txt))

                it_val = QTableWidgetItem(
                    f"{n.valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                )
                it_val.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._tabela.setItem(i, 4, it_val)

                self._atualizar_status_celula(i)
        finally:
            self._tabela.blockSignals(False)

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
            faltando = (not n.numero) or (n.data_emissao is None) or (n.valor <= 0)
            txt = "Revisar" if faltando else "Pronta"
        it = QTableWidgetItem(txt)
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        it.setTextAlignment(Qt.AlignCenter)
        self._tabela.setItem(i, 5, it)

    def _on_item_editado(self, item: QTableWidgetItem) -> None:
        """Aceita edições manuais em número, data e valor. Mantém `self._notas`
        em sincronia com a grid — o worker lê `self._notas`, não a grid."""
        row = item.row()
        col = item.column()
        if row >= len(self._notas):
            return
        n = self._notas[row]
        txt = item.text().strip()
        if col == 2:
            n.numero = txt
        elif col == 3:
            try:
                n.data_emissao = datetime.strptime(txt, "%d/%m/%Y").date()
            except ValueError:
                try:
                    n.data_emissao = datetime.strptime(txt, "%Y-%m-%d").date()
                except ValueError:
                    n.data_emissao = None
        elif col == 4:
            try:
                normalizado = txt.replace(".", "").replace(",", ".")
                n.valor = float(normalizado)
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
        """Habilita o botão Executar se tiver notas prontas E calibração OK."""
        tem_notas = len(self._notas) > 0
        calib_ok = self._calibracao.esta_completa()
        self._btn_executar.setEnabled(tem_notas and calib_ok)
        if not calib_ok:
            self._btn_executar.setToolTip(
                "Calibração da tela Orçamento pendente.\n"
                "Faltam: " + ", ".join(self._calibracao.falta_calibrar()[:5])
                + ("..." if len(self._calibracao.falta_calibrar()) > 5 else "")
            )
        elif not tem_notas:
            self._btn_executar.setToolTip("Extraia notas de um PDF primeiro.")
        else:
            self._btn_executar.setToolTip(
                "Executa o lote no TOTVS. Tecla END aborta emergencial."
            )

    # ---------- Execução do lote ----------

    def _executar_lote(self) -> None:
        # Só lança notas com dados válidos e não já processadas
        pendentes = [
            (i, n) for i, n in enumerate(self._notas)
            if n.status == StatusLancamento.PENDENTE
            and n.numero and n.data_emissao and n.valor > 0
        ]
        if not pendentes:
            QMessageBox.information(
                self, "Nada pra lançar",
                "Não há notas pendentes com dados completos.\n\n"
                "Preencha número, data de emissão e valor pra cada linha "
                "'Revisar' antes de executar."
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

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker is not None:
            try:
                self._worker.cancelar()
            except Exception:  # noqa: BLE001
                pass
        super().closeEvent(event)
