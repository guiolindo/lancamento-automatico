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
    QHeaderView, QInputDialog, QLabel, QMenu, QMessageBox, QPlainTextEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
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
    """Worker thread pro parser Gemini. Suporta NFS-e (com ou sem
    anotação a caneta) e DAE Bahia."""
    concluido = Signal(list)
    falhou = Signal(str)

    def __init__(
        self, pdf: Path, api_key: str, modelo: str,
        tipo_extracao: str = "nfse",
        extrair_caneta: bool = False,
    ):
        super().__init__()
        self._pdf = pdf
        self._api_key = api_key
        self._modelo = modelo
        self._tipo = tipo_extracao
        self._caneta = extrair_caneta

    def run(self) -> None:
        try:
            from ..core.gemini_client import GeminiClient
            client = GeminiClient(self._api_key, self._modelo)
            if self._tipo == "dae":
                itens = client.extrair_daes(self._pdf)
            else:
                itens = client.extrair_notas_nfse(self._pdf, extrair_anotacao_caneta=self._caneta)
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
    COLS_NFSE        = ["#", "Pág.", "Número NF", "Data Emissão", "Valor (R$)", "Status"]
    COLS_NFSE_CANETA = ["#", "Pág.", "Número NF", "Data", "Emissor", "Caneta (destino)", "Valor (R$)", "Status"]
    COLS_DAE         = ["#", "Pág.", "Nº Série DAE", "Filial", "Tipo", "Vencimento", "Valor (R$)", "Status"]

    def __init__(self, settings: SettingsStore, main_window=None, parent=None):
        super().__init__(parent)
        self.settings = settings
        # main_window opcional — quando presente, o Orçamento reusa a
        # lógica de "detectar tela do TOTVS e mover pra outra" +
        # "restaurar após lote" que já existia no dashboard. Antes o
        # Orçamento ignorava isso e o usuário reportou que a janela do
        # app não saía da tela do TOTVS durante a execução.
        self._main_window = main_window
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

        sub = QLabel("Notas por fornecedor (Ótimo, Pluxee, DAE). Extraia do PDF e execute no TOTVS.")
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
        # Menu contextual (botão direito) — mesma pattern da PreviewTable
        # do Novo Lote.
        self._tabela.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tabela.customContextMenuRequested.connect(self._menu_contexto_linha)
        self._cols_atual = self.COLS_NFSE
        self._aplicar_colunas(self.COLS_NFSE)

        # Área principal: grid (dominante) + painel Atividade à direita.
        # Coerente com o dashboard do Novo Lote (main_window._card_atividade).
        area = QHBoxLayout()
        area.setSpacing(12)
        area.addWidget(self._tabela, 3)
        area.addWidget(self._card_atividade(), 0)
        root.addLayout(area, 1)

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
            "Marcar a posição de cada campo na tela 'Notas Fiscais de Despesa' "
            "manualmente. Rede de segurança caso a detecção automática erre."
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

    def _card_atividade(self) -> QFrame:
        """Painel de log ao lado da grid — mesma pattern do dashboard."""
        card = QFrame()
        card.setProperty("card", True)
        card.setMinimumWidth(280)
        card.setMaximumWidth(360)
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(8)
        cab = QHBoxLayout()
        h2 = QLabel("Atividade")
        h2.setProperty("h2", True)
        cab.addWidget(h2)
        cab.addStretch(1)
        btn_limpar = QPushButton("×")
        btn_limpar.setProperty("iconOnly", True)
        btn_limpar.setToolTip("Limpar log")
        btn_limpar.clicked.connect(lambda: self._log.clear())
        cab.addWidget(btn_limpar)
        v.addLayout(cab)
        self._log = QPlainTextEdit()
        self._log.setObjectName("LogConsole")
        self._log.setReadOnly(True)
        v.addWidget(self._log, 1)
        return card

    def _log_line(self, msg: str) -> None:
        try:
            self._log.appendPlainText(f"[{datetime.now():%H:%M:%S}] {msg}")
        except Exception:  # noqa: BLE001
            pass
        try:
            log.info(msg)
        except Exception:  # noqa: BLE001
            pass

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
                f"O PDF tem {tam_mb:.1f} MB. Limite do Gemini: {PDF_MAX_MB_INLINE} MB.\n\n"
                "Compacte antes (smallpdf.com/compress-pdf ou ilovepdf.com) e "
                "arraste o compactado aqui.\n\n"
                "Continuar mesmo assim?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if resp == QMessageBox.No:
                return

        self._pdf_selecionado = caminho
        self._lbl_pdf.setText(f"{caminho.name}  ({tam_mb:.1f} MB)")
        self._btn_extrair.setEnabled(True)
        self.settings.set("ultima_pasta_upload", str(caminho.parent))
        self._lbl_status.setText(f"{caminho.name} · clique Extrair.")

    def _extrair(self) -> None:
        if self._pdf_selecionado is None:
            return
        api_key = self.settings.get_gemini_api_key()
        if not api_key:
            QMessageBox.warning(
                self, "Chave ausente",
                "Configure a chave da API Gemini em Config."
            )
            return

        self._btn_extrair.setEnabled(False)
        self._btn_extrair.setText("Extraindo…")
        self._btn_executar.setEnabled(False)
        self._lbl_status.setText("Enviando PDF pro Gemini…")
        modelo = self.settings.get("gemini_model", "gemini-2.5-flash-lite")

        template_chave = self._combo_forn.currentData()
        template = self._templates.get(template_chave) or {}
        tipo_extracao = template.get("tipo_extracao", "nfse")
        extrair_caneta = bool(template.get("extrair_anotacao_caneta", False))
        self._log_line(f"→ Extraindo {self._pdf_selecionado.name} (template {template_chave})")

        self._extrator = ExtratorNfseThread(
            self._pdf_selecionado, api_key, modelo,
            tipo_extracao=tipo_extracao,
            extrair_caneta=extrair_caneta,
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
        self._lbl_status.setText(f"{n} lançamentos prontos.")
        self._atualizar_estado_executar()

    def _converter_nfse(self, notas_dict: list, template_chave: str, data_lancto: date) -> list:
        template = self._templates.get(template_chave) or {}
        cnpj_esperado = "".join(c for c in str(template.get("cnpj_esperado", "")) if c.isdigit())
        validar_tomador = bool(template.get("validar_cnpj_tomador", False))

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

            cnpj_prest = str(n.get("cnpj_prestador", "")).strip()
            cnpj_tom   = str(n.get("cnpj_tomador", "")).strip()
            anot       = str(n.get("anotacao_caneta", "")).strip()

            # Resolve filial de emissão a partir do CNPJ tomador
            fil_emi_info = self._cnpjs_filiais.get(cnpj_tom) if cnpj_tom else None
            fil_emi_cod  = int(fil_emi_info["codigo"]) if fil_emi_info else None
            fil_emi_nome = fil_emi_info["nome"] if fil_emi_info else ""

            # Fuzzy match do rabisco → filial da caneta
            fil_cnt_cod, fil_cnt_nome = self._resolver_filial_por_texto(anot) if anot else (None, "")

            nota = NotaDespesa(
                pagina=int(n.get("pagina", i + 1)),
                numero=str(n.get("numero", "")).strip(),
                data_emissao=data_emi,
                valor=float(n.get("valor") or 0.0),
                data_lancto=data_lancto,
                template_chave=template_chave,
                cnpj_prestador=cnpj_prest,
                cnpj_tomador=cnpj_tom,
                filial_emissao_codigo=fil_emi_cod,
                filial_emissao_nome=fil_emi_nome,
                anotacao_caneta=anot,
                filial_caneta_codigo=fil_cnt_cod,
                filial_caneta_nome=fil_cnt_nome,
            )

            # Validação de CNPJ: se template declara `cnpj_esperado` e a
            # nota é de outro prestador, marca como IGNORADO e explica.
            # NÃO tentamos lançar — é fornecedor errado no lote.
            if cnpj_esperado and cnpj_prest and cnpj_prest != cnpj_esperado:
                nota.status = StatusLancamento.IGNORADO
                nota.motivo_ignorado = f"CNPJ do prestador ({cnpj_prest}) não bate com o fornecedor {template_chave}"

            # Validação do TOMADOR (build-121): se o template pede, o
            # CNPJ tomador tem que estar cadastrado em `cnpjs_filiais.json`.
            # Aplicado só se a nota ainda não foi barrada pelo prestador.
            elif validar_tomador:
                from ..core.cnpj_utils import TomadorMatch, classificar_tomador
                cls = classificar_tomador(cnpj_tom, self._cnpjs_filiais)
                if cls == TomadorMatch.AUSENTE:
                    nota.status = StatusLancamento.IGNORADO
                    nota.motivo_ignorado = "CNPJ do tomador não veio na extração — não é possível validar a filial de destino"
                elif cls == TomadorMatch.RAIZ_GRUPO:
                    nota.status = StatusLancamento.IGNORADO
                    nota.motivo_ignorado = f"Filial não cadastrada (CNPJ {cnpj_tom} é do grupo, mas não está em cnpjs_filiais.json). Adicione a filial e reprocesse."
                elif cls == TomadorMatch.OUTRA_EMPRESA:
                    nota.status = StatusLancamento.IGNORADO
                    nota.motivo_ignorado = f"CNPJ do tomador ({cnpj_tom}) é de outra empresa — nota chegou por engano"
                # EXATO: passa direto, filial_emissao_codigo já foi resolvido

            out.append(nota)
        return out

    def _resolver_filial_por_texto(self, texto: str) -> tuple[int | None, str]:
        """Fuzzy match do texto (rabisco de caneta) contra nome canônico
        E aliases de cada filial no cnpjs_filiais.json.

        Ex.: 'Linha Verde' bateria mal contra 'Serra Verde' (score ~50)
        se procurasse só o nome — mas 'Linha Verde' aparece como alias
        da filial 16 e casa em 100 no alias. Retornamos o nome canônico
        pra observação/UI sempre.
        """
        if not texto or not self._cnpjs_filiais:
            return None, ""
        try:
            from rapidfuzz import fuzz, process
        except ImportError:
            log.warning("rapidfuzz indisponível — fuzzy match de filial pulado")
            return None, ""

        # Constrói lista de (chave_de_match, código, nome_canonico).
        # Cada filial contribui com 1 entrada pelo nome + N pelos aliases.
        entries: list[tuple[str, int, str]] = []
        for info in self._cnpjs_filiais.values():
            nome_can = str(info.get("nome", "")).strip()
            codigo = int(info.get("codigo", 0))
            if nome_can:
                entries.append((nome_can, codigo, nome_can))
            for alias in info.get("aliases", []) or []:
                a = str(alias).strip()
                if a:
                    entries.append((a, codigo, nome_can))

        chaves = [e[0] for e in entries]
        # WRatio como scorer base + reranking pra desambiguar LOJA vs CD.
        # O TOTVS tem várias filiais cujo CD compartilha nome com uma loja
        # (Feira de Santana vs CD Feira de Santana, Ribeirão das Neves
        # vs CD Ribeirão das Neves). Se o texto escrito à mão tem "CD",
        # queremos preferir a filial que TAMBÉM tem "CD"; se não tem,
        # queremos a loja. WRatio sozinho errava (ex.: 'cd feira de
        # santana' dava score 80 pra 'Feira de Santana' e 79 pro CD).
        tem_cd_texto = self._tem_cd_prefix(texto)
        candidatos_scored: list[tuple[str, float, int]] = []
        for chave, score, idx in process.extract(texto, chaves, scorer=fuzz.WRatio, limit=10):
            nome_can = entries[idx][2]
            eh_cd_alvo = self._tem_cd_prefix(nome_can)
            # Boost se prefixo bate, penalidade se cruza (LOJA<->CD)
            ajuste = +15 if tem_cd_texto == eh_cd_alvo else -20
            candidatos_scored.append((chave, min(100.0, max(0.0, score + ajuste)), idx))
        if not candidatos_scored:
            return None, ""
        candidatos_scored.sort(key=lambda x: -x[1])
        chave_match, score, idx = candidatos_scored[0]
        if score < 70:
            log.info("Fuzzy caneta: '%s' → melhor '%s' (%.0f) descartado (<70)",
                     texto, chave_match, score)
            return None, ""
        codigo, nome_can = entries[idx][1], entries[idx][2]
        log.info("Fuzzy caneta: '%s' → '%s' → %s (código %d, score %.0f)",
                 texto, chave_match, nome_can, codigo, score)
        return codigo, nome_can

    @staticmethod
    def _tem_cd_prefix(texto: str) -> bool:
        """True se o texto começa com 'CD' seguido de espaço/pontuação
        (case-insensitive). 'CDX' não conta — precisa ser palavra."""
        t = texto.strip().lower()
        return t.startswith("cd ") or t == "cd" or t.startswith("cd-") or t.startswith("cd.")

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
        self._lbl_status.setText("Falha na extração.")
        self._log_line(f"XX Falha na extração: {msg[:120]}")
        QMessageBox.critical(
            self, "Falha na extração",
            f"{msg}\n\n"
            "Confira se o PDF está legível e abaixo de 18 MB."
        )

    def _on_template_mudou(self) -> None:
        """Trocou de fornecedor no combo — reconfigura cabeçalho da grid."""
        cols = self._layout_atual()
        if cols is not self._cols_atual:
            self._aplicar_colunas(cols)
        # Limpa notas antigas ao mudar de fornecedor pra não misturar
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

    def _layout_atual(self) -> list:
        """Escolhe o cabeçalho da tabela: NFS-e simples, NFS-e com caneta
        (Pluxee) ou DAE."""
        chave = self._combo_forn.currentData() or ""
        tmpl = self._templates.get(chave) or {}
        tipo = tmpl.get("tipo_extracao", "nfse")
        if tipo == "dae":
            return self.COLS_DAE
        if tmpl.get("extrair_anotacao_caneta"):
            return self.COLS_NFSE_CANETA
        return self.COLS_NFSE

    def _fmt_valor(self, v: float) -> str:
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _popular_grid(self) -> None:
        cols = self._layout_atual()
        if cols is not self._cols_atual:
            self._aplicar_colunas(cols)

        self._tabela.blockSignals(True)
        try:
            self._tabela.setRowCount(len(self._notas))
            for i, n in enumerate(self._notas):
                self._popular_linha(i, n)
                self._atualizar_status_celula(i)
        finally:
            self._tabela.blockSignals(False)

    def _popular_linha(self, i: int, n: NotaDespesa) -> None:
        cols = self._cols_atual
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

        if cols is self.COLS_DAE:
            fil_txt = f"{n.filial_codigo} — {n.filial_nome}" if n.filial_codigo else "?"
            it_f = QTableWidgetItem(fil_txt); it_f.setFlags(it_f.flags() & ~Qt.ItemIsEditable)
            self._tabela.setItem(i, 3, it_f)
            tipo_txt = {"regime_normal": "Regime Normal",
                        "adic_fundo_pobreza": "Adic. Fundo Pobreza"}.get(n.tipo_dae or "", "?")
            it_t = QTableWidgetItem(tipo_txt); it_t.setFlags(it_t.flags() & ~Qt.ItemIsEditable)
            self._tabela.setItem(i, 4, it_t)
            venc_txt = n.vencimento_dae.strftime("%d/%m/%Y") if n.vencimento_dae else ""
            self._tabela.setItem(i, 5, QTableWidgetItem(venc_txt))
            it_val = QTableWidgetItem(self._fmt_valor(n.valor))
            it_val.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._tabela.setItem(i, 6, it_val)
        elif cols is self.COLS_NFSE_CANETA:
            data_txt = n.data_emissao.strftime("%d/%m/%Y") if n.data_emissao else ""
            self._tabela.setItem(i, 3, QTableWidgetItem(data_txt))
            emi_txt = f"{n.filial_emissao_codigo} — {n.filial_emissao_nome}" if n.filial_emissao_codigo else "?"
            it_e = QTableWidgetItem(emi_txt); it_e.setFlags(it_e.flags() & ~Qt.ItemIsEditable)
            self._tabela.setItem(i, 4, it_e)
            # Coluna caneta editável: mostra "20 — Luis Eduardo…" quando
            # resolveu, ou o rabisco bruto pra revisão manual quando não.
            if n.filial_caneta_codigo:
                cnt_txt = f"{n.filial_caneta_codigo} — {n.filial_caneta_nome}"
            else:
                cnt_txt = n.anotacao_caneta or ""
            self._tabela.setItem(i, 5, QTableWidgetItem(cnt_txt))
            it_val = QTableWidgetItem(self._fmt_valor(n.valor))
            it_val.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._tabela.setItem(i, 6, it_val)
        else:  # COLS_NFSE simples
            data_txt = n.data_emissao.strftime("%d/%m/%Y") if n.data_emissao else ""
            self._tabela.setItem(i, 3, QTableWidgetItem(data_txt))
            it_val = QTableWidgetItem(self._fmt_valor(n.valor))
            it_val.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._tabela.setItem(i, 4, it_val)

    def _atualizar_status_celula(self, i: int) -> None:
        n = self._notas[i]
        cols = self._cols_atual
        if n.status == StatusLancamento.SUCESSO:
            txt = "OK"
        elif n.status == StatusLancamento.FALHA:
            txt = f"Falha: {n.erro or ''}"
        elif n.status == StatusLancamento.IGNORADO:
            txt = n.motivo_ignorado or "Ignorada"
        elif n.status == StatusLancamento.EM_ANDAMENTO:
            txt = "Em curso"
        else:
            if cols is self.COLS_DAE:
                faltando = (not n.numero) or (n.filial_codigo is None) or (not n.tipo_dae) or (n.valor <= 0)
            elif cols is self.COLS_NFSE_CANETA:
                faltando = ((not n.numero) or (n.data_emissao is None) or (n.valor <= 0)
                            or n.filial_emissao_codigo is None or n.filial_caneta_codigo is None)
            else:
                faltando = (not n.numero) or (n.data_emissao is None) or (n.valor <= 0)
            txt = "Revisar" if faltando else "Pronta"
        it = QTableWidgetItem(txt)
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        it.setTextAlignment(Qt.AlignCenter)
        self._tabela.setItem(i, len(cols) - 1, it)

    def _on_item_editado(self, item: QTableWidgetItem) -> None:
        """Sincroniza edições manuais da grid com self._notas."""
        row = item.row()
        col = item.column()
        if row >= len(self._notas):
            return
        n = self._notas[row]
        txt = item.text().strip()
        cols = self._cols_atual

        if col == 2:
            n.numero = txt
        elif cols is self.COLS_DAE:
            if col == 5:  # vencimento
                for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                    try:
                        n.vencimento_dae = datetime.strptime(txt, fmt).date()
                        break
                    except ValueError:
                        pass
            elif col == 6:
                try:
                    n.valor = float(txt.replace(".", "").replace(",", "."))
                except ValueError:
                    pass
        elif cols is self.COLS_NFSE_CANETA:
            if col == 3:  # data emissão
                for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                    try:
                        n.data_emissao = datetime.strptime(txt, fmt).date()
                        break
                    except ValueError:
                        pass
            elif col == 5:  # Caneta — refaz fuzzy match ou aceita "codigo — nome" digitado
                # Se o texto começa com número + separador, extrai código:
                import re
                m = re.match(r"^\s*(\d+)\s*[—-]\s*(.*)$", txt)
                if m:
                    n.filial_caneta_codigo = int(m.group(1))
                    n.filial_caneta_nome = m.group(2).strip()
                else:
                    n.anotacao_caneta = txt
                    n.filial_caneta_codigo, n.filial_caneta_nome = self._resolver_filial_por_texto(txt)
            elif col == 6:
                try:
                    n.valor = float(txt.replace(".", "").replace(",", "."))
                except ValueError:
                    pass
        else:  # COLS_NFSE simples
            if col == 3:
                for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                    try:
                        n.data_emissao = datetime.strptime(txt, fmt).date()
                        break
                    except ValueError:
                        pass
            elif col == 4:
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
            self._btn_executar.setToolTip("Extraia um PDF antes.")
        elif not self._calibracao.esta_completa():
            self._btn_executar.setToolTip(
                "Vai tentar detectar os campos por visão. Se falhar, "
                "use 'Calibrar tela'."
            )
        else:
            self._btn_executar.setToolTip("END aborta o lote.")

    # ---------- Execução do lote ----------

    def _executar_lote(self) -> None:
        # Só lança itens com dados válidos e ainda pendentes.
        cols = self._cols_atual
        if cols is self.COLS_DAE:
            pendentes = [
                (i, n) for i, n in enumerate(self._notas)
                if n.status == StatusLancamento.PENDENTE
                and n.numero and n.filial_codigo and n.tipo_dae and n.valor > 0
            ]
            criterio = "número, CNPJ resolvido, tipo e valor"
        elif cols is self.COLS_NFSE_CANETA:
            pendentes = [
                (i, n) for i, n in enumerate(self._notas)
                if n.status == StatusLancamento.PENDENTE
                and n.numero and n.data_emissao and n.valor > 0
                and n.filial_emissao_codigo and n.filial_caneta_codigo
            ]
            criterio = "número, data, valor, filial de emissão e filial da caneta"
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
                f"Preencha {criterio} nas linhas marcadas 'Revisar'."
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
            "Executar lote",
            f"Lançar {len(pendentes)} nota(s) com o template '{template_chave}'?\n\n"
            "Duplicadas ficam IGNORADAS. END aborta. "
            "Deixe o TOTVS aberto em 'Notas Fiscais de Despesa'.",
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
        self._lbl_status.setText("Executando. END aborta.")
        self._log_line(f">> Iniciando lote — {len(pendentes)} nota(s) do template {template_chave}")

        # Multi-monitor: se a janela do Auto Conferi está na MESMA tela do
        # TOTVS, o main_window move ela pra outra tela pra o operador ver
        # o que está acontecendo (user reportou build-104). Em mono-monitor
        # a lógica atual do main_window devolve geometry pra HUD; aqui
        # não usamos HUD (o log já vive dentro da própria página do
        # Orçamento), mas a chamada é idempotente e só move se precisar.
        if self._main_window is not None:
            try:
                self._main_window._preparar_janela_para_execucao()
            except Exception:  # noqa: BLE001
                log.exception("Falha preparando janela pro lote Orçamento")

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
                f"Calibração salva ({len(self._calibracao.campos)} campos)."
            )
            self._log_line(f"OK Calibração salva ({len(self._calibracao.campos)} campos)")

    def _cancelar_lote(self) -> None:
        if self._worker is not None:
            self._worker.cancelar()
            self._btn_cancelar.setEnabled(False)
            self._lbl_status.setText("Cancelando…")

    def _on_log_worker(self, msg: str) -> None:
        self._lbl_status.setText(msg[:180])
        self._log_line(msg)

    def _on_progresso_worker(self, i: int, total: int, msg: str) -> None:
        linha = f"[{i+1}/{total}] {msg}"
        self._lbl_status.setText(linha)
        self._log_line(linha)

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

    # ---------- Menu contextual da grid (botão direito) ----------

    def _menu_contexto_linha(self, pos) -> None:
        row = self._tabela.rowAt(pos.y())
        if row < 0 or row >= len(self._notas):
            return
        self._tabela.selectRow(row)
        n = self._notas[row]
        cols = self._cols_atual

        menu = QMenu(self._tabela)
        act_edit_num  = menu.addAction("Editar número da nota…")
        act_edit_val  = menu.addAction("Editar valor…")
        if cols is self.COLS_DAE:
            act_edit_data = menu.addAction("Editar vencimento…")
            act_edit_fil  = menu.addAction("Editar filial…")
            act_edit_can  = None
        elif cols is self.COLS_NFSE_CANETA:
            act_edit_data = menu.addAction("Editar data de emissão…")
            act_edit_fil  = None
            act_edit_can  = menu.addAction("Editar filial da caneta…")
        else:
            act_edit_data = menu.addAction("Editar data de emissão…")
            act_edit_fil  = None
            act_edit_can  = None
        menu.addSeparator()
        act_reset  = menu.addAction("Marcar como pendente (reprocessar)")
        act_reset.setEnabled(n.status != StatusLancamento.EM_ANDAMENTO)
        act_remover = menu.addAction("Remover deste lote")
        act_remover.setEnabled(n.status != StatusLancamento.EM_ANDAMENTO)

        chosen = menu.exec(self._tabela.viewport().mapToGlobal(pos))
        if chosen is None:
            return

        if chosen is act_edit_num:
            novo, ok = QInputDialog.getText(self, "Número da nota", "Número:", text=n.numero)
            if ok:
                n.numero = novo.strip()
        elif chosen is act_edit_val:
            novo, ok = QInputDialog.getDouble(
                self, "Valor", "Valor (R$):", value=n.valor, decimals=2, min=0.0
            )
            if ok:
                n.valor = novo
        elif chosen is act_edit_data:
            atual = ""
            if cols is self.COLS_DAE and n.vencimento_dae:
                atual = n.vencimento_dae.strftime("%d/%m/%Y")
            elif n.data_emissao:
                atual = n.data_emissao.strftime("%d/%m/%Y")
            novo, ok = QInputDialog.getText(self, "Data", "Data (dd/mm/aaaa):", text=atual)
            if ok:
                for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                    try:
                        d = datetime.strptime(novo.strip(), fmt).date()
                        if cols is self.COLS_DAE:
                            n.vencimento_dae = d
                        else:
                            n.data_emissao = d
                        break
                    except ValueError:
                        pass
        elif act_edit_fil is not None and chosen is act_edit_fil:
            atual = str(n.filial_codigo or "")
            novo, ok = QInputDialog.getText(self, "Filial", "Código da filial:", text=atual)
            if ok and novo.strip().isdigit():
                cod = int(novo.strip())
                n.filial_codigo = cod
                # Pega o nome do cnpjs se tiver, senão deixa em branco
                for info in self._cnpjs_filiais.values():
                    if int(info.get("codigo", -1)) == cod:
                        n.filial_nome = info.get("nome", "")
                        break
        elif act_edit_can is not None and chosen is act_edit_can:
            atual = n.filial_caneta_nome or n.anotacao_caneta or ""
            novo, ok = QInputDialog.getText(
                self, "Filial da caneta",
                "Nome da filial (ex: Luis Eduardo) ou 'código — nome':",
                text=atual,
            )
            if ok:
                txt = novo.strip()
                import re
                m = re.match(r"^\s*(\d+)\s*[—-]\s*(.*)$", txt)
                if m:
                    n.filial_caneta_codigo = int(m.group(1))
                    n.filial_caneta_nome = m.group(2).strip()
                    n.anotacao_caneta = txt
                else:
                    n.anotacao_caneta = txt
                    n.filial_caneta_codigo, n.filial_caneta_nome = self._resolver_filial_por_texto(txt)
        elif chosen is act_reset:
            n.status = StatusLancamento.PENDENTE
            n.erro = None
            n.motivo_ignorado = None
        elif chosen is act_remover:
            del self._notas[row]
            self._popular_grid()
            self._atualizar_resumo()
            return

        # Redesenha só a linha afetada
        self._tabela.blockSignals(True)
        try:
            self._popular_linha(row, n)
            self._atualizar_status_celula(row)
        finally:
            self._tabela.blockSignals(False)
        self._atualizar_resumo()

    # ---------- Ciclo do lote (multi-monitor) ----------

    def _restaurar_janela(self) -> None:
        """Volta a MainWindow pra tela/estado de antes do lote."""
        if self._main_window is not None:
            try:
                self._main_window._restaurar_janela_pos_lote()
            except Exception:  # noqa: BLE001
                log.exception("Falha restaurando janela pós-lote Orçamento")

    def _on_finished_worker(self, sucessos: int, falhas: int, ignoradas: int) -> None:
        self._btn_executar.setEnabled(True)
        self._btn_extrair.setEnabled(True)
        self._btn_cancelar.setEnabled(True)
        self._btn_cancelar.setVisible(False)
        self._restaurar_janela()
        total = sucessos + falhas + ignoradas
        resumo = f"Concluído — {sucessos} OK · {falhas} falhas · {ignoradas} ignoradas (de {total})"
        self._lbl_status.setText(resumo)
        self._log_line(f"== {resumo}")
        QMessageBox.information(
            self, "Lote concluído",
            f"Sucesso: {sucessos}\n"
            f"Falhas:  {falhas}\n"
            f"Já lançadas: {ignoradas}"
        )

    def _on_erro_worker(self, msg: str) -> None:
        self._btn_executar.setEnabled(True)
        self._btn_extrair.setEnabled(True)
        self._btn_cancelar.setVisible(False)
        self._restaurar_janela()
        self._lbl_status.setText("Erro.")
        self._log_line(f"XX Lote abortado: {msg[:180]}")
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
