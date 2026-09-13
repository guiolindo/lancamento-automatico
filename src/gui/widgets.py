"""
Widgets custom pequenos, reutilizáveis pela UI. Se algum crescer,
promove pra próprio arquivo.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDateEdit, QDateTimeEdit


class DateEditFast(QDateEdit):
    """QDateEdit com dois ajustes de UX pedidos no build-84:

    1. **Scroll do mouse não muda a data** — antes, esbarrar a rodinha
       do mouse quando o campo tinha foco alterava dia/mês/ano sem
       querer. Ignoramos wheelEvent.
    2. **Ao ganhar foco, já pula pra seção do dia com ela selecionada**
       — permite digitar `13092026` de uma vez, sem precisar clicar em
       cada pedaço. Cada seção auto-avança quando os 2 dígitos (ou 4
       do ano) são preenchidos.

    Compatível como drop-in do QDateEdit — todos os métodos existentes
    (setDisplayFormat, setCalendarPopup, setMinimumDate, etc.) seguem
    funcionando.
    """

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt convention)
        event.ignore()

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        # Pula pro DIA já com seleção. Digitar dígitos preenche e avança.
        self.setCurrentSection(QDateTimeEdit.DaySection)
