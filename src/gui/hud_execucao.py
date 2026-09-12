"""
HUD flutuante mostrado durante execução do lote em CONFIGURAÇÃO MONO-MONITOR.

Motivo: se o usuário tem só uma tela, o Auto Conferi maximizado cobre a
janela do TOTVS que o RPA precisa manipular. A solução é minimizar a
MainWindow e mostrar este HUD compacto no canto superior direito da
mesma tela — fora da região da janela do TOTVS, sempre visível
(always-on-top), sem cobrir campo nenhum.

Em multi-monitor este HUD não é usado — a MainWindow fica visível no
outro monitor e mostra o progresso normalmente.

Sinais espelham os do LoteWorker; a MainWindow conecta um no outro.
"""

from __future__ import annotations

import time as _time

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
    QWidget,
)


class HudExecucao(QWidget):
    """Painel flutuante compacto pra acompanhar o lote sem tapar o TOTVS."""

    # Emitido quando o operador aperta "Parar" no HUD — equivale a END.
    parar_clicado = Signal()

    # Emitido quando o operador responde a confirmação manual pelo HUD.
    # True = próximo lançamento, False = parar lote.
    confirmacao_respondida = Signal(bool)

    LARGURA = 380
    ALTURA_MIN = 132
    ALTURA_COM_CONFIRMACAO = 232
    MARGEM_TELA = 12

    def __init__(self, parent: QWidget | None = None):
        # Sem parent Qt (parent=None) pra evitar que o HUD herde o estado
        # minimizado da MainWindow — ele precisa ficar visível mesmo com
        # a janela principal minimizada.
        super().__init__(None)
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setWindowTitle("Auto Conferi — em execução")

        self._inicio = _time.monotonic()
        self._total = 0
        self._idx_atual = -1
        self._modo_confirmacao_ativo = False

        self._montar_ui()
        self.setFixedSize(self.LARGURA, self.ALTURA_MIN)

    def _montar_ui(self) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)

        # Cabeçalho: título + tempo
        cab = QHBoxLayout()
        cab.setSpacing(8)
        titulo = QLabel("Auto Conferi — lote em execução")
        titulo.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #E5E7EB;"
        )
        cab.addWidget(titulo, 1)
        self._lbl_tempo = QLabel("00:00")
        self._lbl_tempo.setStyleSheet("font-size: 11px; color: #94A3B8;")
        cab.addWidget(self._lbl_tempo, 0, Qt.AlignRight)
        v.addLayout(cab)

        # Linha principal: progresso textual
        self._lbl_progresso = QLabel("Aguardando…")
        self._lbl_progresso.setStyleSheet(
            "font-size: 13px; color: #F1F5F9; font-weight: 600;"
        )
        self._lbl_progresso.setWordWrap(True)
        v.addWidget(self._lbl_progresso)

        # Barra de progresso
        self._bar = QProgressBar()
        self._bar.setRange(0, 1)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self._bar.setStyleSheet(
            "QProgressBar { background: #1F2937; border: none; border-radius: 3px; }"
            "QProgressBar::chunk { background: qlineargradient("
            "x1:0, y1:0, x2:1, y2:0, stop:0 #14B8A6, stop:1 #3B82F6);"
            " border-radius: 3px; }"
        )
        v.addWidget(self._bar)

        # Botão parar (sempre disponível)
        h_botoes = QHBoxLayout()
        h_botoes.setSpacing(8)
        self._btn_parar = QPushButton("⏹  Parar lote (END)")
        self._btn_parar.setCursor(Qt.PointingHandCursor)
        self._btn_parar.setStyleSheet(
            "QPushButton { background: #DC2626; color: #FFF; border: none; "
            "border-radius: 6px; padding: 6px 12px; font-size: 12px; font-weight: 600; }"
            "QPushButton:hover { background: #EF4444; }"
        )
        self._btn_parar.clicked.connect(self.parar_clicado.emit)
        h_botoes.addWidget(self._btn_parar, 1)
        v.addLayout(h_botoes)

        # Painel de confirmação manual (oculto por padrão)
        self._painel_confirmacao = QFrame()
        self._painel_confirmacao.setStyleSheet(
            "QFrame { background: #1F2937; border: 1px solid #374151; "
            "border-radius: 6px; }"
        )
        pv = QVBoxLayout(self._painel_confirmacao)
        pv.setContentsMargins(10, 8, 10, 10)
        pv.setSpacing(6)
        self._lbl_confirmacao = QLabel(
            "Revisão manual — confira no TOTVS e escolha:"
        )
        self._lbl_confirmacao.setStyleSheet(
            "font-size: 11px; color: #F1F5F9; font-weight: 600; border: none;"
        )
        self._lbl_confirmacao.setWordWrap(True)
        pv.addWidget(self._lbl_confirmacao)

        ph = QHBoxLayout()
        ph.setSpacing(6)
        self._btn_prosseguir = QPushButton("✓ Próximo")
        self._btn_prosseguir.setCursor(Qt.PointingHandCursor)
        self._btn_prosseguir.setStyleSheet(
            "QPushButton { background: #14B8A6; color: #FFF; border: none; "
            "border-radius: 5px; padding: 6px 10px; font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background: #2DD4BF; }"
        )
        self._btn_prosseguir.clicked.connect(self._on_prosseguir)
        ph.addWidget(self._btn_prosseguir, 1)

        self._btn_parar_manual = QPushButton("⏹ Parar")
        self._btn_parar_manual.setCursor(Qt.PointingHandCursor)
        self._btn_parar_manual.setStyleSheet(
            "QPushButton { background: #374151; color: #F1F5F9; border: none; "
            "border-radius: 5px; padding: 6px 10px; font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background: #4B5563; }"
        )
        self._btn_parar_manual.clicked.connect(self._on_parar_manual)
        ph.addWidget(self._btn_parar_manual, 0)
        pv.addLayout(ph)

        self._painel_confirmacao.setHidden(True)
        v.addWidget(self._painel_confirmacao)

        # Estilo do próprio HUD
        self.setStyleSheet(
            "HudExecucao { background: #0F141A; border: 1px solid #334155; "
            "border-radius: 4px; }"
        )

        # Timer pra atualizar o "tempo decorrido"
        self._timer_tempo = QTimer(self)
        self._timer_tempo.setInterval(1000)
        self._timer_tempo.timeout.connect(self._tick_tempo)

    # ---------- API pública ----------

    def iniciar(self, total: int, geo_tela: QRect) -> None:
        """Chamado quando o lote começa. Posiciona no canto superior direito
        do monitor cujo geo é passado (o mesmo onde o TOTVS está)."""
        self._total = max(1, total)
        self._idx_atual = -1
        self._inicio = _time.monotonic()
        self._bar.setRange(0, self._total)
        self._bar.setValue(0)
        self._lbl_progresso.setText(f"Preparando {self._total} lançamento(s)…")
        self._lbl_tempo.setText("00:00")
        self._reposicionar(geo_tela)
        self.show()
        self.raise_()
        self._timer_tempo.start()

    def on_progresso(self, i: int, total: int, msg: str) -> None:
        self._idx_atual = i
        if total > 0:
            self._total = total
            self._bar.setRange(0, total)
        self._bar.setValue(i + 1)
        self._lbl_progresso.setText(f"{i + 1}/{total} · {msg}")

    def pedir_confirmacao_manual(self, index: int, resumo: str) -> None:
        """Cresce o HUD e mostra painel com Prosseguir/Parar."""
        self._modo_confirmacao_ativo = True
        self._lbl_confirmacao.setText(
            f"Revisão manual — lançamento {index + 1}:\n{resumo}\n\n"
            "Confira no TOTVS, aperte + pra gravar, depois clique:"
        )
        self._painel_confirmacao.setHidden(False)
        self.setFixedSize(self.LARGURA, self.ALTURA_COM_CONFIRMACAO)
        self.raise_()

    def esconder_confirmacao(self) -> None:
        self._modo_confirmacao_ativo = False
        self._painel_confirmacao.setHidden(True)
        self.setFixedSize(self.LARGURA, self.ALTURA_MIN)

    def finalizar(self, sucessos: int, falhas: int) -> None:
        self._timer_tempo.stop()
        self._bar.setValue(self._bar.maximum())
        if falhas == 0:
            self._lbl_progresso.setText(f"✓ Concluído — {sucessos} lançados")
        else:
            self._lbl_progresso.setText(
                f"⚠ Finalizado — {sucessos} ok · {falhas} falha(s)"
            )
        # Auto-esconde após 3s pra dar tempo do usuário ler
        QTimer.singleShot(3000, self.close)

    # ---------- Interno ----------

    def _on_prosseguir(self) -> None:
        self.esconder_confirmacao()
        self.confirmacao_respondida.emit(True)

    def _on_parar_manual(self) -> None:
        self.esconder_confirmacao()
        self.confirmacao_respondida.emit(False)

    def _tick_tempo(self) -> None:
        elapsed = int(_time.monotonic() - self._inicio)
        m, s = divmod(elapsed, 60)
        self._lbl_tempo.setText(f"{m:02d}:{s:02d}")

    def _reposicionar(self, geo_tela: QRect) -> None:
        x = geo_tela.right() - self.LARGURA - self.MARGEM_TELA
        y = geo_tela.top() + self.MARGEM_TELA
        self.move(x, y)
