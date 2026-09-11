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
            self.log_line.emit(f"-> Enviando '{self.arquivo.name}' para o Gemini...")
            self.log_line.emit("-> Instanciando cliente Gemini (transporte REST)")
            client = GeminiClient(self.api_key, self.modelo)
            self.log_line.emit("-> Cliente pronto; chamando extrair()")
            extracao = client.extrair(self.arquivo, self.imposto)
            self.log_line.emit(
                f"OK Extracao recebida: {len(extracao.get('linhas', []))} linhas, "
                f"referencia {extracao.get('mes_ref','?')}/{extracao.get('ano_ref','?')}"
            )
            lancamentos, nao_resolvidas = montar_lancamentos(
                extracao, self.imposto, self.mapping, self.data_emissao,
            )
            if nao_resolvidas:
                self.log_line.emit(
                    f"[!] {len(nao_resolvidas)} filial(is) nao resolvida(s) no de-para"
                )
            self.log_line.emit(f"OK {len(lancamentos)} lancamentos prontos para revisao")
            self.finished.emit(lancamentos, nao_resolvidas)
        except BaseException as e:  # noqa: BLE001
            log.exception("Falha na extração")
            # Envia tipo + mensagem para a GUI para diagnóstico rápido.
            self.error.emit(f"{type(e).__name__}: {e}")


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

    def __init__(self, lancamentos: list[Lancamento], settings: dict, calibracao, parar_em_falha: bool = False):
        super().__init__()
        self.lancamentos = lancamentos
        self.settings = settings
        self.calibracao = calibracao
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

    def _emit_e_log(self, msg: str) -> None:
        """Emite pro sinal E grava direto no arquivo — se o sinal falhar
        por alguma razão, o log em disco sobrevive."""
        try:
            log.info(msg)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.log_line.emit(msg)
        except Exception:  # noqa: BLE001
            pass

    def run(self) -> None:
        # NUNCA deixa a run morrer sem gravar em algum lugar. Sequência:
        # 1. log em arquivo direto (independente do Qt)
        # 2. tenta emitir sinal pra GUI
        # 3. try/except em cada etapa individual
        try:
            log.info(">> LoteWorker.run() ENTRADA no thread")
            self._emit_e_log(">> LoteWorker.run(): iniciando thread do lote")

            try:
                from ..core.rpa_totvs import EmergencyAbortException, ManualAbortException, RpaTotvs
            except BaseException as e:  # noqa: BLE001
                log.exception("Falha importando rpa_totvs")
                self._emit_e_log(f"XX Falha importando rpa_totvs: {type(e).__name__}: {e}")
                self.error.emit(f"import rpa_totvs falhou: {e}")
                return
            self._emit_e_log(">> Modulo rpa_totvs importado")

            # Auto-detecção via visão computacional. Se der certo, preenche
            # calibracao.campos sem exigir calibração manual do operador.
            try:
                from ..core.visao_totvs import preencher_calibracao_automatica
                ok_visao, msg_visao = preencher_calibracao_automatica(self.calibracao)
                self._emit_e_log(f"[visão] {msg_visao}")
                if not ok_visao:
                    self._emit_e_log("[visão] fallback pra calibração manual salva")
            except BaseException as e:  # noqa: BLE001
                self._emit_e_log(f"[visão] módulo indisponível ({e}) — usando calibração manual")

            try:
                rpa = RpaTotvs(
                    self.settings,
                    self.calibracao,
                    on_progress=self._on_progress,
                    aguardar_confirmacao=self._aguardar_confirmacao,
                )
            except BaseException as e:  # noqa: BLE001
                log.exception("Falha instanciando RpaTotvs")
                self._emit_e_log(f"XX Falha instanciando RpaTotvs: {type(e).__name__}: {e}")
                self.error.emit(f"RpaTotvs() falhou: {e}")
                return
            self._emit_e_log(">> RpaTotvs instanciado")
            self._emit_e_log("-> Conectando à janela do TOTVS...")
            self._emit_e_log("i Tecla END = parada de emergência")
            try:
                try:
                    rpa.conectar()
                except BaseException as e:  # noqa: BLE001
                    log.exception("Falha em rpa.conectar()")
                    self._emit_e_log(f"XX Falha em conectar(): {type(e).__name__}: {e}")
                    raise
                self._emit_e_log("OK Janela conectada")

                sucessos = 0
                falhas = 0
                total = len(self.lancamentos)
                for i, lanc in enumerate(self.lancamentos):
                    if self._cancelar:
                        self.log_line.emit("|| Execução cancelada pelo usuário")
                        break
                    self._i_atual = i
                    self.progresso.emit(i, total, f"{lanc.filial_nome} - {lanc.tipo_folha}")
                    try:
                        rpa.lancar(lanc)
                        sucessos += 1
                    except ManualAbortException:
                        self.log_line.emit("|| Lote interrompido no modo revisão manual")
                        break
                    except EmergencyAbortException:
                        self.log_line.emit("!! EMERGÊNCIA: tecla END pressionada — lote abortado")
                        break
                    except Exception as e:  # noqa: BLE001
                        falhas += 1
                        self.log_line.emit(f"X Falha em {lanc.filial_nome}/{lanc.tipo_folha}: {e}")
                        if self.parar_em_falha:
                            break
                    self.lancamento_atualizado.emit(i)
                self.finished.emit(sucessos, falhas)
            finally:
                rpa.encerrar()
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
