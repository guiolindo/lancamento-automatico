"""
Auto-detecção das posições dos campos na tela 'Inclusão de Títulos' do TOTVS.

Elimina a calibração manual. A ideia:

1. Achamos a janela 'Operador Financeiro' (pygetwindow) e tiramos screenshot
   apenas dessa região.
2. Fazemos template matching (OpenCV) do texto 'Inclusão de Títulos' que
   fica no cabeçalho da subjanela — é o nosso ÂNCORA.
3. Como o layout do TOTVS é fixo, todos os campos têm offset conhecido
   em relação a esse âncora — aplicamos os offsets e devolvemos as
   coordenadas absolutas de clique.
4. Testamos em múltiplas escalas (0.85 até 1.20) pra tolerar variação de
   DPI/monitor sem exigir recalibração.

Para o popup de duplicidade usamos o mesmo esquema com o texto 'Atenção'
como âncora.

Se qualquer âncora não bater com confiança ≥ 0.7, devolvemos None e o
fluxo cai na calibração manual antiga (fallback).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Offsets (dx, dy) do TOP-LEFT de cada campo/botão em relação ao TOP-LEFT
# do âncora 'Inclusão de Títulos' (imagem anchor_child.png).
# Valores medidos a partir de src/assets/totvs_reference/child_ref.png,
# onde o âncora está em (25, 5).
CAMPOS_OFFSET_ANCHOR_CHILD: dict[str, tuple[int, int]] = {
    "btn_confirmar":      (35, 40),
    "empresa":            (80, 66),
    "especie":            (440, 66),
    "pessoa":             (80, 88),
    "observacao":         (175, 215),
    "nro_documento":      (100, 251),
    "dt_emissao":         (395, 251),
    "valor":              (605, 251),
    "dt_contabilizacao":  (125, 275),
    "vencimento":         (305, 298),
    "btn_gerar_parcelas": (550, 370),
}

# Popup 'Atenção' — offsets do TOP-LEFT do âncora 'Atenção'.
POPUP_OFFSET_ANCHOR: dict[str, tuple[int, int]] = {
    "popup_indicador": (55, 67),
    "popup_ok":        (235, 115),
}

CONFIANCA_MINIMA = 0.70
ESCALAS = (0.85, 0.92, 1.00, 1.08, 1.15, 1.22)


@dataclass
class ResultadoVisao:
    campos: dict[str, tuple[int, int]]   # coords absolutas na tela (screen coords)
    confianca_child: float
    origem_child: tuple[int, int]        # top-left do âncora child na tela


@dataclass
class ResultadoVisaoPopup:
    popup_indicador: tuple[int, int]
    popup_ok: tuple[int, int]
    confianca: float


def _assets_dir() -> Path:
    """Localiza a pasta src/assets no dev e no exe compilado."""
    aqui = Path(__file__).resolve()
    candidatos = [
        aqui.parent.parent / "assets",  # dev: src/assets
    ]
    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidatos.extend([
            exe_dir / "src" / "assets",
            exe_dir / "assets",
        ])
    except Exception:
        pass
    for c in candidatos:
        if (c / "totvs_reference").exists():
            return c
    return aqui.parent.parent / "assets"


def _ref_path(nome: str) -> Path:
    return _assets_dir() / "totvs_reference" / nome


def _capturar_janela(titulo: str) -> Optional[tuple["numpy.ndarray", int, int]]:  # type: ignore  # noqa: F821
    """Screenshot da janela; devolve (BGR ndarray, left, top) ou None."""
    try:
        import pygetwindow as gw
        import numpy as np
        import mss
    except Exception:
        return None

    janelas = [w for w in gw.getAllWindows() if titulo.lower() in (w.title or "").lower()]
    if not janelas:
        return None
    win = janelas[0]
    # Alguns backends devolvem width/height <=0 quando minimizada.
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
        # mss devolve BGRA — convertemos pra BGR (formato do OpenCV).
        arr = np.array(raw, dtype=np.uint8)[:, :, :3]  # descarta alpha
    return arr, monitor["left"], monitor["top"]


def _match_multi_escala(imagem_bgr, template_bgr) -> tuple[float, int, int, float]:
    """Devolve (confianca, x, y, escala) do melhor match multi-escala."""
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


def resolver_child(titulo_janela: str = "Operador Financeiro") -> Optional[ResultadoVisao]:
    """Detecta a subjanela 'Inclusão de Títulos' e devolve coords absolutas
    de todos os campos. None se falhar."""
    try:
        import cv2
    except Exception:
        return None

    cap = _capturar_janela(titulo_janela)
    if cap is None:
        return None
    imagem, left, top = cap

    tpl_path = _ref_path("anchor_child.png")
    if not tpl_path.exists():
        return None
    template = cv2.imread(str(tpl_path), cv2.IMREAD_COLOR)
    if template is None:
        return None

    conf, ax, ay, escala = _match_multi_escala(imagem, template)
    if conf < CONFIANCA_MINIMA:
        return None

    # Corrigimos os offsets de acordo com a escala detectada.
    campos_absolutos: dict[str, tuple[int, int]] = {}
    for chave, (dx, dy) in CAMPOS_OFFSET_ANCHOR_CHILD.items():
        campos_absolutos[chave] = (
            left + ax + int(dx * escala),
            top + ay + int(dy * escala),
        )

    return ResultadoVisao(
        campos=campos_absolutos,
        confianca_child=conf,
        origem_child=(left + ax, top + ay),
    )


def resolver_popup(titulo_janela: str = "Operador Financeiro") -> Optional[ResultadoVisaoPopup]:
    """Detecta o popup 'Atenção' e devolve coords absolutas dos pontos.
    None se não achar (o popup nem sempre está aberto)."""
    try:
        import cv2
    except Exception:
        return None

    cap = _capturar_janela(titulo_janela)
    if cap is None:
        return None
    imagem, left, top = cap

    tpl_path = _ref_path("anchor_popup.png")
    if not tpl_path.exists():
        return None
    template = cv2.imread(str(tpl_path), cv2.IMREAD_COLOR)
    if template is None:
        return None

    conf, ax, ay, escala = _match_multi_escala(imagem, template)
    if conf < CONFIANCA_MINIMA:
        return None

    ind = POPUP_OFFSET_ANCHOR["popup_indicador"]
    ok = POPUP_OFFSET_ANCHOR["popup_ok"]
    return ResultadoVisaoPopup(
        popup_indicador=(left + ax + int(ind[0] * escala),
                         top + ay + int(ind[1] * escala)),
        popup_ok=(left + ax + int(ok[0] * escala),
                  top + ay + int(ok[1] * escala)),
        confianca=conf,
    )


def preencher_calibracao_automatica(calibracao) -> tuple[bool, str]:
    """Tenta preencher `calibracao.campos` via visão automática.
    Devolve (sucesso, mensagem)."""
    # Precisamos das coordenadas RELATIVAS à janela (offset window-relative)
    # porque o resto do RPA já converte para absoluto a partir do get da janela.
    # Como a visão já devolve absoluto, aqui armazenamos absoluto e o
    # rpa_totvs interpretará campos como já absolutos quando marcar
    # `usar_absoluto = True`. Alternativa: descobrir left/top de novo e
    # subtrair. Mais simples: subtrair aqui.
    try:
        import pygetwindow as gw
    except Exception as e:
        return False, f"pygetwindow indisponível: {e}"

    r = resolver_child(calibracao.titulo_janela or "Operador Financeiro")
    if r is None:
        return False, "Não foi possível reconhecer a tela 'Inclusão de Títulos'."

    janelas = [w for w in gw.getAllWindows()
               if (calibracao.titulo_janela or "Operador Financeiro").lower() in (w.title or "").lower()]
    if not janelas:
        return False, "Janela do TOTVS sumiu entre a detecção e a leitura."
    win = janelas[0]

    # Converte pra offset relativo à janela (que é o que rpa_totvs espera)
    for chave, (ax, ay) in r.campos.items():
        calibracao.campos[chave] = (int(ax - win.left), int(ay - win.top))

    # Popup: tenta detectar; se não achar, tudo bem — só será calibrado se
    # o operador provocar o erro depois.
    p = resolver_popup(calibracao.titulo_janela or "Operador Financeiro")
    if p is not None:
        calibracao.campos["popup_ok"] = (int(p.popup_ok[0] - win.left),
                                         int(p.popup_ok[1] - win.top))
        calibracao.campos["popup_indicador"] = (int(p.popup_indicador[0] - win.left),
                                                int(p.popup_indicador[1] - win.top))

    return True, f"Visão OK — confiança {r.confianca_child:.0%}, {len(r.campos)} campos."
