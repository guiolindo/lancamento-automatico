from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QMenu, QTableWidget, QTableWidgetItem
)

from ..core.models import Lancamento, StatusLancamento


STATUS_ROTULOS = {
    StatusLancamento.PENDENTE: ("Pendente", QColor("#8892A6")),
    StatusLancamento.EM_ANDAMENTO: ("Em andamento", QColor("#4F8CFF")),
    StatusLancamento.SUCESSO: ("Sucesso", QColor("#3BD787")),
    StatusLancamento.FALHA: ("Falha", QColor("#F26B6B")),
    StatusLancamento.IGNORADO: ("Ignorado", QColor("#8892A6")),
}


class PreviewTable(QTableWidget):
    COLS = ["#", "Filial", "Cód.", "Tipo Folha", "Observação", "Valor (R$)", "Status"]

    # Sinais emitidos pelo menu contextual. MainWindow escuta e faz o
    # trabalho real (QInputDialog, mexer no worker, etc.). PreviewTable
    # mantém-se estúpida — só sabe da lista dela.
    pediu_editar_filial = Signal(int)      # index
    pediu_editar_valor = Signal(int)
    pediu_remover = Signal(int)
    pediu_reprocessar = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(self.COLS))
        self.setHorizontalHeaderLabels(self.COLS)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setShowGrid(False)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)

        self._lancamentos: list[Lancamento] = []

    def carregar(self, lancamentos: list[Lancamento]) -> None:
        self._lancamentos = lancamentos
        self.setRowCount(len(lancamentos))
        for i, lanc in enumerate(lancamentos):
            self._render_row(i, lanc)

    def atualizar_linha(self, i: int) -> None:
        if 0 <= i < len(self._lancamentos):
            self._render_row(i, self._lancamentos[i])

    def _render_row(self, i: int, lanc: Lancamento) -> None:
        valor = f"{lanc.valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        rotulo, cor = STATUS_ROTULOS.get(
            lanc.status, ("?", QColor("#8892A6"))
        )
        celulas = [
            str(i + 1),
            lanc.filial_nome,
            str(lanc.filial_codigo),
            lanc.tipo_folha,
            lanc.observacao,
            valor,
            rotulo,
        ]
        for c, texto in enumerate(celulas):
            item = QTableWidgetItem(texto)
            if c == 5:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if c == 6:
                item.setForeground(cor)
                item.setTextAlignment(Qt.AlignCenter)
            self.setItem(i, c, item)

    def lancamentos(self) -> list[Lancamento]:
        return self._lancamentos

    def remover_linha(self, i: int) -> None:
        """Remove um lançamento da lista + da tabela em bloco. MainWindow
        precisa recarregar KPIs depois (via sinal na chamada)."""
        if not (0 <= i < len(self._lancamentos)):
            return
        del self._lancamentos[i]
        self.removeRow(i)
        # Renumera a coluna # nas linhas restantes
        for row in range(self.rowCount()):
            item = self.item(row, 0)
            if item:
                item.setText(str(row + 1))

    def contextMenuEvent(self, event) -> None:  # noqa: N802 (Qt convention)
        row = self.rowAt(event.pos().y())
        if row < 0 or row >= len(self._lancamentos):
            return
        # Seleciona a linha clicada pra dar feedback visual
        self.selectRow(row)

        lanc = self._lancamentos[row]
        menu = QMenu(self)
        act_filial = menu.addAction("Editar filial…")
        act_valor = menu.addAction("Editar valor…")
        menu.addSeparator()
        act_remover = menu.addAction("Remover deste lote")
        # "Reprocessar apenas esta" só faz sentido se o lote já rodou
        # (status ≠ PENDENTE) — mas mostrar sempre e deixar MainWindow
        # decidir se o comando tem efeito. Aqui só sinaliza intenção.
        menu.addSeparator()
        act_reproc = menu.addAction("Reprocessar apenas esta")
        act_reproc.setEnabled(lanc.status != StatusLancamento.EM_ANDAMENTO)

        chosen = menu.exec(event.globalPos())
        if chosen is act_filial:
            self.pediu_editar_filial.emit(row)
        elif chosen is act_valor:
            self.pediu_editar_valor.emit(row)
        elif chosen is act_remover:
            self.pediu_remover.emit(row)
        elif chosen is act_reproc:
            self.pediu_reprocessar.emit(row)
