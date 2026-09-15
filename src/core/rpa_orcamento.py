"""
RPA da tela 'Notas Fiscais de Despesa' do TOTVS Orçamento (build-103).

Fluxo por nota:

  1. Aba Nota — cabeçalho: empresa, nat.despesa, pessoa.
  2. Aba Nota — digita **Nº Nota Fiscal** e **verifica duplicidade
     JÁ AQUI**. O TOTVS valida esse campo no OnLeaveFocus e mostra
     popup "Aviso" imediatamente — não precisa esperar o "+".
     Se popup aparecer:
        - `duplicidade_regra: pular_ja_lancada` → OK → F2 → popup
          Atenção "Sim" → nota IGNORADA (nunca inventamos número,
          é NF real).
  3. Sem popup → continua aba Nota (datas, obs, valor, ICMS).
  4. Aba Financeiro (clica aba): obs, radio Vencimento, qtd parcelas,
     dias entre venc., data 1º venc., Gerar parcelas.
  5. Aba Contabilização (clica aba): linha1 (troca filial no DAE +
     valor) e linha2 (troca conta débito/CR no DAE + valor); no
     modo simples OTIMO, replica valor em N linhas.
  6. Segunda verificação de duplicidade — snapshot antes do "+" +
     click + snapshot depois. Cinturão + suspensório (o TOTVS
     pode revalidar).
  7. "+" UMA vez (grava tudo).
  8. Clica "Autorizar".

Emergência: tecla END aborta o lote. Mesma pattern do rpa_totvs.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from .calibracao_orcamento import CalibracaoOrcamento
from .logger import log
from .models import NotaDespesa, StatusLancamento


VK_END = 0x23


def _capslock_off() -> None:
    try:
        import ctypes
        VK_CAPITAL = 0x14
        KEYEVENTF_KEYUP = 0x0002
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        if user32.GetKeyState(VK_CAPITAL) & 1:
            user32.keybd_event(VK_CAPITAL, 0, 0, 0)
            user32.keybd_event(VK_CAPITAL, 0, KEYEVENTF_KEYUP, 0)
    except Exception:  # noqa: BLE001
        pass


class EmergencyAbortException(RuntimeError):
    pass


def _trazer_para_frente(win) -> None:
    """Copiado do rpa_totvs — mesma pattern anti-AV (SetForegroundWindow limpo)."""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        hwnd = getattr(win, "_hWnd", None)
        if not hwnd:
            return
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
        user32.BringWindowToTop(hwnd)
        if bool(user32.SetForegroundWindow(hwnd)):
            return
        # Fallback: pisca taskbar
        fg = user32.GetForegroundWindow()
        if fg != hwnd:
            class FLASHWINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.UINT),
                    ("hwnd", wintypes.HWND),
                    ("dwFlags", wintypes.DWORD),
                    ("uCount", wintypes.UINT),
                    ("dwTimeout", wintypes.DWORD),
                ]
            fi = FLASHWINFO()
            fi.cbSize = ctypes.sizeof(FLASHWINFO)
            fi.hwnd = hwnd
            fi.dwFlags = 0xC
            fi.uCount = 3
            fi.dwTimeout = 0
            user32.FlashWindowEx(ctypes.byref(fi))
    except Exception as e:  # noqa: BLE001
        log.warning("_trazer_para_frente falhou: %s", e)


class RpaOrcamento:
    def __init__(
        self,
        settings: dict,
        calibracao: CalibracaoOrcamento,
        template: dict,
        on_progress: Optional[Callable[[NotaDespesa, str], None]] = None,
    ):
        if not calibracao.esta_completa():
            faltam = calibracao.falta_calibrar()
            raise RuntimeError(
                "Calibração do Orçamento incompleta — faltam os campos: "
                + ", ".join(faltam)
            )
        self.settings = settings
        self.calibracao = calibracao
        self.template = template
        self.on_progress = on_progress
        self._delays = settings.get("delays", {})
        self._win = None
        self._abort_event = threading.Event()
        self._hotkey_thread: Optional[threading.Thread] = None

    # ---------- conexão ----------

    def conectar(self) -> None:
        _capslock_off()
        self._start_hotkey_watcher()

        titulo = (self.calibracao.titulo_janela or "Orçamento").strip()
        import pygetwindow as gw
        timeout = int(self._delays.get("timeout_janela_s", 30))
        deadline = time.time() + timeout
        log.info("conectar(): procurando janela contendo '%s'", titulo)
        while time.time() < deadline:
            try:
                todas = gw.getAllWindows()
            except Exception as e:  # noqa: BLE001
                log.exception("getAllWindows falhou: %s", e)
                raise
            janelas = [w for w in todas if titulo.lower() in (w.title or "").lower()]
            if janelas:
                self._win = janelas[0]
                log.info("conectar(): achou '%s'", self._win.title)
                _trazer_para_frente(self._win)
                return
            time.sleep(0.5)
        raise RuntimeError(f"Janela '{titulo}' não encontrada em {timeout}s")

    def encerrar(self) -> None:
        self._abort_event.set()

    # ---------- emergência ----------

    def _start_hotkey_watcher(self) -> None:
        if self._hotkey_thread and self._hotkey_thread.is_alive():
            return

        def watcher() -> None:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                user32.GetAsyncKeyState.restype = ctypes.c_short
                user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
            except Exception:  # noqa: BLE001
                return
            confirmacoes = 0
            while not self._abort_event.is_set():
                try:
                    estado = user32.GetAsyncKeyState(VK_END)
                    if estado & 0x8000:
                        confirmacoes += 1
                        if confirmacoes >= 2:
                            log.warning("END pressionada — abortando lote Orçamento")
                            self._abort_event.set()
                            return
                    else:
                        confirmacoes = 0
                except Exception:  # noqa: BLE001
                    return
                time.sleep(0.05)

        self._hotkey_thread = threading.Thread(target=watcher, daemon=True)
        self._hotkey_thread.start()

    def _check_abort(self) -> None:
        if self._abort_event.is_set():
            raise EmergencyAbortException("Cancelado pela tecla END")

    # ---------- helpers ----------

    def _pos_abs(self, campo: str) -> tuple[int, int]:
        ox, oy = self.calibracao.campos[campo]
        if self._win is None:
            return int(ox), int(oy)
        return int(self._win.left + ox), int(self._win.top + oy)

    def _sleep(self, chave: str, default_ms: int = 400) -> None:
        ms = int(self._delays.get(chave, default_ms))
        time.sleep(ms / 1000.0)

    def _clicar(self, campo: str) -> None:
        import pyautogui
        x, y = self._pos_abs(campo)
        pyautogui.click(x, y)
        self._sleep("apos_click_ms")

    def _preencher(self, campo: str, valor: str) -> None:
        self._check_abort()
        valor_up = valor.upper() if isinstance(valor, str) else str(valor)
        import pyautogui
        from .keyboard_utils import digitar_texto
        self._clicar(campo)
        pyautogui.press("backspace", presses=12, interval=0.002)
        pyautogui.press("delete", presses=12, interval=0.002)
        self._sleep("apos_selectall_ms")
        _capslock_off()
        intervalo = float(self._delays.get("intervalo_digitacao_s", 0.003))
        # digitar_texto usa typewrite pra ASCII puro e clipboard+Ctrl+V
        # pra strings com acentos (build-105). Antes o typewrite ignorava
        # caracteres não-ASCII silenciosamente — "ELÉTRICA" virava
        # "ELTRICA" no TOTVS.
        digitar_texto(valor_up, intervalo_ascii=intervalo)
        self._sleep("entre_campos_ms")

    def _digitar_multilinha(self, campo: str, texto: str) -> None:
        """Preenche uma observação que pode ter \\n. Cada linha vai
        separada por Enter — `typewrite` (e o clipboard) não interpretam
        \\n como Enter dependendo do layout."""
        self._check_abort()
        import pyautogui
        from .keyboard_utils import digitar_texto
        self._clicar(campo)
        pyautogui.press("backspace", presses=30, interval=0.002)
        pyautogui.press("delete", presses=30, interval=0.002)
        self._sleep("apos_selectall_ms")
        _capslock_off()
        intervalo = float(self._delays.get("intervalo_digitacao_s", 0.003))
        linhas = str(texto).upper().split("\n")
        for i, linha in enumerate(linhas):
            if i > 0:
                pyautogui.press("enter")
                time.sleep(0.05)
            digitar_texto(linha, intervalo_ascii=intervalo)
        self._sleep("entre_campos_ms")

    def _marcar_checkbox_se_necessario(self, campo: str, marcar: bool) -> None:
        """Clica no checkbox uma vez. Confiamos no template: se `marcar_icms`
        é True, o usuário validou visualmente na primeira execução."""
        if not marcar:
            return
        self._check_abort()
        import pyautogui
        x, y = self._pos_abs(campo)
        pyautogui.click(x, y)
        self._sleep("apos_click_ms")

    # ---------- detecção popup duplicidade ----------

    def _snapshot_titulos(self) -> set[str]:
        import pygetwindow as gw
        try:
            return {(w.title or "") for w in gw.getAllWindows()}
        except Exception:  # noqa: BLE001
            return set()

    def _achar_popup_novo(self, titulos_antes: set[str], palavras: tuple[str, ...]):
        import pygetwindow as gw
        try:
            for w in gw.getAllWindows():
                titulo = (w.title or "").strip()
                if not titulo or titulo in titulos_antes:
                    continue
                t = titulo.lower()
                if any(k in t for k in palavras):
                    log.info("Popup NOVO detectado: %r", titulo)
                    return w
        except Exception:  # noqa: BLE001
            pass
        return None

    def _fechar_popup(self, campo_botao: Optional[str], win_popup) -> None:
        """Fecha o popup clicando no botão calibrado ou, na falta, no centro-inferior
        da janela do popup, com fallback pra Enter/Space."""
        import pyautogui
        if campo_botao and campo_botao in self.calibracao.campos:
            x, y = self._pos_abs(campo_botao)
            pyautogui.moveTo(x, y, duration=0.05)
            pyautogui.click(x, y)
            time.sleep(0.4)
            return
        if win_popup is not None:
            try:
                win_popup.activate()
                time.sleep(0.15)
            except Exception:  # noqa: BLE001
                pass
            cx = int(win_popup.left + win_popup.width / 2)
            cy = int(win_popup.top + win_popup.height - 30)
            pyautogui.moveTo(cx, cy, duration=0.05)
            pyautogui.click(cx, cy)
            time.sleep(0.4)
        pyautogui.press("enter")
        time.sleep(0.2)

    # ---------- fluxo por nota ----------

    def lancar(self, nota: NotaDespesa) -> None:
        nota.status = StatusLancamento.EM_ANDAMENTO
        self._notificar(nota, "Iniciando")
        self._check_abort()

        try:
            if self._win is not None:
                _trazer_para_frente(self._win)

            # 1) Cabeçalho + Nota Fiscal → check imediato de duplicidade.
            #    TOTVS mostra popup Aviso NO ONBLUR do campo Nota Fiscal,
            #    antes mesmo de a gente clicar "+". Se ignorarmos aqui, o
            #    resto do preenchimento cai por cima do popup (bug reportado).
            if self._checar_duplicidade_apos_nota_fiscal(nota):
                return  # nota ficou IGNORADA

            # 2) Sem duplicidade → completa aba Nota (datas, obs, valor, ICMS).
            self._completar_aba_nota(nota)

            # 3) Abas Financeiro + Contabilização.
            self._preencher_aba_financeiro(nota)
            self._preencher_aba_contabilizacao(nota)

            # 4) Segunda verificação (cinturão + suspensório) — snapshot ANTES
            #    do "+" pra detectar popup que apareça depois.
            self._notificar(nota, "Gravando (+ único, final)")
            titulos_antes = self._snapshot_titulos()
            self._clicar("btn_novo_mais")
            self._sleep("apos_gerar_parcelas_ms", 1500)

            popup = self._achar_popup_novo(titulos_antes, ("aviso", "atenção", "atencao"))
            if popup is not None:
                if self._resolver_duplicidade(popup, titulos_antes, nota):
                    return

            # 5) Sem duplicidade → gravou com sucesso. Agora Autorizar.
            self._sleep("apos_confirmar_ms", 3000)
            self._notificar(nota, "Autorizando")
            self._clicar("btn_autorizar")
            self._sleep("apos_confirmar_ms", 2000)

            nota.status = StatusLancamento.SUCESSO
            self._notificar(nota, "Sucesso")

        except EmergencyAbortException:
            raise
        except Exception as e:  # noqa: BLE001
            nota.status = StatusLancamento.FALHA
            nota.erro = str(e)
            self._notificar(nota, f"Falha: {e}")
            log.exception("Falha lançando nota %s (pág %d)", nota.numero, nota.pagina)
            raise

    def _tratar_duplicidade(self, popup_aviso, titulos_antes: set[str]) -> None:
        """Fluxo do template 'pular_ja_lancada':
        1. Fecha popup Aviso (OK).
        2. Aperta F2 (borracha do TOTVS = limpar tela).
        3. Aparece popup Atenção — Sim pra confirmar limpar.
        4. Tela limpa e pronta pra próxima nota.
        """
        import pyautogui
        log.info("Duplicidade — fechando popup 'Aviso'")
        # Build-97: tenta detectar OK do popup via visão (template matching
        # do texto 'Aviso') pra clicar exatamente no botão em runtime, sem
        # depender de calibração salva. Fallback pra offset calibrado.
        self._clicar_popup_via_visao("aviso", "popup_dupl_ok", popup_aviso)
        time.sleep(0.3)

        # F2 — borracha (limpa tela)
        self._check_abort()
        titulos_antes_f2 = self._snapshot_titulos()
        pyautogui.press("f2")
        self._sleep("apos_gerar_parcelas_ms", 1000)

        # Popup Atenção — confirma Sim
        popup_atencao = self._achar_popup_novo(titulos_antes_f2, ("atenção", "atencao", "aviso"))
        if popup_atencao is not None:
            log.info("Popup 'Atenção' após F2 — Sim")
            self._clicar_popup_via_visao("atencao", "popup_atencao_sim", popup_atencao)
            time.sleep(0.3)
        else:
            log.warning("Popup 'Atenção' esperado após F2 não apareceu — seguindo")

    def _clicar_popup_via_visao(self, tipo: str, campo_calib: str, win_popup) -> None:
        """Prioriza calibração manual se o campo estiver calibrado. Só usa
        visão como fallback (build-100 — respeita o operador). Se a
        calibração NÃO tem esse campo, tenta detectar via template
        matching do título do popup."""
        # 1) Calibração manual do campo — vem primeiro. Se o operador
        #    calibrou o botão do popup, é aquilo.
        if campo_calib in self.calibracao.campos:
            log.info("Popup %s: usando calibração manual (%s)", tipo, campo_calib)
            self._fechar_popup(campo_calib, win_popup)
            return

        # 2) Sem calibração manual → visão automática.
        titulo = self.calibracao.titulo_janela or "Orçamento"
        try:
            from .visao_orcamento import resolver_popup_aviso, resolver_popup_atencao
            r = resolver_popup_aviso(titulo) if tipo == "aviso" else resolver_popup_atencao(titulo)
            if r is not None and campo_calib in r.campos:
                import pyautogui
                x, y = r.campos[campo_calib]
                log.info("Popup %s: visão OK conf=%.0f%% — clique em (%d,%d)",
                         tipo, r.confianca * 100, x, y)
                pyautogui.moveTo(x, y, duration=0.05)
                pyautogui.click(x, y)
                time.sleep(0.3)
                return
        except Exception as e:  # noqa: BLE001
            log.warning("Visão do popup '%s' falhou: %s — fallback", tipo, e)
        # 3) Último recurso: fechar via janela ativa + Enter.
        self._fechar_popup(campo_calib, win_popup)

    def _checar_duplicidade_apos_nota_fiscal(self, nota: NotaDespesa) -> bool:
        """Preenche cabeçalho da aba Nota (empresa, nat.despesa, pessoa) +
        campo Nota Fiscal e VERIFICA se o TOTVS já sinalizou duplicidade.

        Retorna True se a nota virou IGNORADA (duplicidade tratada) — o
        chamador deve parar o fluxo. False se pode seguir preenchendo.
        """
        an = self.template.get("aba_nota") or {}

        # Empresa: fixa OU por CNPJ do documento (DAE) OU por CNPJ do
        # tomador (Pluxee — cada nota é pra uma filial diferente).
        if an.get("empresa_por_cnpj_tomador") and nota.filial_emissao_codigo is not None:
            empresa = str(nota.filial_emissao_codigo)
        elif an.get("empresa_por_cnpj") and nota.filial_codigo is not None:
            empresa = str(nota.filial_codigo)
        else:
            empresa = str(an.get("empresa_codigo", ""))
        self._preencher("empresa", empresa)

        self._preencher("nat_despesa", str(an.get("nat_despesa_codigo", "")))
        self._sleep("apos_especie_ms", 600)
        self._preencher("pessoa", str(an.get("pessoa_codigo", "")))
        self._sleep("apos_pessoa_ms", 800)

        # Snapshot ANTES de digitar a NF — o popup Aviso costuma nascer
        # aqui no OnLeaveFocus do campo (o TOTVS valida unicidade).
        titulos_antes = self._snapshot_titulos()

        self._preencher("nota_fiscal", str(nota.numero))
        # Força OnLeaveFocus: Tab dispara a validação do TOTVS mesmo se o
        # próximo campo não for o Série (o robô já vai clicar em outro
        # campo depois, mas Tab garante que a validação rode ANTES de
        # tentarmos qualquer outro click).
        import pyautogui
        pyautogui.press("tab")
        self._sleep("apos_selectall_ms", 1000)

        # Deu popup?
        popup = self._achar_popup_novo(titulos_antes, ("aviso", "atenção", "atencao"))
        if popup is not None:
            log.info(
                "Popup Aviso detectado LOGO após digitar Nota Fiscal — duplicidade cedo"
            )
            return self._resolver_duplicidade(popup, titulos_antes, nota)
        return False

    def _completar_aba_nota(self, nota: NotaDespesa) -> None:
        """Preenche o restante da aba Nota (assumindo cabeçalho + NF já OK,
        sem duplicidade)."""
        an = self.template.get("aba_nota") or {}
        regras = self.template.get("regras") or {}

        # Data emissão: por padrão = data_emissao da nota; pra DAE,
        # `data_emissao_regra: data_lancto` porque não há emissão no DAE.
        emi_regra = regras.get("data_emissao_regra")
        if emi_regra == "data_lancto":
            self._preencher("data_emissao", nota.data_lancto.strftime("%d/%m/%Y"))
        elif nota.data_emissao is not None:
            self._preencher("data_emissao", nota.data_emissao.strftime("%d/%m/%Y"))
        self._preencher("data_lancto",   nota.data_lancto.strftime("%d/%m/%Y"))
        self._preencher("st_doc",        str(an.get("st_doc", "Regular")))
        self._preencher("modelo",        str(an.get("modelo", "")))
        self._digitar_multilinha("observacao_fiscal", self._resolver_texto(an, nota, "observacao_fiscal"))
        valor_txt = f"{nota.valor:.2f}".replace(".", ",")
        self._preencher("valor_total_nf", valor_txt)
        self._marcar_checkbox_se_necessario("check_icms", bool(an.get("marcar_icms", False)))

    def _resolver_duplicidade(self, popup, titulos_antes: set, nota: NotaDespesa) -> bool:
        """Dispatcher da regra `duplicidade_regra` do template. Retorna
        True se tratou (nota virou IGNORADA), False se não é caso da
        regra (deixa o caller decidir). Levanta RuntimeError se a regra
        for desconhecida — nunca inventamos número de NF."""
        regra = (self.template.get("regras") or {}).get("duplicidade_regra", "pular_ja_lancada")
        if regra == "pular_ja_lancada":
            self._tratar_duplicidade(popup, titulos_antes)
            nota.status = StatusLancamento.IGNORADO
            nota.motivo_ignorado = "já lançada (nota fiscal duplicada)"
            self._notificar(nota, "IGNORADA — já lançada")
            return True
        raise RuntimeError(
            f"Duplicidade detectada e regra '{regra}' não implementada. "
            "Nunca inventamos número de nota fiscal — cancele e verifique manual."
        )

    # Compat: alguém pode ter chamado `_preencher_aba_nota` — mantemos o
    # nome apontando pra função que preserva o comportamento antigo
    # (sem check cedo), pra testes/scripts. Fluxo real usa
    # _checar_duplicidade_apos_nota_fiscal + _completar_aba_nota.
    def _preencher_aba_nota(self, nota: NotaDespesa) -> None:
        an = self.template.get("aba_nota") or {}
        if an.get("empresa_por_cnpj") and nota.filial_codigo is not None:
            empresa = str(nota.filial_codigo)
        else:
            empresa = str(an.get("empresa_codigo", ""))
        self._preencher("empresa", empresa)
        self._preencher("nat_despesa", str(an.get("nat_despesa_codigo", "")))
        self._sleep("apos_especie_ms", 600)
        self._preencher("pessoa", str(an.get("pessoa_codigo", "")))
        self._sleep("apos_pessoa_ms", 800)
        self._preencher("nota_fiscal", str(nota.numero))
        self._completar_aba_nota(nota)

    def _preencher_aba_financeiro(self, nota: NotaDespesa) -> None:
        af = self.template.get("aba_financeiro") or {}
        self._clicar("aba_financeiro")
        self._sleep("apos_click_ms", 700)
        self._digitar_multilinha("observacao_financeira", self._resolver_texto(af, nota, "observacao_financeira"))
        # Radio Vencimento (modo)
        self._clicar("radio_vencimento")
        self._preencher("qtd_parcelas", str(af.get("quantidade_parcelas", 1)))
        self._preencher("dias_entre_venc", str(af.get("dias_entre_vencimentos", 1)))
        # Vencimento: default = data_lancto; DAE usa vencimento_dae.
        venc_regra = af.get("vencimento_igual_a") or "data_lancto"
        if venc_regra == "vencimento_dae" and nota.vencimento_dae is not None:
            venc = nota.vencimento_dae
        else:
            venc = nota.data_lancto
        self._preencher("data_vencimento", venc.strftime("%d/%m/%Y"))
        self._clicar("btn_gerar")
        self._sleep("apos_gerar_parcelas_ms", 1000)

    def _resolver_texto(self, secao: dict, nota: NotaDespesa, chave_base: str) -> str:
        """Resolve texto do template. Ordem de precedência:

        1. `<chave>_template`: string com placeholders `{filial_caneta_nome}`,
           `{filial_emissao_nome}`, `{filial_nome}` — substituídos pelos
           dados da nota (Pluxee, build-107).
        2. `<chave>_por_tipo`: dict tipo→texto (DAE regime_normal /
           adic_fundo_pobreza).
        3. `<chave>`: string literal fixa (OTIMO).
        """
        template_str = secao.get(f"{chave_base}_template")
        if isinstance(template_str, str):
            return self._formatar_template(template_str, nota)

        por_tipo = secao.get(f"{chave_base}_por_tipo") or secao.get("observacao_por_tipo")
        if isinstance(por_tipo, dict) and nota.tipo_dae:
            return str(por_tipo.get(nota.tipo_dae, ""))

        return str(secao.get(chave_base, ""))

    def _formatar_template(self, txt: str, nota: NotaDespesa) -> str:
        """Substitui placeholders com dados da nota. Usa .format_map com
        defaultdict pra placeholders desconhecidos não quebrarem tudo."""
        class _Falta(dict):
            def __missing__(self, key):
                return "?"
        campos = _Falta(
            filial_nome=nota.filial_nome or "",
            filial_emissao_nome=nota.filial_emissao_nome or "",
            filial_caneta_nome=nota.filial_caneta_nome or nota.anotacao_caneta or "?",
            numero=nota.numero or "",
        )
        try:
            return txt.format_map(campos)
        except (KeyError, IndexError, ValueError) as e:
            log.warning("Template inválido %r: %s", txt, e)
            return txt

    def _preencher_aba_contabilizacao(self, nota: NotaDespesa) -> None:
        ac = self.template.get("aba_contabilizacao") or {}
        self._clicar("aba_contabilizacao")
        self._sleep("apos_click_ms", 700)
        valor_txt = f"{nota.valor:.2f}".replace(".", ",")

        # Modo simples (OTIMO): replicar_valor_nas_linhas: N
        if "replicar_valor_nas_linhas" in ac:
            n_linhas = int(ac.get("replicar_valor_nas_linhas", 2))
            if n_linhas >= 1:
                self._preencher("contab_linha1_valor", valor_txt)
            if n_linhas >= 2:
                self._preencher("contab_linha2_valor", valor_txt)
            return

        # Modo estruturado (DAE, PLUXEE): linha1 + linha2 com regras.
        self._processar_linha_contab(ac.get("linha1") or {}, "linha1", nota, valor_txt)
        self._processar_linha_contab(ac.get("linha2") or {}, "linha2", nota, valor_txt)

    def _processar_linha_contab(
        self, cfg: dict, prefixo: str, nota: NotaDespesa, valor_txt: str,
    ) -> None:
        """Aplica a config de UMA linha da aba Contabilização. `prefixo` é
        'linha1' ou 'linha2' — usado pra achar o campo calibrado
        (contab_linha1_filial, contab_linha2_conta_debito, etc.).

        Reconhece:
        - `trocar_filial_para`: string enum. Opções:
             'filial_loja'     → nota.filial_codigo (usado pelo DAE)
             'filial_emissao'  → nota.filial_emissao_codigo (Pluxee)
             'filial_caneta'   → nota.filial_caneta_codigo (Pluxee)
          Pra compat com o build-101 aceita também
             `trocar_filial_para_da_loja: true` (= 'filial_loja').
        - `conta_debito` / `cr`: strings fixas (DAE — linha 2).
        - `preencher_valor`: bool (default True).
        """
        # Trocar filial
        alvo = cfg.get("trocar_filial_para")
        if not alvo and cfg.get("trocar_filial_para_da_loja"):
            alvo = "filial_loja"
        if alvo:
            codigo = None
            if alvo == "filial_loja":
                codigo = nota.filial_codigo
            elif alvo == "filial_emissao":
                codigo = nota.filial_emissao_codigo
            elif alvo == "filial_caneta":
                codigo = nota.filial_caneta_codigo
            if codigo is not None:
                self._preencher(f"contab_{prefixo}_filial", str(codigo))
            else:
                log.warning("Contab %s: alvo '%s' pediu troca de filial mas "
                            "nota não tem esse código resolvido — deixando "
                            "a filial padrão do TOTVS", prefixo, alvo)

        # Colunas técnicas (só linha 2 do DAE hoje)
        if cfg.get("conta_debito"):
            self._preencher(f"contab_{prefixo}_conta_debito", str(cfg["conta_debito"]))
        if cfg.get("cr"):
            self._preencher(f"contab_{prefixo}_cr", str(cfg["cr"]))

        if cfg.get("preencher_valor", True):
            self._preencher(f"contab_{prefixo}_valor", valor_txt)

    def _notificar(self, nota: NotaDespesa, msg: str) -> None:
        if self.on_progress:
            try:
                self.on_progress(nota, msg)
            except Exception:  # noqa: BLE001
                log.exception("on_progress callback falhou")


def executar_lote_orcamento(
    notas: list[NotaDespesa],
    template: dict,
    settings: dict,
    calibracao: CalibracaoOrcamento,
    on_progress: Optional[Callable[[NotaDespesa, str], None]] = None,
    parar_em_falha: bool = False,
) -> tuple[int, int, int]:
    """Retorna (sucessos, falhas, ignoradas)."""
    rpa = RpaOrcamento(settings, calibracao, template, on_progress=on_progress)
    try:
        rpa.conectar()
        sucessos = falhas = ignoradas = 0
        for nota in notas:
            try:
                rpa.lancar(nota)
                if nota.status == StatusLancamento.SUCESSO:
                    sucessos += 1
                elif nota.status == StatusLancamento.IGNORADO:
                    ignoradas += 1
            except EmergencyAbortException:
                break
            except Exception:  # noqa: BLE001
                falhas += 1
                if parar_em_falha:
                    break
        return sucessos, falhas, ignoradas
    finally:
        rpa.encerrar()
