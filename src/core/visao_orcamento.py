"""
Auto-detecção das posições dos campos na tela 'Notas Fiscais de Despesas'
do TOTVS Orçamento (build-97).

Mesma pattern do `visao_totvs.py` (Operador Financeiro), adaptada pros
23 campos + 3 abas do módulo Orçamento:

1. Achamos a janela 'Orçamento…' via pygetwindow e tiramos screenshot só
   dessa região.
2. Template matching (OpenCV) do texto 'Notas Fiscais de Despesas' que
   fica no cabeçalho da subjanela — é o âncora principal.
3. Layout do TOTVS é fixo → todos os campos das 3 abas têm offset conhecido
   em relação a esse âncora. Aplicamos offsets e devolvemos coords absolutas.
4. Testamos múltiplas escalas (0.85 até 1.22) pra tolerar DPI/monitor
   diferente sem forçar recalibração manual.

Para os popups usamos dois âncoras próprios: 'Aviso' (duplicidade) e
'Atenção!' (pós-F2 / descartar alterações).

Coordenadas de referência foram medidas em `aba_nota_branco.png` (aba
Nota vazia; captura de tela real do TOTVS em prod). O canto superior
esquerdo do texto 'Notas Fiscais de Despesas' está em (20, 62) na
imagem original — todos os offsets abaixo são relativos a esse ponto.

Se qualquer âncora não bater com confiança ≥ 0.70 → devolvemos None e o
fluxo cai na calibração manual (fallback) — mesmo comportamento do
visao_totvs.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Offsets (dx, dy) do TOP-LEFT de cada campo/botão em relação ao TOP-LEFT
# do âncora 'Notas Fiscais de Despesas' (anchor_header.png).
# Todas as coords foram medidas na captura `aba_nota_branco.png` (1024x820,
# janela TOTVS a partir de x=0) com o âncora em (20, 62).
CAMPOS_OFFSET_ANCHOR: dict[str, tuple[int, int]] = {
    # ---- Toolbar (topo, y=+43) ----
    "btn_novo_mais":         (67, 43),
    "btn_autorizar":         (555, 43),
    # ---- Abas (linha de abas, y=+79) ----
    "aba_financeiro":        (111, 79),
    "aba_contabilizacao":    (182, 79),
    # ---- Aba Nota (padrão) ----
    "empresa":               (330, 119),
    "nat_despesa":           (90, 141),
    "pessoa":                (120, 162),
    "nota_fiscal":           (120, 183),
    "st_doc":                (480, 183),
    "modelo":                (90, 205),
    "data_emissao":          (700, 128),
    "data_lancto":           (700, 142),
    "observacao_fiscal":     (860, 148),
    "valor_total_nf":        (130, 329),
    "check_icms":            (30, 408),
    # ---- Aba Financeiro (posições válidas quando ela está ativa) ----
    "observacao_financeira": (620, 253),
    "radio_vencimento":      (340, 284),
    "qtd_parcelas":          (527, 284),
    "dias_entre_venc":       (680, 284),
    "data_vencimento":       (830, 284),
    "btn_gerar":             (280, 284),
    # ---- Aba Contabilização (posições válidas quando ela está ativa) ----
    # Colunas medidas em aba_contabilizacao_branco.png: Filial ~x=220,
    # Conta Débito ~x=270, CR (após Débito/COD/CR/GC) ~x=430,
    # Valor ~x=910. Linhas: 1 @ y=283, 2 @ y=302 (~19px de altura).
    "contab_linha1_filial":        (200, 221),
    "contab_linha1_valor":         (890, 221),
    "contab_linha2_conta_debito":  (250, 240),
    "contab_linha2_cr":            (410, 240),
    "contab_linha2_valor":         (890, 240),
}

# Popup Aviso (duplicidade) — offsets do âncora "Aviso".
POPUP_AVISO_OFFSET: dict[str, tuple[int, int]] = {
    "popup_dupl_ok": (205, 127),
}

# Popup Atenção (pós-F2 confirmar descartar) — offsets do âncora "Atenção!".
POPUP_ATENCAO_OFFSET: dict[str, tuple[int, int]] = {
    "popup_atencao_sim": (120, 135),
}

CONFIANCA_MINIMA = 0.70
ESCALAS = (0.85, 0.92, 1.00, 1.08, 1.15, 1.22)


@dataclass
class ResultadoVisaoOrc:
    campos: dict[str, tuple[int, int]]     # coords absolutas de tela
    confianca_header: float
    origem_header: tuple[int, int]         # top-left do âncora na tela


@dataclass
class ResultadoVisaoPopupOrc:
    campos: dict[str, tuple[int, int]]     # popup_dupl_ok e/ou popup_atencao_sim
    confianca: float


def _assets_dir() -> Path:
    aqui = Path(__file__).resolve()
    candidatos = [aqui.parent.parent / "assets"]
    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidatos.extend([exe_dir / "src" / "assets", exe_dir / "assets"])
    except Exception:  # noqa: BLE001
        pass
    for c in candidatos:
        if (c / "totvs_reference" / "orcamento").exists():
            return c
    return aqui.parent.parent / "assets"


def _ref_path(nome: str) -> Path:
    return _assets_dir() / "totvs_reference" / "orcamento" / nome


def _capturar_janela(titulo: str):
    try:
        import pygetwindow as gw
        import numpy as np
        import mss
    except Exception:  # noqa: BLE001
        return None

    janelas = [w for w in gw.getAllWindows() if titulo.lower() in (w.title or "").lower()]
    if not janelas:
        return None
    win = janelas[0]
    if win.width <= 0 or win.height <= 0:
        return None

    with mss.mss() as sct:
        monitor = {
            "left": max(0, int(win.left)),
            "top": max(0, int(win.top)),
            "width": int(win.width),
            "height": int(win.height),
        }
        raw = sct.grab(monitor)
        arr = np.array(raw, dtype=np.uint8)[:, :, :3]
    return arr, monitor["left"], monitor["top"]


def _match_multi_escala(imagem_bgr, template_bgr):
    import cv2
    melhor = (0.0, 0, 0, 1.0)
    for escala in ESCALAS:
        h, w = template_bgr.shape[:2]
        novo_w = max(4, int(w * escala))
        novo_h = max(4, int(h * escala))
        if imagem_bgr.shape[0] < novo_h or imagem_bgr.shape[1] < novo_w:
            continue
        tpl = cv2.resize(template_bgr, (novo_w, novo_h), interpolation=cv2.INTER_AREA)
        try:
            res = cv2.matchTemplate(imagem_bgr, tpl, cv2.TM_CCOEFF_NORMED)
        except cv2.error:
            continue
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val > melhor[0]:
            melhor = (float(max_val), int(max_loc[0]), int(max_loc[1]), escala)
    return melhor


def resolver_header(titulo_janela: str = "Orçamento") -> Optional[ResultadoVisaoOrc]:
    """Detecta o âncora 'Notas Fiscais de Despesas' e devolve coords
    absolutas dos 23 campos. None se falhar."""
    try:
        import cv2
    except Exception:  # noqa: BLE001
        return None

    cap = _capturar_janela(titulo_janela)
    if cap is None:
        return None
    imagem, left, top = cap

    tpl_path = _ref_path("anchor_header.png")
    if not tpl_path.exists():
        return None
    template = cv2.imread(str(tpl_path), cv2.IMREAD_COLOR)
    if template is None:
        return None

    conf, ax, ay, escala = _match_multi_escala(imagem, template)
    if conf < CONFIANCA_MINIMA:
        return None

    campos: dict[str, tuple[int, int]] = {}
    for chave, (dx, dy) in CAMPOS_OFFSET_ANCHOR.items():
        campos[chave] = (
            left + ax + int(dx * escala),
            top + ay + int(dy * escala),
        )

    return ResultadoVisaoOrc(
        campos=campos,
        confianca_header=conf,
        origem_header=(left + ax, top + ay),
    )


def _resolver_popup(
    titulo_janela: str,
    anchor_file: str,
    offsets: dict[str, tuple[int, int]],
) -> Optional[ResultadoVisaoPopupOrc]:
    try:
        import cv2
    except Exception:  # noqa: BLE001
        return None

    cap = _capturar_janela(titulo_janela)
    if cap is None:
        return None
    imagem, left, top = cap

    tpl_path = _ref_path(anchor_file)
    if not tpl_path.exists():
        return None
    template = cv2.imread(str(tpl_path), cv2.IMREAD_COLOR)
    if template is None:
        return None

    conf, ax, ay, escala = _match_multi_escala(imagem, template)
    if conf < CONFIANCA_MINIMA:
        return None

    campos = {
        k: (left + ax + int(dx * escala), top + ay + int(dy * escala))
        for k, (dx, dy) in offsets.items()
    }
    return ResultadoVisaoPopupOrc(campos=campos, confianca=conf)


def resolver_popup_aviso(titulo_janela: str = "Orçamento") -> Optional[ResultadoVisaoPopupOrc]:
    return _resolver_popup(titulo_janela, "anchor_popup_aviso.png", POPUP_AVISO_OFFSET)


def resolver_popup_atencao(titulo_janela: str = "Orçamento") -> Optional[ResultadoVisaoPopupOrc]:
    return _resolver_popup(titulo_janela, "anchor_popup_atencao.png", POPUP_ATENCAO_OFFSET)


def preencher_calibracao_automatica(calibracao) -> tuple[bool, str]:
    """Preenche `calibracao.campos` (relativos à janela) via visão.
    Devolve (sucesso, mensagem). Pattern idêntica ao visao_totvs."""
    try:
        import pygetwindow as gw
    except Exception as e:  # noqa: BLE001
        return False, f"pygetwindow indisponível: {e}"

    titulo = calibracao.titulo_janela or "Orçamento"
    r = resolver_header(titulo)
    if r is None:
        return False, "Não foi possível reconhecer a tela 'Notas Fiscais de Despesas'."

    janelas = [w for w in gw.getAllWindows() if titulo.lower() in (w.title or "").lower()]
    if not janelas:
        return False, "Janela do TOTVS sumiu entre a detecção e a leitura."
    win = janelas[0]

    for chave, (ax, ay) in r.campos.items():
        calibracao.campos[chave] = (int(ax - win.left), int(ay - win.top))

    # Popups são detectados oportunisticamente se aparecerem. O RPA também
    # tenta clicar via calibração manual se algum campo do popup não vier
    # aqui — na prática, o popup só existe DURANTE a execução, então a
    # detecção principal roda de novo na hora, dentro do RpaOrcamento.

    from .logger import log
    log.info("=" * 60)
    log.info("VISÃO ORÇAMENTO: janela '%s' em (%d,%d) %dx%d",
             win.title, win.left, win.top, win.width, win.height)
    log.info("VISÃO ORÇAMENTO: âncora em (%d,%d), confiança %.0f%%",
             r.origem_header[0], r.origem_header[1], r.confianca_header * 100)
    for k, (rx, ry) in sorted(calibracao.campos.items()):
        log.info("VISÃO ORÇAMENTO: %-20s offset (%4d,%4d) -> tela (%4d,%4d)",
                 k, rx, ry, win.left + rx, win.top + ry)
    log.info("=" * 60)

    return True, f"Visão OK — confiança {r.confianca_header:.0%}, {len(r.campos)} campos."
