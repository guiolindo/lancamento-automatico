from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(self.COLS))
        self.setHorizontalHeaderLabels(self.COLS)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setShowGrid(False)

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
