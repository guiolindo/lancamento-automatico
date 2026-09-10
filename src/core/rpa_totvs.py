"""
RPA da tela 'Inclusão de Títulos' do TOTVS, otimizado para RemoteApp.

Como a janela do TOTVS é um app remoto rodando em VM (Auto Sky) que
aparece flutuando no PC do usuário, `pywinauto` NÃO consegue enxergar
os controles internos. Estratégia: coordenadas relativas ao canto da
janela, capturadas via calibração inicial, e cliques/teclado via
`pyautogui`. Isso funciona porque:
- `pygetwindow` lê o retângulo da janela local (o quadro do RDP).
- `pyautogui.click(x, y)` envia clique em pixel absoluto — o RDP repassa
  pra dentro da VM.
- Teclado (`pyautogui.hotkey`, `typewrite`, `press`) idem.
- Detecção de popup de erro: `pygetwindow` lista todas as janelas
  visíveis, e o popup do TOTVS aparece como janela separada com título
  contendo "Atenção".
"""

from __future__ import annotations

import random
import threading
import time
from typing import Callable, Optional

from .calibracao import Calibracao
from .logger import log
from .models import Lancamento, StatusLancamento


# Códigos de tecla virtuais do Windows (para GetAsyncKeyState).
VK_END = 0x23
VK_ESCAPE = 0x1B


def _gerar_nro_documento() -> str:
    """7 dígitos aleatórios (mesma cardinalidade dos exemplos do TOTVS)."""
    return str(random.randint(1_000_000, 9_999_999))


class ManualAbortException(RuntimeError):
    """O operador pediu para parar o lote no modo revisão manual."""


class EmergencyAbortException(RuntimeError):
    """O operador apertou a tecla de emergência (END)."""


def _trazer_para_frente(win) -> None:
    """DESABILITADO por causa de travamentos suspeitos.

    Antes tentava SetForegroundWindow + keybd_event(Alt) — parece que essa
    combinação estava causando o Executar 'travar' no PC do usuário
    (provavelmente uma race no user32 ou proteção de roubo de foco).
    Operador deixa o TOTVS visível manualmente antes de rodar.
    """
    log.info("_trazer_para_frente: NO-OP (deixe o TOTVS visível manualmente)")


