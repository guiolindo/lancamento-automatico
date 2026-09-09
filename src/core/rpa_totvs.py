from __future__ import annotations

import random
import threading
import time
from typing import Callable, Optional

from .logger import log
from .models import Lancamento, StatusLancamento


def _gerar_nro_documento() -> str:
    """7 dígitos aleatórios (mesma cardinalidade dos exemplos do TOTVS)."""
    return str(random.randint(1_000_000, 9_999_999))


class ManualAbortException(RuntimeError):
    """O operador pediu para parar o lote no modo revisão manual."""


class RpaTotvs:
    """
    Automação da tela 'Inclusão de Títulos' do TOTVS/Consinco (Operador
    Financeiro). Preenche campo a campo por UI Automation (pywinauto) com
    fallback por teclado. Cada método pequeno pra facilitar debug por print.
    """

    def __init__(
        self,
        settings: dict,
        on_progress: Optional[Callable[[Lancamento, str], None]] = None,
        aguardar_confirmacao: Optional[Callable[[Lancamento], bool]] = None,
    ):
        self.settings = settings
        self.on_progress = on_progress
        # Callback bloqueante retornando True para prosseguir ou False para
        # abortar o lote. Usado em modo manual (confirmar_automaticamente=False)
        # depois que o robô preenche e clica Gerar Parcelas.
        self.aguardar_confirmacao = aguardar_confirmacao
        self._app = None
        self._janela = None
        self._delays = settings.get("delays", {})
        self._rpa_cfg = settings.get("rpa", {})

    # ---------- infra de janela ----------

    def conectar(self) -> None:
        """Localiza a janela 'Inclusão de Títulos' já aberta pelo usuário."""
        from pywinauto import Desktop  # import atrasado (só existe em Windows)
        titulo = self._rpa_cfg.get("titulo_janela", "Inclusão de Títulos")
        timeout = int(self._rpa_cfg.get("timeout_janela_s", 20))
        log.info("Procurando janela '%s'", titulo)
        deadline = time.time() + timeout
        last_err: Optional[Exception] = None
        while time.time() < deadline:
            try:
                win = Desktop(backend="uia").window(title_re=f".*{titulo}.*")
                win.wait("visible", timeout=1)
                self._janela = win
                log.info("Janela localizada")
                return
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(0.5)
        raise RuntimeError(f"Janela '{titulo}' não encontrada em {timeout}s: {last_err}")

    def _sleep(self, chave: str, default_ms: int = 150) -> None:
        ms = int(self._delays.get(chave, default_ms))
        time.sleep(ms / 1000.0)

    # ---------- helpers de preenchimento ----------

    def _campo(self, nome_auto_id: str):
        """
        Tenta várias estratégias: auto_id → title → best_match. Cada nome
        de campo pode variar em builds diferentes do TOTVS; concentramos
        aqui pra facilitar ajuste por screenshot.
        """
        candidatos = [
            {"auto_id": nome_auto_id},
            {"title": nome_auto_id},
            {"best_match": nome_auto_id},
        ]
        for kwargs in candidatos:
            try:
                ctrl = self._janela.child_window(**kwargs, control_type="Edit")
                ctrl.wait("visible", timeout=2)
                return ctrl
            except Exception:  # noqa: BLE001
                continue
        raise LookupError(f"Campo não encontrado: {nome_auto_id}")

    def _preencher(self, campo_nome: str, valor: str) -> None:
        ctrl = self._campo(campo_nome)
        ctrl.set_focus()
        try:
            ctrl.set_edit_text("")
            ctrl.type_keys(valor, with_spaces=True, set_foreground=False)
        except Exception:
            # fallback: pyautogui
            import pyautogui
            pyautogui.typewrite(valor, interval=0.02)
        self._sleep("entre_campos_ms")

    def _tab(self) -> None:
        import pyautogui
        pyautogui.press("tab")
        self._sleep("entre_campos_ms")

    def _clicar_botao(self, nome: str) -> None:
        btn = self._janela.child_window(title=nome, control_type="Button")
        btn.wait("enabled", timeout=5)
        btn.click_input()

    # ---------- fluxo principal ----------

    def lancar(self, lanc: Lancamento) -> None:
        """Executa um único lançamento. Atualiza status no objeto."""
        max_tent = int(self._rpa_cfg.get("max_tentativas_duplicidade", 10))
        lanc.status = StatusLancamento.EM_ANDAMENTO
        self._notificar(lanc, "Iniciando lançamento")

        try:
            self._preencher_cabecalho(lanc)

            for tentativa in range(1, max_tent + 1):
                lanc.tentativas = tentativa
                lanc.nro_documento = _gerar_nro_documento()
                self._preencher("Nro.Documento", lanc.nro_documento)
                self._tab()  # dispara auto-preencher Nro Título

                self._preencher_datas_e_valor(lanc)

                self._notificar(lanc, f"Tentativa {tentativa}: Gerar Parcelas")
                self._clicar_botao("Gerar Parcelas")
                self._sleep("apos_gerar_parcelas_ms", 1500)

                if self._popup_duplicidade():
                    log.warning("Nro %s duplicado; nova tentativa", lanc.nro_documento)
                    self._fechar_popup()
                    continue

                if bool(self._rpa_cfg.get("confirmar_automaticamente", True)):
                    self._confirmar_inclusao()
                    lanc.status = StatusLancamento.SUCESSO
                    self._notificar(lanc, "Sucesso")
                    return

                # Modo revisão manual: robô preencheu e apertou Gerar Parcelas.
                # Bloqueia até o operador conferir na tela, apertar "+" e
                # dizer "continuar" (ou "parar") no aviso da GUI.
                self._notificar(
                    lanc,
                    "Preenchido — confira e aperte + no TOTVS, depois clique Continuar",
                )
                prosseguir = True
                if self.aguardar_confirmacao is not None:
                    prosseguir = self.aguardar_confirmacao(lanc)
                if not prosseguir:
                    raise ManualAbortException("Lote interrompido pelo operador")
                lanc.status = StatusLancamento.SUCESSO
                return

            raise RuntimeError(f"Falhou após {max_tent} tentativas de Nro.Documento")
        except Exception as e:  # noqa: BLE001
            lanc.status = StatusLancamento.FALHA
            lanc.erro = str(e)
            self._notificar(lanc, f"Falha: {e}")
            log.exception("Falha lançando %s / %s", lanc.filial_codigo, lanc.tipo_folha)
            raise

    # ---------- subrotinas do fluxo ----------

    def _preencher_cabecalho(self, lanc: Lancamento) -> None:
        self._preencher("Empresa", str(lanc.filial_codigo))
        self._tab()
        self._preencher("Espécie", lanc.especie)
        self._tab()
        self._sleep("apos_especie_ms", 800)  # aguarda auto-preencher banco/agência/depositário
        self._preencher("Pessoa", str(lanc.pessoa_codigo))
        self._tab()
        self._sleep("apos_pessoa_ms", 800)  # aguarda auto-preencher P.Nota
        self._preencher("Observação", lanc.observacao)
        self._tab()

    def _preencher_datas_e_valor(self, lanc: Lancamento) -> None:
        emi = lanc.data_emissao.strftime("%d/%m/%Y")
        cont = lanc.data_contabilizacao.strftime("%d/%m/%Y")
        venc = lanc.vencimento.strftime("%d/%m/%Y")
        valor = f"{lanc.valor:.2f}".replace(".", ",")

        self._preencher("Dt.Emissão", emi)
        self._tab()
        self._preencher("Valor Faturado", valor)
        self._tab()
        self._preencher("Dt.Contabilização", cont)
        self._tab()
        self._preencher("Vencimento Inicial", venc)
        self._tab()

    def _popup_duplicidade(self) -> bool:
        """Detecta popup de erro após 'Gerar Parcelas'."""
        try:
            from pywinauto import Desktop
            desk = Desktop(backend="uia")
            for w in desk.windows():
                try:
                    t = (w.window_text() or "").lower()
                    if any(k in t for k in ("erro", "aviso", "atenção", "duplic")):
                        return True
                except Exception:  # noqa: BLE001
                    continue
        except Exception:  # noqa: BLE001
            pass
        return False

    def _fechar_popup(self) -> None:
        import pyautogui
        pyautogui.press("enter")
        time.sleep(0.4)

    def _confirmar_inclusao(self) -> None:
        """Clica no botão '+' verde no topo pra confirmar o lançamento."""
        self._clicar_botao("+")
        self._sleep("apos_confirmar_ms", 2000)

    # ---------- utilidades ----------

    def _notificar(self, lanc: Lancamento, msg: str) -> None:
        if self.on_progress:
            try:
                self.on_progress(lanc, msg)
            except Exception:  # noqa: BLE001
                log.exception("on_progress callback falhou")


def executar_lote(
    lancamentos: list[Lancamento],
    settings: dict,
    on_progress: Optional[Callable[[Lancamento, str], None]] = None,
    aguardar_confirmacao: Optional[Callable[[Lancamento], bool]] = None,
    parar_em_falha: bool = False,
) -> tuple[int, int]:
    """
    Executa uma lista de lançamentos em sequência. Retorna (sucessos, falhas).
    """
    rpa = RpaTotvs(settings, on_progress=on_progress, aguardar_confirmacao=aguardar_confirmacao)
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
