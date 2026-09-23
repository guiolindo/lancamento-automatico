"""
Utilitários puros de CNPJ. Nada de UI, nada de I/O. Existe pra ser
fácil de testar (não precisa Qt/pyautogui no import).
"""

from __future__ import annotations

from enum import Enum


class TomadorMatch(str, Enum):
    """Resultado da validação do CNPJ tomador de uma nota contra o
    cadastro de filiais.

    - EXATO: CNPJ bate 100% com uma filial → OK, lança na filial resolvida.
    - RAIZ_GRUPO: os 8 primeiros dígitos (CNPJ raiz) batem com alguma
      filial do grupo, mas o CNPJ completo (com sufixo /XXXX) não —
      provavelmente é uma filial nova, ainda não cadastrada em
      `cnpjs_filiais.json`. Bloqueia; operador precisa cadastrar antes
      de reprocessar.
    - OUTRA_EMPRESA: nem a raiz bate. Nota veio parar aqui por engano
      (endereçamento errado, email misturado). Bloqueia.
    - AUSENTE: o CNPJ tomador nem veio da extração (Gemini não achou).
      Trata como OUTRA_EMPRESA — não tem como validar, melhor barrar.
    """
    EXATO = "EXATO"
    RAIZ_GRUPO = "RAIZ_GRUPO"
    OUTRA_EMPRESA = "OUTRA_EMPRESA"
    AUSENTE = "AUSENTE"


def raiz_cnpj(cnpj: str) -> str:
    """Devolve os 8 primeiros dígitos de um CNPJ, filtrando pontuação.
    String vazia se o input não tiver 8+ dígitos."""
    digitos = "".join(c for c in cnpj if c.isdigit())
    return digitos[:8] if len(digitos) >= 8 else ""


def classificar_tomador(cnpj_tomador: str, cnpjs_cadastrados: dict | set) -> TomadorMatch:
    """Classifica o CNPJ tomador de uma nota contra o cadastro de filiais.

    `cnpjs_cadastrados` é o dict de `cnpjs_filiais.json` (chave = CNPJ
    completo em 14 dígitos) OU um set de CNPJs — tanto faz.
    """
    cnpj = "".join(c for c in (cnpj_tomador or "") if c.isdigit())
    if not cnpj:
        return TomadorMatch.AUSENTE

    # Coleção de chaves independente do tipo
    if isinstance(cnpjs_cadastrados, dict):
        chaves = cnpjs_cadastrados.keys()
    else:
        chaves = cnpjs_cadastrados

    if cnpj in chaves:
        return TomadorMatch.EXATO

    raiz = raiz_cnpj(cnpj)
    if not raiz:
        return TomadorMatch.OUTRA_EMPRESA

    for k in chaves:
        if raiz_cnpj(k) == raiz:
            return TomadorMatch.RAIZ_GRUPO

    return TomadorMatch.OUTRA_EMPRESA
