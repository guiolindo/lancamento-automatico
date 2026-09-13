"""
Dialog mostrado após o lote terminar. Substitui o QMessageBox
"Sucessos: X / Falhas: Y" que era ruim de diagnosticar — se falhavam 3
lançamentos no meio de um lote de 12, o operador tinha que ler o log
inteiro pra descobrir quais.

Mostra:
- Cabeçalho com o resultado (verde se tudo ok, âmbar se falha parcial,
  vermelho se falha total)
- Lista scrollável das falhas com filial + valor + erro (só aparece se
  falhas > 0)
- Botão "Reprocessar falhas" (só aparece se falhas > 0). Emite sinal;
  a MainWindow escuta e dispara um novo lote só com os lançamentos
  falhados, com status resetado pra PENDENTE.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout,
)

from ..core.models import Lancamento, StatusLancamento


def _formatar_moeda(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class LoteResumoDialog(QDialog):
    reprocessar_falhas = Signal()  # emitido se usuário clicar em "Reprocessar"

    def __init__(self, lancamentos: list[Lancamento], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lote finalizado")
        self.setMinimumWidth(560)
        self.setMinimumHeight(280)

        sucessos = [l for l in lancamentos if l.status == StatusLancamento.SUCESSO]
        falhas = [l for l in lancamentos if l.status == StatusLancamento.FALHA]
        # Ignorados/pendentes não contam pra sucesso nem pra falha —
        # geralmente são lançamentos que o cancelamento pegou antes.
        n_ok = len(sucessos)
        n_bad = len(falhas)
        total_ok = sum(l.valor for l in sucessos)
        total_bad = sum(l.valor for l in falhas)

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(14)

        # Cabeçalho — cor conforme resultado
        if n_bad == 0 and n_ok > 0:
            titulo = f"✓ Lote concluído — {n_ok} lançamento(s) OK"
            cor_titulo = "#22C55E"  # verde
            subtitulo = f"Total lançado: {_formatar_moeda(total_ok)}"
        elif n_ok > 0 and n_bad > 0:
            titulo = f"⚠ Lote parcial — {n_ok} OK · {n_bad} falha(s)"
            cor_titulo = "#F59E0B"  # âmbar
            subtitulo = (
                f"Lançado: {_formatar_moeda(total_ok)}  ·  "
                f"Não lançado (falhas): {_formatar_moeda(total_bad)}"
            )
        elif n_bad > 0:
            titulo = f"✗ Lote falhou — {n_bad} falha(s), 0 OK"
            cor_titulo = "#EF4444"  # vermelho
            subtitulo = f"Nada foi lançado. Verifique a lista abaixo."
        else:
            titulo = "Lote sem lançamentos processados"
            cor_titulo = "#B7C2CF"
            subtitulo = "Verifique se o lote foi cancelado antes de iniciar."

        lbl_titulo = QLabel(titulo)
        lbl_titulo.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {cor_titulo};"
        )
        v.addWidget(lbl_titulo)

        lbl_sub = QLabel(subtitulo)
        lbl_sub.setStyleSheet("font-size: 12px; color: #B7C2CF;")
        lbl_sub.setWordWrap(True)
        v.addWidget(lbl_sub)

        # Lista de falhas — só se houver
        if falhas:
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet("color: #273340;")
            v.addWidget(sep)

            lbl_lista = QLabel("Falhas neste lote:")
            lbl_lista.setStyleSheet(
                "font-size: 11px; font-weight: 700; color: #B7C2CF; "
                "text-transform: uppercase; letter-spacing: 1px;"
            )
            v.addWidget(lbl_lista)

            lista = QListWidget()
            lista.setSelectionMode(QListWidget.NoSelection)
            lista.setStyleSheet(
                "QListWidget { background: #0F141A; border: 1px solid #273340; "
                "border-radius: 4px; padding: 6px; }"
                "QListWidget::item { padding: 8px 4px; border-bottom: 1px solid #171E26; }"
            )
            for l in falhas:
                erro = (l.erro or "erro não capturado").strip().splitlines()[0][:200]
                texto = (
                    f"  {l.filial_nome} ({l.filial_codigo}) — "
                    f"{_formatar_moeda(l.valor)}\n"
                    f"     {erro}"
                )
                item = QListWidgetItem(texto)
                item.setForeground(Qt.white)
                lista.addItem(item)
            v.addWidget(lista, 1)

        # Botões
        h = QHBoxLayout()
        h.addStretch(1)
        if falhas:
            btn_reproc = QPushButton(f"Reprocessar {n_bad} falha(s)")
            btn_reproc.setProperty("primary", True)
            btn_reproc.clicked.connect(self._on_reprocessar)
            h.addWidget(btn_reproc)
        btn_fechar = QPushButton("Fechar")
        btn_fechar.setDefault(True)
        btn_fechar.clicked.connect(self.accept)
        h.addWidget(btn_fechar)
        v.addLayout(h)

    def _on_reprocessar(self) -> None:
        self.reprocessar_falhas.emit()
        self.accept()
