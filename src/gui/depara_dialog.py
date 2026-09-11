"""
Diálogo de cadastro de filiais (De-Para).

Substitui a edição manual do mapeamento.json — o operador adiciona,
remove e edita filiais numa tabela; ao Salvar, grava de volta no JSON
mantendo os blocos que não são de-para (comentários, impostos).
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget
)

from ..core.mapping import MappingRepository


EMPRESAS = ["MG", "BA", "CD_ADM"]
TIPOS = ["LOJA", "CD", "ADM"]


class DeParaDialog(QDialog):
    def __init__(self, mapping: MappingRepository, mapping_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("De-Para de filiais")
        self.resize(1000, 640)
        self.mapping = mapping
        self.mapping_path = mapping_path
        self._dados_originais: dict = {}

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(20, 16, 20, 16)
        raiz.setSpacing(12)

        titulo = QLabel("Cadastro de Filiais")
        titulo.setProperty("h1", True)
        raiz.addWidget(titulo)

        instr = QLabel(
            "Adicione as filiais/lojas/CDs com seus códigos TOTVS. "
            "Em <b>Aliases</b>, coloque as diferentes formas que o nome pode "
            "aparecer nos relatórios (separadas por vírgula) — o app usa isso "
            "pra resolver \"SAJ\" → \"Santo Antonio de Jesus\", por exemplo."
        )
        instr.setWordWrap(True)
        instr.setProperty("muted", True)
        raiz.addWidget(instr)

        # Toolbar
        toolbar = QHBoxLayout()
        btn_add = QPushButton("+ Adicionar filial")
        btn_add.clicked.connect(self._adicionar_linha)
        toolbar.addWidget(btn_add)

        btn_rem = QPushButton("− Remover selecionada")
        btn_rem.setProperty("danger", True)
        btn_rem.clicked.connect(self._remover_linha)
        toolbar.addWidget(btn_rem)

        toolbar.addStretch(1)

        btn_reload = QPushButton("Recarregar do arquivo")
        btn_reload.clicked.connect(self._recarregar)
        toolbar.addWidget(btn_reload)

        raiz.addLayout(toolbar)

        # Tabela
        self.tabela = QTableWidget()
        self.tabela.setColumnCount(5)
        self.tabela.setHorizontalHeaderLabels(["Empresa", "Código", "Nome", "Tipo", "Aliases (separar com vírgula)"])
        self.tabela.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.verticalHeader().setDefaultSectionSize(34)
        h = self.tabela.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Interactive)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.Stretch)
        self.tabela.setColumnWidth(2, 220)
        raiz.addWidget(self.tabela, 1)

        # Rodapé
        acoes = QHBoxLayout()
        self.lbl_status = QLabel("")
        self.lbl_status.setProperty("muted", True)
        acoes.addWidget(self.lbl_status, 1)

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        acoes.addWidget(btn_cancel)

        btn_salvar = QPushButton("Salvar")
        btn_salvar.setProperty("primary", True)
        btn_salvar.clicked.connect(self._salvar)
        acoes.addWidget(btn_salvar)
        raiz.addLayout(acoes)

        self._carregar()

    # ---------- carga ----------

    def _carregar(self) -> None:
        with open(self.mapping_path, "r", encoding="utf-8") as f:
            self._dados_originais = json.load(f)

        self.tabela.setRowCount(0)
        for empresa_chave, empresa in (self._dados_originais.get("empresas") or {}).items():
            for filial in empresa.get("filiais", []):
                self._append_linha(
                    empresa_chave,
                    int(filial["codigo"]),
                    filial.get("nome", ""),
                    filial.get("tipo", "LOJA"),
                    filial.get("aliases", []),
                )
        self._atualizar_status()

    def _recarregar(self) -> None:
        if self.tabela.rowCount() > 0:
            resp = QMessageBox.question(
                self, "Recarregar",
                "Descartar as alterações não salvas e recarregar do arquivo?",
            )
            if resp != QMessageBox.Yes:
                return
        self._carregar()

    # ---------- edição ----------

    def _append_linha(self, empresa: str, codigo: int, nome: str, tipo: str, aliases: list[str]) -> None:
        linha = self.tabela.rowCount()
        self.tabela.insertRow(linha)

        combo_emp = QComboBox()
        combo_emp.addItems(EMPRESAS)
        if empresa in EMPRESAS:
            combo_emp.setCurrentText(empresa)
        self.tabela.setCellWidget(linha, 0, combo_emp)

        spin_cod = QSpinBox()
        spin_cod.setRange(1, 9999)
        spin_cod.setValue(codigo)
        self.tabela.setCellWidget(linha, 1, spin_cod)

        edit_nome = QLineEdit(nome)
        self.tabela.setCellWidget(linha, 2, edit_nome)

        combo_tipo = QComboBox()
        combo_tipo.addItems(TIPOS)
        if tipo in TIPOS:
            combo_tipo.setCurrentText(tipo)
        self.tabela.setCellWidget(linha, 3, combo_tipo)

        edit_alias = QLineEdit(", ".join(aliases))
        edit_alias.setPlaceholderText("Ex: SAJ, SANTO ANTONIO DE JESUS")
        self.tabela.setCellWidget(linha, 4, edit_alias)

    def _adicionar_linha(self) -> None:
        # Sugere próximo código livre (max+1)
        codigos = set()
        for l in range(self.tabela.rowCount()):
            sb: QSpinBox = self.tabela.cellWidget(l, 1)  # type: ignore
            codigos.add(sb.value())
        proximo = max(codigos) + 1 if codigos else 1

        self._append_linha("MG", proximo, "", "LOJA", [])
        self.tabela.selectRow(self.tabela.rowCount() - 1)
        # Foca no nome pra o operador digitar direto
        edit = self.tabela.cellWidget(self.tabela.rowCount() - 1, 2)
        if edit:
            edit.setFocus()
        self._atualizar_status()

    def _remover_linha(self) -> None:
        linhas = sorted({idx.row() for idx in self.tabela.selectedIndexes()}, reverse=True)
        if not linhas:
            return
        for l in linhas:
            self.tabela.removeRow(l)
        self._atualizar_status()

    def _atualizar_status(self) -> None:
        self.lbl_status.setText(f"{self.tabela.rowCount()} filial(is)")

    # ---------- salvar ----------

    def _coletar(self) -> dict[str, dict]:
        """Reconstrói o bloco 'empresas' a partir da tabela."""
        empresas: dict[str, dict] = {}
        for chave in EMPRESAS:
            desc_original = ((self._dados_originais.get("empresas") or {}).get(chave, {}) or {}).get(
                "descricao", chave
            )
            empresas[chave] = {"descricao": desc_original, "filiais": []}

        for l in range(self.tabela.rowCount()):
            emp: str = self.tabela.cellWidget(l, 0).currentText()  # type: ignore
            cod: int = int(self.tabela.cellWidget(l, 1).value())  # type: ignore
            nome: str = self.tabela.cellWidget(l, 2).text().strip()  # type: ignore
            tipo: str = self.tabela.cellWidget(l, 3).currentText()  # type: ignore
            aliases_txt: str = self.tabela.cellWidget(l, 4).text()  # type: ignore
            aliases = [a.strip() for a in aliases_txt.split(",") if a.strip()]

            if not nome:
                raise ValueError(f"Linha {l+1}: nome vazio")

            empresas[emp]["filiais"].append({
                "codigo": cod,
                "nome": nome,
                "tipo": tipo,
                "aliases": aliases,
            })
        return empresas

    def _salvar(self) -> None:
        try:
            novas_empresas = self._coletar()
        except ValueError as e:
            QMessageBox.warning(self, "Dados incompletos", str(e))
            return

        # Detecta código duplicado (mesmo código em duas linhas) — TOTVS não aceita.
        codigos: dict[int, str] = {}
        for chave, bloco in novas_empresas.items():
            for f in bloco["filiais"]:
                if f["codigo"] in codigos:
                    QMessageBox.warning(
                        self, "Código duplicado",
                        f"Código {f['codigo']} aparece em '{codigos[f['codigo']]}' e '{f['nome']}'.",
                    )
                    return
                codigos[f["codigo"]] = f["nome"]

        # Preserva _comentario e impostos, substitui só empresas.
        dados = dict(self._dados_originais)
        dados["empresas"] = novas_empresas

        try:
            with open(self.mapping_path, "w", encoding="utf-8") as f:
                json.dump(dados, f, indent=2, ensure_ascii=False)
        except OSError as e:
            QMessageBox.critical(self, "Erro ao salvar", str(e))
            return

        # Recarrega o repositório em memória — próxima extração já usa.
        try:
            self.mapping.reload()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(
                self, "Salvou, mas...",
                f"Arquivo gravado, porém falhou ao recarregar em memória: {e}\n"
                "Feche e reabra o app.",
            )
        self.accept()
