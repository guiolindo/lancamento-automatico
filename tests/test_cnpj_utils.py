"""
Testes da validação de CNPJ tomador (build-121). Cobre os 4 resultados
possíveis: EXATO, RAIZ_GRUPO, OUTRA_EMPRESA, AUSENTE.
"""

from __future__ import annotations

from src.core.cnpj_utils import TomadorMatch, classificar_tomador, raiz_cnpj


# Mini-cadastro que imita o `cnpjs_filiais.json` real (só o que
# importa pra teste). Todas as filiais têm a mesma raiz 28548486.
CADASTRO = {
    "28548486000116": {"codigo": 6,  "nome": "Contagem"},
    "28548486000205": {"codigo": 7,  "nome": "Passos"},
    "28548486000388": {"codigo": 10, "nome": "Nova Serrana"},
}


def test_raiz_extrai_8_digitos():
    assert raiz_cnpj("28548486000116") == "28548486"
    assert raiz_cnpj("28.548.486/0001-16") == "28548486"


def test_raiz_string_curta_devolve_vazio():
    assert raiz_cnpj("") == ""
    assert raiz_cnpj("123") == ""


def test_exato_bate_e_libera():
    """Contagem está cadastrada — passa direto."""
    assert classificar_tomador("28548486000116", CADASTRO) == TomadorMatch.EXATO


def test_exato_ignora_pontuacao():
    """Robustez: se o Gemini devolver com formatação, ainda funciona."""
    assert classificar_tomador("28.548.486/0001-16", CADASTRO) == TomadorMatch.EXATO


def test_raiz_grupo_filial_nova_da_mesma_empresa():
    """CNPJ 28548486000999 tem a raiz da Multicom mas o sufixo não está
    cadastrado. É filial nova — bloqueia e pede pra adicionar."""
    assert classificar_tomador("28548486000999", CADASTRO) == TomadorMatch.RAIZ_GRUPO


def test_outra_empresa_nem_a_raiz_bate():
    """CNPJ aleatório de outra empresa (Pluxee, por exemplo)."""
    assert classificar_tomador("20211412000188", CADASTRO) == TomadorMatch.OUTRA_EMPRESA


def test_ausente_string_vazia():
    """Gemini não conseguiu extrair — trata como se fosse outra empresa
    (não confia). Retorno específico pra a UI diferenciar a mensagem."""
    assert classificar_tomador("", CADASTRO) == TomadorMatch.AUSENTE
    assert classificar_tomador(None, CADASTRO) == TomadorMatch.AUSENTE  # type: ignore[arg-type]


def test_aceita_set_alem_de_dict():
    """A API aceita tanto o dict de cnpjs_filiais quanto um set de CNPJs
    — é mais leve pra teste, e a assinatura reflete a flexibilidade."""
    apenas_set = {"28548486000116", "28548486000205"}
    assert classificar_tomador("28548486000116", apenas_set) == TomadorMatch.EXATO
    assert classificar_tomador("28548486000999", apenas_set) == TomadorMatch.RAIZ_GRUPO


def test_cadastro_vazio_tudo_vira_outra_empresa():
    """Edge: se cnpjs_filiais.json está vazio ou não foi carregado,
    todo CNPJ não-vazio cai como 'outra empresa' — ninguém no cadastro
    pra comparar raiz."""
    assert classificar_tomador("28548486000116", {}) == TomadorMatch.OUTRA_EMPRESA
    assert classificar_tomador("", {}) == TomadorMatch.AUSENTE
