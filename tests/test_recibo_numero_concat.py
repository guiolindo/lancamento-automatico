"""
Testes do número concatenado ANO+Nº do recibo (build-132).

TOTVS espera o campo Nº documento como ano + número do recibo
concatenados — "2026" + "1205" → "20261205". Isso é feito no
`_converter_recibos` com os campos `ano` e `numero` extraídos
separadamente pelo Gemini.
"""

from __future__ import annotations


def _concat(ano: str, numero: str) -> str:
    """Simula a lógica do _converter_recibos (build-132). Pura: só
    strings, sem Qt."""
    ano_raw = "".join(c for c in str(ano) if c.isdigit())
    num_raw = "".join(c for c in str(numero) if c.isdigit())
    if ano_raw and num_raw:
        return f"{ano_raw}{num_raw}"
    return num_raw


def test_concatena_ano_e_numero_do_recibo():
    """Exemplos do usuário: ano 2026 + recibo 1205 → 20261205."""
    assert _concat("2026", "1205") == "20261205"
    assert _concat("2026", "405") == "2026405"
    assert _concat("2025", "1030") == "20251030"


def test_sem_ano_cai_no_numero_cru():
    """Se o Gemini não achou o 'ANO' no cabeçalho, pelo menos passa o
    número do recibo pro TOTVS — o operador vê 'XXX' e barra na
    duplicidade, ou corrige manualmente."""
    assert _concat("", "1205") == "1205"
    assert _concat(None, "405") == "405"  # type: ignore[arg-type]


def test_sem_numero_devolve_vazio():
    """Falta recibo: devolve string vazia. O filtro de 'pendentes' do
    _executar_lote exige `n.numero` not empty, então essa linha nunca
    entra no RPA — operador precisa editar antes."""
    assert _concat("2026", "") == ""
    assert _concat("", "") == ""


def test_ignora_pontuacao_nos_dois_campos():
    """Se o Gemini devolver "ANO 2026" ou "N° 1205" (com símbolos),
    só os dígitos sobrevivem."""
    assert _concat("ANO 2026", "Nº 1205") == "20261205"
    assert _concat("2026.", " 1.205 ") == "20261205"


def test_ano_grande_e_numero_grande():
    """Edge: nada quebra a concatenação, nem com números longos."""
    assert _concat("2026", "99999") == "202699999"
