from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from ..core.gemini_client import GeminiClient, montar_lancamentos
from ..core.logger import log
from ..core.mapping import MappingRepository
from ..core.models import Imposto, Lancamento, LinhaExtracao


class ExtracaoWorker(QObject):
    """Roda a extração pelo Gemini em thread separada."""
    finished = Signal(list, list)   # lancamentos, nao_resolvidas
    error = Signal(str)
    log_line = Signal(str)

    def __init__(
        self,
        arquivo: Path,
        api_key: str,
        modelo: str,
        imposto: Imposto,
        mapping: MappingRepository,
        data_emissao: date,
    ):
        super().__init__()
        self.arquivo = arquivo
        self.api_key = api_key
        self.modelo = modelo
        self.imposto = imposto
        self.mapping = mapping
        self.data_emissao = data_emissao

    def run(self) -> None:
        try:
            self.log_line.emit(f"→ Enviando '{self.arquivo.name}' para o Gemini…")
            client = GeminiClient(self.api_key, self.modelo)
            extracao = client.extrair(self.arquivo, self.imposto)
            self.log_line.emit(
                f"✓ Extração recebida: {len(extracao.get('linhas', []))} linhas, "
                f"referência {extracao.get('mes_ref','?')}/{extracao.get('ano_ref','?')}"
            )
            lancamentos, nao_resolvidas = montar_lancamentos(
                extracao, self.imposto, self.mapping, self.data_emissao,
            )
            if nao_resolvidas:
                self.log_line.emit(
                    f"⚠ {len(nao_resolvidas)} filial(is) não resolvida(s) no de-para"
                )
            self.log_line.emit(f"✓ {len(lancamentos)} lançamentos prontos para revisão")
            self.finished.emit(lancamentos, nao_resolvidas)
        except Exception as e:  # noqa: BLE001
            log.exception("Falha na extração")
            self.error.emit(str(e))


class LoteWorker(QObject):
    """Roda a execução no TOTVS em thread separada."""
    progresso = Signal(int, int, str)  # index, total, mensagem
    lancamento_atualizado = Signal(int)  # index
    finished = Signal(int, int)         # sucessos, falhas
    error = Signal(str)
    log_line = Signal(str)
    # Modo revisão manual: pede confirmação do operador para seguir. A GUI
    # deve responder via responder_confirmacao(True/False).
    pedir_confirmacao_manual = Signal(int, str)   # index, resumo

    def __init__(self, lancamentos: list[Lancamento], settings: dict, parar_em_falha: bool = False):
        super().__init__()
        self.lancamentos = lancamentos
        self.settings = settings
        self.parar_em_falha = parar_em_falha
        self._cancelar = False
        import threading
        self._evento_confirmacao = threading.Event()
        self._resposta_confirmacao = False

    def cancelar(self) -> None:
        self._cancelar = True
        # Se estamos parados esperando confirmação, libera com "não prosseguir".
        self._resposta_confirmacao = False
        self._evento_confirmacao.set()

    def responder_confirmacao(self, prosseguir: bool) -> None:
        self._resposta_confirmacao = prosseguir
        self._evento_confirmacao.set()

    def _aguardar_confirmacao(self, lanc: Lancamento) -> bool:
        self._evento_confirmacao.clear()
        resumo = f"{lanc.filial_nome} — {lanc.tipo_folha} — R$ {lanc.valor:,.2f}"
        self.pedir_confirmacao_manual.emit(getattr(self, "_i_atual", -1), resumo)
        self._evento_confirmacao.wait()
        return self._resposta_confirmacao and not self._cancelar

    def run(self) -> None:
        try:
            from ..core.rpa_totvs import ManualAbortException, RpaTotvs
            rpa = RpaTotvs(
                self.settings,
                on_progress=self._on_progress,
                aguardar_confirmacao=self._aguardar_confirmacao,
            )
            self.log_line.emit("→ Conectando à janela do TOTVS…")
            rpa.conectar()
            self.log_line.emit("✓ Janela conectada")

            sucessos = 0
            falhas = 0
            total = len(self.lancamentos)
            for i, lanc in enumerate(self.lancamentos):
                if self._cancelar:
                    self.log_line.emit("⏹ Execução cancelada pelo usuário")
                    break
                self._i_atual = i
                self.progresso.emit(i, total, f"{lanc.filial_nome} — {lanc.tipo_folha}")
                try:
                    rpa.lancar(lanc)
                    sucessos += 1
                except ManualAbortException:
                    self.log_line.emit("⏹ Lote interrompido pelo operador")
                    break
                except Exception as e:  # noqa: BLE001
                    falhas += 1
                    self.log_line.emit(f"✗ Falha em {lanc.filial_nome}/{lanc.tipo_folha}: {e}")
                    if self.parar_em_falha:
                        break
                self.lancamento_atualizado.emit(i)
            self.finished.emit(sucessos, falhas)
        except Exception as e:  # noqa: BLE001
            log.exception("Falha no lote")
            self.error.emit(str(e))

    def _on_progress(self, lanc: Lancamento, msg: str) -> None:
        self.log_line.emit(f"  · {lanc.filial_nome}/{lanc.tipo_folha}: {msg}")
        self.lancamento_atualizado.emit(getattr(self, "_i_atual", -1))


def rodar_em_thread(worker: QObject) -> QThread:
    """Utilitário: move um worker para uma QThread e inicia."""
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)  # type: ignore[attr-defined]
    worker.error.connect(thread.quit)     # type: ignore[attr-defined]
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread
