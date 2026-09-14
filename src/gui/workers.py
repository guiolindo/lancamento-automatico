from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from ..core.gemini_client import GeminiClient, montar_lancamentos
from ..core.logger import log
from ..core.mapping import MappingRepository
from ..core.models import Imposto, Lancamento, LinhaExtracao, NotaDespesa, StatusLancamento


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
        data_contabilizacao: date | None = None,
        vencimento: date | None = None,
    ):
        super().__init__()
        self.arquivo = arquivo
        self.api_key = api_key
        self.modelo = modelo
        self.imposto = imposto
        self.mapping = mapping
        self.data_emissao = data_emissao
        # None → montar_lancamentos usa data_emissao como fallback (mesmo
        # comportamento antigo). Passando as 3 explicitamente, ele usa
        # cada uma no campo correto do TOTVS.
        self.data_contabilizacao = data_contabilizacao
        self.vencimento = vencimento

    def run(self) -> None:
        try:
            self.log_line.emit(f"-> Enviando '{self.arquivo.name}' para o Gemini...")
            self.log_line.emit("-> Instanciando cliente Gemini (transporte REST)")
            client = GeminiClient(self.api_key, self.modelo)
            self.log_line.emit("-> Cliente pronto; chamando extrair()")
            extracao = client.extrair(self.arquivo, self.imposto, self.mapping)
            self.log_line.emit(
                f"OK Extracao recebida: {len(extracao.get('linhas', []))} linhas, "
                f"referencia {extracao.get('mes_ref','?')}/{extracao.get('ano_ref','?')}"
            )
            lancamentos, nao_resolvidas = montar_lancamentos(
                extracao, self.imposto, self.mapping, self.data_emissao,
                data_contabilizacao=self.data_contabilizacao,
                vencimento=self.vencimento,
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
            ok_visao = False
            msg_visao = ""
            try:
                from ..core.visao_totvs import preencher_calibracao_automatica
                ok_visao, msg_visao = preencher_calibracao_automatica(self.calibracao)
                self._emit_e_log(f"[visão] {msg_visao}")
                if not ok_visao:
                    self._emit_e_log("[visão] fallback pra calibração manual salva")
            except BaseException as e:  # noqa: BLE001
                msg_visao = f"módulo indisponível: {e}"
                self._emit_e_log(f"[visão] {msg_visao} — usando calibração manual")

            # Pré-check com mensagem HUMANA antes de tentar RpaTotvs.
            # Se a visão falhou E não tem calibração manual salva, o
            # RpaTotvs.__init__ ia estourar 'Calibração incompleta —
            # faltam empresa, especie, pessoa...' que é ininteligível
            # pro usuário final. Aqui traduzimos pra causa real.
            if not ok_visao and not self.calibracao.esta_completa():
                m_low = (msg_visao or "").lower()
                if any(k in m_low for k in ("sumiu", "reconhecer", "pygetwindow", "indisponível", "indisponivel")):
                    friendly = (
                        "Não achei o TOTVS aberto na tela 'Inclusão de Títulos'.\n\n"
                        "Antes de executar:\n"
                        "  1. Abra o TOTVS e vá até a tela 'Inclusão de Títulos' "
                        "(janela 'Operador Financeiro').\n"
                        "  2. Deixe essa janela visível (não minimizada).\n"
                        "  3. Clique em 'Executar no TOTVS' de novo.\n\n"
                        "Se o TOTVS já está aberto e mesmo assim dá esse erro, "
                        "clique em 'Recalibrar (backup)' pra calibrar manualmente uma vez."
                    )
                else:
                    friendly = (
                        f"Não consegui preparar a automação do TOTVS.\n\n"
                        f"Detalhe técnico: {msg_visao}\n\n"
                        "Verifique se o TOTVS está aberto na tela 'Inclusão de "
                        "Títulos' e tente de novo. Se persistir, calibre "
                        "manualmente com o botão 'Recalibrar (backup)'."
                    )
                self._emit_e_log("XX " + friendly.replace("\n", " "))
                self.error.emit(friendly)
                return

            try:
                rpa = RpaTotvs(
                    self.settings,
                    self.calibracao,
                    on_progress=self._on_progress,
                    aguardar_confirmacao=self._aguardar_confirmacao,
                )
            except BaseException as e:  # noqa: BLE001
                log.exception("Falha instanciando RpaTotvs")
                # Traduz a exceção interna pra linguagem humana quando
                # for reconhecível.
                msg = str(e)
                if "Calibração incompleta" in msg or "Calibracao incompleta" in msg:
                    friendly = (
                        "A configuração dos campos do TOTVS está incompleta.\n\n"
                        "Isso normalmente acontece quando o TOTVS não estava "
                        "aberto na tela certa quando você apertou 'Executar'. "
                        "Abra o TOTVS na tela 'Inclusão de Títulos' e tente "
                        "de novo."
                    )
                else:
                    friendly = f"Não consegui preparar a automação:\n\n{msg}"
                self._emit_e_log(f"XX {friendly}")
                self.error.emit(friendly)
                return
            self._emit_e_log(">> RpaTotvs instanciado")
            self._emit_e_log("-> Conectando à janela do TOTVS...")
            self._emit_e_log("i Tecla END = parada de emergência")
            try:
                try:
                    rpa.conectar()
                except BaseException as e:  # noqa: BLE001
                    log.exception("Falha em rpa.conectar()")
                    msg = str(e)
                    if "não encontrada" in msg or "nao encontrada" in msg:
                        friendly = (
                            "A janela 'Operador Financeiro' do TOTVS não "
                            "apareceu no tempo esperado.\n\n"
                            "Verifique se:\n"
                            "  • O TOTVS está aberto\n"
                            "  • A tela 'Inclusão de Títulos' está ativa\n"
                            "  • A janela não está minimizada"
                        )
                    else:
                        friendly = f"Não consegui conectar ao TOTVS:\n\n{msg}"
                    self._emit_e_log(f"XX {friendly}")
                    self.error.emit(friendly)
                    return
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


class LoteOrcamentoWorker(QObject):
    """Executa o lote do módulo Orçamento (Notas Fiscais de Despesa).
    Paralelo ao `LoteWorker`, mas usa `RpaOrcamento` + template do fornecedor.
    """
    progresso = Signal(int, int, str)         # index, total, mensagem
    nota_atualizada = Signal(int)             # index
    finished = Signal(int, int, int)          # sucessos, falhas, ignoradas
    error = Signal(str)
    log_line = Signal(str)

    def __init__(
        self,
        notas: list[NotaDespesa],
        template: dict,
        settings: dict,
        calibracao,
        parar_em_falha: bool = False,
    ):
        super().__init__()
        self.notas = notas
        self.template = template
        self.settings = settings
        self.calibracao = calibracao
        self.parar_em_falha = parar_em_falha
        self._cancelar = False

    def cancelar(self) -> None:
        self._cancelar = True

    def _emit_e_log(self, msg: str) -> None:
        try:
            log.info(msg)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.log_line.emit(msg)
        except Exception:  # noqa: BLE001
            pass

    def run(self) -> None:
        try:
            self._emit_e_log(">> LoteOrcamentoWorker.run(): iniciando")

            try:
                from ..core.rpa_orcamento import EmergencyAbortException, RpaOrcamento
            except BaseException as e:  # noqa: BLE001
                log.exception("Falha importando rpa_orcamento")
                self.error.emit(f"import rpa_orcamento falhou: {e}")
                return

            # Auto-detecção visual (build-97). Se a visão baseada em
            # template matching enxergar o cabeçalho 'Notas Fiscais de
            # Despesas', ela preenche os 23 campos sozinha e o operador
            # NÃO precisa calibrar. Fallback pra calibração manual salva
            # se a visão falhar.
            ok_visao = False
            msg_visao = ""
            try:
                from ..core.visao_orcamento import preencher_calibracao_automatica as visao_orc
                ok_visao, msg_visao = visao_orc(self.calibracao)
                self._emit_e_log(f"[visão orçamento] {msg_visao}")
                if not ok_visao:
                    self._emit_e_log("[visão orçamento] fallback pra calibração manual salva")
            except BaseException as e:  # noqa: BLE001
                msg_visao = f"módulo indisponível: {e}"
                self._emit_e_log(f"[visão orçamento] {msg_visao} — usando calibração manual")

            if not ok_visao and not self.calibracao.esta_completa():
                m_low = (msg_visao or "").lower()
                if any(k in m_low for k in ("reconhecer", "sumiu", "pygetwindow", "indisponível", "indisponivel")):
                    friendly = (
                        "Não achei o TOTVS aberto na tela 'Notas Fiscais de Despesas'.\n\n"
                        "Antes de executar:\n"
                        "  1. Abra o TOTVS Orçamento e vá até 'Notas Fiscais "
                        "de Despesas'.\n"
                        "  2. Deixe a janela visível (não minimizada).\n"
                        "  3. Clique em 'Executar no TOTVS' de novo.\n\n"
                        "Se persistir, use 'Calibrar tela' pra calibração manual."
                    )
                else:
                    faltam = self.calibracao.falta_calibrar()
                    friendly = (
                        "A calibração da tela Orçamento está incompleta.\n\n"
                        "Faltam: " + ", ".join(faltam[:8])
                        + ("..." if len(faltam) > 8 else "")
                        + "\n\nUse 'Calibrar tela' no dialog Orçamento."
                    )
                self._emit_e_log(f"XX {friendly}")
                self.error.emit(friendly)
                return

            try:
                rpa = RpaOrcamento(
                    self.settings, self.calibracao, self.template,
                    on_progress=self._on_progress,
                )
            except BaseException as e:  # noqa: BLE001
                log.exception("Falha instanciando RpaOrcamento")
                self.error.emit(f"Não consegui preparar a automação:\n\n{e}")
                return

            self._emit_e_log("-> Conectando à janela Orçamento...")
            self._emit_e_log("i Tecla END = parada de emergência")

            try:
                try:
                    rpa.conectar()
                except BaseException as e:  # noqa: BLE001
                    log.exception("Falha em rpa.conectar()")
                    msg = str(e)
                    if "não encontrada" in msg or "nao encontrada" in msg:
                        friendly = (
                            "A janela 'Orçamento' do TOTVS não apareceu.\n\n"
                            "Verifique se:\n"
                            "  • O TOTVS está aberto na tela 'Notas Fiscais de Despesa'\n"
                            "  • A janela começa com 'Orçamento'\n"
                            "  • A janela não está minimizada"
                        )
                    else:
                        friendly = f"Não consegui conectar ao TOTVS:\n\n{msg}"
                    self.error.emit(friendly)
                    return
                self._emit_e_log("OK Janela conectada")

                sucessos = falhas = ignoradas = 0
                total = len(self.notas)
                for i, nota in enumerate(self.notas):
                    if self._cancelar:
                        self._emit_e_log("|| Execução cancelada pelo usuário")
                        break
                    self._i_atual = i
                    self.progresso.emit(i, total, f"Nota #{nota.numero or '(vazio)'} — pág {nota.pagina}")
                    try:
                        rpa.lancar(nota)
                        if nota.status == StatusLancamento.SUCESSO:
                            sucessos += 1
                        elif nota.status == StatusLancamento.IGNORADO:
                            ignoradas += 1
                    except EmergencyAbortException:
                        self._emit_e_log("!! EMERGÊNCIA: END pressionada — lote abortado")
                        break
                    except Exception as e:  # noqa: BLE001
                        falhas += 1
                        self._emit_e_log(f"X Falha nota #{nota.numero}: {e}")
                        if self.parar_em_falha:
                            break
                    self.nota_atualizada.emit(i)
                self.finished.emit(sucessos, falhas, ignoradas)
            finally:
                rpa.encerrar()
        except Exception as e:  # noqa: BLE001
            log.exception("Falha no lote Orçamento")
            self.error.emit(str(e))

    def _on_progress(self, nota: NotaDespesa, msg: str) -> None:
        self.log_line.emit(f"  · Nota #{nota.numero or '?'}: {msg}")
        self.nota_atualizada.emit(getattr(self, "_i_atual", -1))


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
