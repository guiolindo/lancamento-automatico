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
import time
from typing import Callable, Optional

from .calibracao import Calibracao
from .logger import log
from .models import Lancamento, StatusLancamento


def _gerar_nro_documento() -> str:
    """7 dígitos aleatórios (mesma cardinalidade dos exemplos do TOTVS)."""
    return str(random.randint(1_000_000, 9_999_999))


class ManualAbortException(RuntimeError):
    """O operador pediu para parar o lote no modo revisão manual."""


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

    # ---------- conexão ----------

    def conectar(self) -> None:
        titulo = (self.calibracao.titulo_janela or "").strip()
        if not titulo:
            # Modo absoluto: offsets são coordenadas de tela. Sem janela pra
            # localizar. Isso funciona desde que o TOTVS não seja movido.
            log.info("RpaTotvs: modo absoluto (sem título de janela)")
            self._win = None
            return

        import pygetwindow as gw
        timeout = int(self._delays.get("timeout_janela_s", 20))
        deadline = time.time() + timeout
        log.info("RpaTotvs: procurando janela '%s'", titulo)
        while time.time() < deadline:
            janelas = [w for w in gw.getAllWindows() if titulo.lower() in (w.title or "").lower()]
            if janelas:
                self._win = janelas[0]
                try:
                    self._win.activate()
                except Exception:  # noqa: BLE001
                    pass
                log.info("RpaTotvs: janela em (%d, %d) tamanho %dx%d",
                         self._win.left, self._win.top,
                         self._win.width, self._win.height)
                time.sleep(0.3)
                return
            time.sleep(0.5)
        raise RuntimeError(f"Janela '{titulo}' não encontrada em {timeout}s")

    # ---------- helpers de click/teclado ----------

    def _pos_abs(self, campo: str) -> tuple[int, int]:
        ox, oy = self.calibracao.campos[campo]
        if self._win is None:
            # Modo absoluto: ox/oy já são coordenadas de tela.
            return int(ox), int(oy)
        wx, wy = self._win.left, self._win.top
        return int(wx + ox), int(wy + oy)

    def _sleep(self, chave: str, default_ms: int = 150) -> None:
        ms = int(self._delays.get(chave, default_ms))
        time.sleep(ms / 1000.0)

    def _clicar(self, campo: str) -> None:
        import pyautogui
        x, y = self._pos_abs(campo)
        pyautogui.click(x, y)
        self._sleep("entre_campos_ms")

    def _limpar_campo(self) -> None:
        """Ctrl+A + Delete pra apagar valor existente (datas pré-preenchidas)."""
        import pyautogui
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.05)
        pyautogui.press("delete")
        time.sleep(0.05)

    def _colar(self, texto: str) -> None:
        import pyautogui
        try:
            import pyperclip
            pyperclip.copy(texto)
            pyautogui.hotkey("ctrl", "v")
        except Exception:  # noqa: BLE001
            # fallback: digita direto
            pyautogui.typewrite(texto, interval=0.02)
        time.sleep(0.05)

    def _preencher(self, campo: str, valor: str) -> None:
        self._clicar(campo)
        self._limpar_campo()
        self._colar(valor)

    # ---------- popup de duplicidade ----------

    def _popup_duplicidade(self) -> bool:
        import pygetwindow as gw
        try:
            titulo_pai = ((self._win.title if self._win else "") or "").lower()
            for w in gw.getAllWindows():
                t = (w.title or "").lower()
                if any(k in t for k in ("atenção", "atencao", "aviso", "erro")):
                    if titulo_pai and t == titulo_pai:
                        continue
                    log.info("Popup detectado: '%s'", w.title)
                    return True
        except Exception:  # noqa: BLE001
            pass
        return False

    def _fechar_popup(self) -> None:
        import pyautogui
        pyautogui.press("enter")
        time.sleep(0.4)

    # ---------- fluxo principal ----------

    def lancar(self, lanc: Lancamento) -> None:
        max_tent = int(self._rpa_cfg.get("max_tentativas_duplicidade", 10))
        lanc.status = StatusLancamento.EM_ANDAMENTO
        self._notificar(lanc, "Iniciando")

        try:
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
    rpa.conectar()

    sucessos = 0
    falhas = 0
    for lanc in lancamentos:
        try:
            rpa.lancar(lanc)
            sucessos += 1
        except ManualAbortException:
            break
        except Exception:  # noqa: BLE001
            falhas += 1
            if parar_em_falha:
                break
    return sucessos, falhas
