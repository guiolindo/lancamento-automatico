"""
Diálogo de cadastro de filiais (De-Para) — versão card-based.

Cada filial é uma linha em card. Sem QTableWidget/cellWidget que
sofriam de bugs de overlap.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QVBoxLayout, QWidget
)

from ..core.mapping import MappingRepository


EMPRESAS = ["MG", "BA", "CD_ADM"]
TIPOS = ["LOJA", "CD", "ADM"]


class FilialRow(QFrame):
    """Uma linha visual de filial — 2 sub-linhas."""

    def __init__(self, empresa: str, codigo: int, nome: str, tipo: str,
                 aliases: list[str], on_remove, parent=None):
        super().__init__(parent)
        self.setProperty("filialRow", True)
        self._on_remove = on_remove

        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)

        # ----- Linha 1: Empresa | Código | Nome | Tipo | Remover
        r1 = QHBoxLayout()
        r1.setSpacing(10)

        self.combo_emp = QComboBox()
        self.combo_emp.addItems(EMPRESAS)
        if empresa in EMPRESAS:
            self.combo_emp.setCurrentText(empresa)
        self.combo_emp.setFixedWidth(110)
        r1.addWidget(self.combo_emp)

        self.spin_cod = QSpinBox()
        self.spin_cod.setRange(1, 9999)
        self.spin_cod.setValue(codigo)
        self.spin_cod.setButtonSymbols(QSpinBox.NoButtons)
        self.spin_cod.setAlignment(Qt.AlignCenter)
        self.spin_cod.setFixedWidth(90)
        r1.addWidget(self.spin_cod)

        self.edit_nome = QLineEdit(nome)
        self.edit_nome.setPlaceholderText("Nome da filial")
        r1.addWidget(self.edit_nome, 1)

        self.combo_tipo = QComboBox()
        self.combo_tipo.addItems(TIPOS)
        if tipo in TIPOS:
            self.combo_tipo.setCurrentText(tipo)
        self.combo_tipo.setFixedWidth(100)
        r1.addWidget(self.combo_tipo)

        btn_rem = QPushButton("Remover")
        btn_rem.setProperty("danger", True)
        btn_rem.setFixedWidth(96)
        btn_rem.clicked.connect(lambda: self._on_remove(self))
        r1.addWidget(btn_rem)

        v.addLayout(r1)

        # ----- Linha 2: Aliases
        r2 = QHBoxLayout()
        r2.setSpacing(10)
        lb_al = QLabel("Aliases")
        lb_al.setProperty("inlineLabel", True)
        lb_al.setFixedWidth(60)
        r2.addWidget(lb_al)

        self.edit_alias = QLineEdit(", ".join(aliases))
        self.edit_alias.setPlaceholderText(
            "Separe com vírgula. Ex: SAJ, ANTONIO JESUS, ST ANTONIO"
        )
        r2.addWidget(self.edit_alias, 1)
        v.addLayout(r2)

    def dados(self) -> dict:
        aliases = [a.strip() for a in self.edit_alias.text().split(",") if a.strip()]
        return {
            "empresa": self.combo_emp.currentText(),
            "codigo": int(self.spin_cod.value()),
            "nome": self.edit_nome.text().strip(),
            "tipo": self.combo_tipo.currentText(),
            "aliases": aliases,
        }


class DeParaDialog(QDialog):
    def __init__(self, mapping: MappingRepository, mapping_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("De-Para de filiais")
        self.resize(920, 680)
        self.setMinimumSize(720, 520)
        self.mapping = mapping
        self.mapping_path = mapping_path
        self._dados_originais: dict = {}
        self._rows: list[FilialRow] = []

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(24, 20, 24, 20)
        raiz.setSpacing(14)

        # ----- Cabeçalho
        titulo = QLabel("Cadastro de Filiais")
        titulo.setProperty("h1", True)
        raiz.addWidget(titulo)

        instr = QLabel(
            "Cadastre filiais/lojas/CDs com os códigos TOTVS. Em <b>Aliases</b>, "
            "coloque as formas que o nome aparece nos relatórios — o app usa isso "
            "pra resolver abreviações."
        )
        instr.setWordWrap(True)
        instr.setProperty("muted", True)
        raiz.addWidget(instr)

        # ----- Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        btn_add = QPushButton("+ Adicionar filial")
        btn_add.setProperty("primary", True)
        btn_add.clicked.connect(self._adicionar)
        toolbar.addWidget(btn_add)

        btn_reload = QPushButton("Recarregar do arquivo")
        btn_reload.clicked.connect(self._recarregar)
        toolbar.addWidget(btn_reload)

        toolbar.addStretch(1)

        self.lbl_status = QLabel("")
        self.lbl_status.setProperty("muted", True)
        toolbar.addWidget(self.lbl_status)

        raiz.addLayout(toolbar)

        # ----- Área rolável com os cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._container = QWidget()
        self._lista = QVBoxLayout(self._container)
        self._lista.setContentsMargins(2, 2, 8, 2)
        self._lista.setSpacing(10)
        self._lista.addStretch(1)  # espaçador no fim
        scroll.setWidget(self._container)
        raiz.addWidget(scroll, 1)

        # ----- Rodapé com ações
        acoes = QHBoxLayout()
        acoes.addStretch(1)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        acoes.addWidget(btn_cancel)

        btn_salvar = QPushButton("Salvar tudo")
        btn_salvar.setProperty("primary", True)
        btn_salvar.setMinimumWidth(140)
        btn_salvar.clicked.connect(self._salvar)
        acoes.addWidget(btn_salvar)
        raiz.addLayout(acoes)

        self._carregar()

    # ---------- carga ----------

    def _carregar(self) -> None:
        with open(self.mapping_path, "r", encoding="utf-8") as f:
            self._dados_originais = json.load(f)

        self._limpar()
        for empresa_chave, empresa in (self._dados_originais.get("empresas") or {}).items():
            for filial in empresa.get("filiais", []):
                self._append_row(
                    empresa_chave,
                    int(filial["codigo"]),
                    filial.get("nome", ""),
                    filial.get("tipo", "LOJA"),
                    filial.get("aliases", []),
                )
        self._atualizar_status()

    def _limpar(self) -> None:
        for row in list(self._rows):
            self._lista.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

    def _recarregar(self) -> None:
        if self._rows:
            resp = QMessageBox.question(
                self, "Recarregar",
                "Descartar alterações não salvas e recarregar do arquivo?",
            )
            if resp != QMessageBox.Yes:
                return
        self._carregar()

    # ---------- edição ----------

    def _append_row(self, empresa: str, codigo: int, nome: str, tipo: str,
                    aliases: list[str]) -> FilialRow:
        row = FilialRow(empresa, codigo, nome, tipo, aliases, on_remove=self._remover)
        # Insere antes do stretch final
        self._lista.insertWidget(self._lista.count() - 1, row)
        self._rows.append(row)
        return row

    def _adicionar(self) -> None:
        codigos = {r.spin_cod.value() for r in self._rows}
        proximo = max(codigos) + 1 if codigos else 1
        row = self._append_row("MG", proximo, "", "LOJA", [])
        row.edit_nome.setFocus()
        self._atualizar_status()

    def _remover(self, row: FilialRow) -> None:
        self._rows.remove(row)
        self._lista.removeWidget(row)
        row.deleteLater()
        self._atualizar_status()

    def _atualizar_status(self) -> None:
        self.lbl_status.setText(f"{len(self._rows)} filial(is)")

    # ---------- salvar ----------

    def _coletar(self) -> dict[str, dict]:
        empresas: dict[str, dict] = {}
        for chave in EMPRESAS:
            desc = ((self._dados_originais.get("empresas") or {})
                    .get(chave, {}) or {}).get("descricao", chave)
            empresas[chave] = {"descricao": desc, "filiais": []}

        for i, row in enumerate(self._rows):
            d = row.dados()
            if not d["nome"]:
                raise ValueError(f"Linha {i+1}: nome vazio")
            empresas[d["empresa"]]["filiais"].append({
                "codigo": d["codigo"],
                "nome": d["nome"],
                "tipo": d["tipo"],
                "aliases": d["aliases"],
            })
        return empresas

    def _salvar(self) -> None:
        try:
            novas = self._coletar()
        except ValueError as e:
            QMessageBox.warning(self, "Dados incompletos", str(e))
            return

        # Código duplicado
        vistos: dict[int, str] = {}
        for chave, bloco in novas.items():
            for f in bloco["filiais"]:
                if f["codigo"] in vistos:
                    QMessageBox.warning(
                        self, "Código duplicado",
                        f"Código {f['codigo']} aparece em '{vistos[f['codigo']]}' e '{f['nome']}'.",
                    )
                    return
                vistos[f["codigo"]] = f["nome"]

        dados = dict(self._dados_originais)
        dados["empresas"] = novas

        try:
            with open(self.mapping_path, "w", encoding="utf-8") as f:
                json.dump(dados, f, indent=2, ensure_ascii=False)
        except OSError as e:
            QMessageBox.critical(self, "Erro ao salvar", str(e))
            return

        try:
            self.mapping.reload()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(
                self, "Salvou, mas...",
                f"Arquivo gravado, mas falhou ao recarregar em memória: {e}\n"
                "Feche e reabra o app.",
            )
        self.accept()
