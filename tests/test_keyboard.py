"""
Testes do keyboard_utils. Não testa a digitação real (precisaria de
janela em foco), só o discriminador ASCII/unicode — que é o que
determina qual caminho (typewrite vs clipboard) vai ser usado.

Foi bug em produção no build-105: pyautogui.typewrite ignora
silenciosamente non-ASCII, o que fazia "Elétrica" virar "eltrica".
Esse teste impede a regressão.
"""

from __future__ import annotations

from src.core.keyboard_utils import _eh_ascii_puro


def test_ascii_puro_true_para_ascii_basico():
    assert _eh_ascii_puro("ABC")
    assert _eh_ascii_puro("Teste 123 - !@#$")
    assert _eh_ascii_puro("")


def test_ascii_puro_false_para_acentos():
    # O caso que quebrou em produção.
    assert not _eh_ascii_puro("Elétrica")
    assert not _eh_ascii_puro("São Paulo")
    assert not _eh_ascii_puro("Muriaé")


def test_ascii_puro_false_para_cedilha():
    assert not _eh_ascii_puro("Multicom Atacadão")
    assert not _eh_ascii_puro("Serviço")


def test_ascii_puro_false_para_emojis():
    # Improvável no fluxo real, mas exercita o edge.
    assert not _eh_ascii_puro("teste ✅")


def test_ascii_puro_lida_com_string_muito_longa():
    # Notas de despesa às vezes têm observação de 200+ chars.
    texto_asc = "A" * 500
    texto_uni = ("A" * 499) + "é"
    assert _eh_ascii_puro(texto_asc)
    assert not _eh_ascii_puro(texto_uni)