class RpaTotvs:
    def __init__(
        self,
        settings: dict,
        calibracao: Calibracao,
        on_progress: Optional[Callable[[Lancamento, str], None]] = None,
        aguardar_confirmacao: Optional[Callable[[Lancamento], bool]] = None,
    ):
        if not calibracao.esta_completa():
            faltam = calibracao.falta_calibrar()
            raise RuntimeError(
                "Calibração incompleta — faltam os campos: " + ", ".join(faltam)
            )
        self.settings = settings
        self.calibracao = calibracao
        self.on_progress = on_progress
        self.aguardar_confirmacao = aguardar_confirmacao
        self._delays = settings.get("delays", {})
        self._rpa_cfg = settings.get("rpa", {})
        self._win = None  # janela do TOTVS
        # Emergência: END global cancela o lote imediatamente.
        self._abort_event = threading.Event()
        self._hotkey_thread: Optional[threading.Thread] = None

    # ---------- conexão ----------

    def conectar(self) -> None:
        log.info("conectar(): iniciando")
        self._start_hotkey_watcher()
        log.info("conectar(): hotkey watcher (END) ativo")

        titulo = (self.calibracao.titulo_janela or "").strip()
        if not titulo:
            log.info("conectar(): modo absoluto (sem título de janela)")
            self._win = None
            return

        log.info("conectar(): importando pygetwindow")
        import pygetwindow as gw
        log.info("conectar(): pygetwindow importado")
        timeout = int(self._delays.get("timeout_janela_s", 30))
        deadline = time.time() + timeout
        log.info("conectar(): procurando janela contendo '%s' (timeout %ds)", titulo, timeout)
        tentativa = 0
        while time.time() < deadline:
            tentativa += 1
            try:
                todas = gw.getAllWindows()
            except Exception as e:  # noqa: BLE001
                log.exception("conectar(): erro em getAllWindows(): %s", e)
                raise
            janelas = [w for w in todas if titulo.lower() in (w.title or "").lower()]
            if janelas:
                self._win = janelas[0]
                log.info("conectar(): janela achada na tentativa %d: '%s'", tentativa, self._win.title)
                _trazer_para_frente(self._win)
                log.info("conectar(): janela em (%d, %d) tamanho %dx%d",
                         self._win.left, self._win.top,
                         self._win.width, self._win.height)
                return
            log.info("conectar(): tentativa %d — %d janelas visíveis, nenhuma casou", tentativa, len(todas))
            time.sleep(0.5)
        raise RuntimeError(f"Janela '{titulo}' não encontrada em {timeout}s")

    def encerrar(self) -> None:
        """Para o hotkey watcher — chamado ao fim do lote."""
        self._abort_event.set()

    # ---------- emergência ----------

    def _start_hotkey_watcher(self) -> None:
        if self._hotkey_thread and self._hotkey_thread.is_alive():
            return

        def watcher() -> None:
            try:
                import ctypes
                user32 = ctypes.windll.user32
            except Exception:  # noqa: BLE001
                return
            while not self._abort_event.is_set():
                try:
                    if user32.GetAsyncKeyState(VK_END) & 0x8000:
                        log.warning("Tecla END pressionada — abortando lote")
                        self._abort_event.set()
                        return
                except Exception:  # noqa: BLE001
                    return
                time.sleep(0.05)

        self._hotkey_thread = threading.Thread(target=watcher, daemon=True)
        self._hotkey_thread.start()

    def _check_abort(self) -> None:
        if self._abort_event.is_set():
            raise EmergencyAbortException("Cancelado pela tecla END")

    # ---------- helpers de click/teclado ----------

    def _pos_abs(self, campo: str) -> tuple[int, int]:
        ox, oy = self.calibracao.campos[campo]
        if self._win is None:
            # Modo absoluto: ox/oy já são coordenadas de tela.
            return int(ox), int(oy)
        wx, wy = self._win.left, self._win.top
        return int(wx + ox), int(wy + oy)

    def _sleep(self, chave: str, default_ms: int = 400) -> None:
        ms = int(self._delays.get(chave, default_ms))
        time.sleep(ms / 1000.0)

    def _clicar(self, campo: str) -> None:
        import pyautogui
        x, y = self._pos_abs(campo)
        pyautogui.click(x, y)
        self._sleep("apos_click_ms")

    def _preencher(self, campo: str, valor: str) -> None:
        """Triple-click + Ctrl+A + Backspace × 15 + typewrite(UPPERCASE).

        Belt AND suspenders: se uma abordagem falhar, a próxima pega.
        - Triple-click: seleciona a linha inteira em TEdit Delphi comum.
        - Ctrl+A: redundância, seleciona tudo em campos que respondem a atalho.
        - Backspace × 15: apaga o que sobrar (campos mascarados que
          ignoraram as duas seleções).
        - typewrite: envia tecla por tecla (funciona em máscaras).
        - .upper(): Observação e alguns campos exigem maiúsculas.
        """
        self._check_abort()
        valor_up = valor.upper() if isinstance(valor, str) else str(valor)
        log.info("preencher %s = %r", campo, valor_up)
        import pyautogui
        x, y = self._pos_abs(campo)

        # Triple-click coloca o cursor E seleciona o conteúdo da linha
        pyautogui.tripleClick(x, y)
        self._sleep("apos_click_ms")

        # Redundância: Ctrl+A
        pyautogui.hotkey("ctrl", "a")
        self._sleep("apos_selectall_ms")

        # Ultima redundância: apaga o que sobrou
        pyautogui.press("backspace", presses=15, interval=0.005)
        self._sleep("apos_selectall_ms")

        # Digita o valor (maiúsculo)
        intervalo = float(self._delays.get("intervalo_digitacao_s", 0.005))
        pyautogui.typewrite(valor_up, interval=intervalo)
        self._sleep("apos_typewrite_ms")
        self._sleep("entre_campos_ms")

    # ---------- popup de duplicidade ----------

    def _achar_popup(self):
        """Retorna a janela top-level do popup 'Atenção' se existir.

        Em RemoteApp o popup NÃO aparece como janela top-level (fica dentro
        do Operador Financeiro). Esse método só funciona se o TOTVS rodar
        localmente. Preferir _popup_por_pixel() quando calibrado.
        """
        import pygetwindow as gw
        try:
            titulo_pai = ((self._win.title if self._win else "") or "").lower()
            for w in gw.getAllWindows():
                t = (w.title or "").lower()
                if any(k in t for k in ("atenção", "atencao", "aviso", "erro")):
                    if titulo_pai and t == titulo_pai:
                        continue
                    return w
        except Exception:  # noqa: BLE001
            pass
        return None

    def _popup_por_pixel(self) -> bool:
        """Verifica se o pixel calibrado 'popup_indicador' está com a cor
        de referência. Funciona em RemoteApp porque só lê o pixel na tela
        local (que reflete o que a VM está renderizando).
        """
        if "popup_indicador" not in self.calibracao.campos:
            return False
        if "popup_indicador" not in self.calibracao.cores:
            return False
        try:
            import pyautogui
            x, y = self._pos_abs("popup_indicador")
            atual = pyautogui.pixel(x, y)
            ref = self.calibracao.cores["popup_indicador"]
            dist = sum(abs(int(a) - int(b)) for a, b in zip(atual, ref))
            # Tolerância folgada — RemoteApp pode variar cor ligeiramente
            # por compressão do RDP.
            match = dist < 60
            if match:
                log.info("Popup detectado por pixel: atual=%s ref=%s dist=%d",
                         atual, ref, dist)
            return match
        except Exception:  # noqa: BLE001
            log.exception("Falha lendo pixel de popup")
            return False

    def _popup_duplicidade(self) -> bool:
        # Preferência: pixel calibrado (funciona em RemoteApp).
        if self._popup_por_pixel():
            return True
        # Fallback: janela top-level (só funciona com TOTVS local).
        p = self._achar_popup()
        if p is not None:
            log.info("Popup (janela top-level) detectado: '%s'", p.title)
            return True
        return False

    def _fechar_popup(self) -> None:
        import pyautogui
        # 1o: se botão OK calibrado, clica exatamente lá.
        if "popup_ok" in self.calibracao.campos:
            x, y = self._pos_abs("popup_ok")
            log.info("Fechando popup: click em popup_ok (%d, %d)", x, y)
            pyautogui.moveTo(x, y, duration=0.05)
            pyautogui.click(x, y)
            time.sleep(0.5)
            if not self._popup_por_pixel():
                return

        # 2o: se detectou janela top-level, click no centro-inferior dela.
        p = self._achar_popup()
        if p is not None:
            try:
                p.activate()
                time.sleep(0.2)
            except Exception:  # noqa: BLE001
                pass
            cx = int(p.left + p.width / 2)
            cy = int(p.top + p.height - 30)
            pyautogui.moveTo(cx, cy, duration=0.05)
            pyautogui.click(cx, cy)
            time.sleep(0.5)

        # 3o: redundância com teclado.
        if self._popup_por_pixel() or self._achar_popup() is not None:
            pyautogui.press("enter")
            time.sleep(0.3)
        if self._popup_por_pixel() or self._achar_popup() is not None:
            pyautogui.press("space")
            time.sleep(0.3)
        if self._popup_por_pixel() or self._achar_popup() is not None:
            log.warning("Popup NÃO fechou apesar de click OK + enter + space")

    # ---------- fluxo principal ----------

    def lancar(self, lanc: Lancamento) -> None:
        max_tent = int(self._rpa_cfg.get("max_tentativas_duplicidade", 10))
        lanc.status = StatusLancamento.EM_ANDAMENTO
        self._notificar(lanc, "Iniciando")
        self._check_abort()

        try:
            # Re-força o TOTVS pra frente a cada lançamento — o operador pode
            # ter clicado em outro app e voltado.
            if self._win is not None:
                _trazer_para_frente(self._win)

            # Cabeçalho — só uma vez por lançamento.
            self._preencher_cabecalho(lanc)

            for tentativa in range(1, max_tent + 1):
                lanc.tentativas = tentativa

                lanc.nro_documento = _gerar_nro_documento()
                self._preencher("nro_documento", lanc.nro_documento)

                self._preencher_datas_e_valor(lanc)

                self._notificar(lanc, f"Tentativa {tentativa}: Gerar Parcelas")
                self._clicar("btn_gerar_parcelas")
                self._sleep("apos_gerar_parcelas_ms", 1500)

                if self._popup_duplicidade():
                    log.warning("Nro %s duplicado — nova tentativa", lanc.nro_documento)
                    self._fechar_popup()
                    continue

                if bool(self._rpa_cfg.get("confirmar_automaticamente", True)):
                    self._clicar("btn_confirmar")
                    self._sleep("apos_confirmar_ms", 2000)
                    lanc.status = StatusLancamento.SUCESSO
                    self._notificar(lanc, "Sucesso")
                    return

                # Modo revisão manual: pausa esperando operador.
                self._notificar(lanc, "Preenchido — confira e aperte + no TOTVS")
                prosseguir = True
                if self.aguardar_confirmacao is not None:
                    prosseguir = self.aguardar_confirmacao(lanc)
                if not prosseguir:
                    raise ManualAbortException("Lote interrompido pelo operador")
                lanc.status = StatusLancamento.SUCESSO
                return

            raise RuntimeError(f"Falhou após {max_tent} tentativas de Nro.Documento")
        except ManualAbortException:
            raise
        except EmergencyAbortException:
            raise
        except Exception as e:  # noqa: BLE001
            lanc.status = StatusLancamento.FALHA
            lanc.erro = str(e)
            self._notificar(lanc, f"Falha: {e}")
            log.exception("Falha no lançamento %s / %s", lanc.filial_codigo, lanc.tipo_folha)
            raise

    def _preencher_cabecalho(self, lanc: Lancamento) -> None:
        self._preencher("empresa", str(lanc.filial_codigo))
        self._preencher("especie", lanc.especie)
        self._sleep("apos_especie_ms", 800)  # aguarda auto-preencher banco/agência
        self._preencher("pessoa", str(lanc.pessoa_codigo))
        self._sleep("apos_pessoa_ms", 800)  # aguarda auto-preencher P.Nota
        self._preencher("observacao", lanc.observacao)

    def _preencher_datas_e_valor(self, lanc: Lancamento) -> None:
        emi = lanc.data_emissao.strftime("%d/%m/%Y")
        cont = lanc.data_contabilizacao.strftime("%d/%m/%Y")
        venc = lanc.vencimento.strftime("%d/%m/%Y")
        valor = f"{lanc.valor:.2f}".replace(".", ",")
        self._preencher("dt_emissao", emi)
        self._preencher("dt_contabilizacao", cont)
        self._preencher("vencimento", venc)
        self._preencher("valor", valor)

    def _notificar(self, lanc: Lancamento, msg: str) -> None:
        if self.on_progress:
            try:
                self.on_progress(lanc, msg)
            except Exception:  # noqa: BLE001
                log.exception("on_progress callback falhou")


def executar_lote(
    lancamentos: list[Lancamento],
    settings: dict,
    calibracao: Calibracao,
    on_progress: Optional[Callable[[Lancamento, str], None]] = None,
    aguardar_confirmacao: Optional[Callable[[Lancamento], bool]] = None,
    parar_em_falha: bool = False,
) -> tuple[int, int]:
    rpa = RpaTotvs(settings, calibracao, on_progress=on_progress, aguardar_confirmacao=aguardar_confirmacao)
    try:
        rpa.conectar()

        sucessos = 0
        falhas = 0
        for lanc in lancamentos:
            try:
                rpa.lancar(lanc)
                sucessos += 1
            except (ManualAbortException, EmergencyAbortException):
                break
            except Exception:  # noqa: BLE001
                falhas += 1
                if parar_em_falha:
                    break
        return sucessos, falhas
    finally:
        rpa.encerrar()
