"""
Testes do MappingRepository — o carregador de `mapeamento.json`.

O foco é a resolução de filial por fuzzy: essa foi a fonte de várias
regressões (build-108 aliases, build-109 rerank CD vs Loja) e o operador
sente diretamente quando erra.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.mapping import MappingRepository
from src.core.models import TipoFilial


REPO_ROOT = Path(__file__).resolve().parent.parent
MAPPING_PATH = REPO_ROOT / "src" / "config" / "mapeamento.json"


@pytest.fixture(scope="module")
def repo() -> MappingRepository:
    """Carrega o mapeamento real do repo, uma vez por módulo."""
    return MappingRepository(MAPPING_PATH)


def test_mapping_carrega_todas_as_filiais(repo):
    """Se o número de filiais mudar sem intenção, esse teste avisa. Não
    é vinculante — atualiza o número quando adicionar filial nova."""
    assert len(repo.filiais) >= 30
    assert all(f.codigo > 0 for f in repo.filiais)


def test_mapping_carrega_impostos_esperados(repo):
    """IRRF, INSS, FGTS_CONSIG são os que estão em produção. Outros
    podem existir em roadmap."""
    disponiveis = set(repo.impostos_disponiveis())
    assert {"IRRF", "INSS", "FGTS_CONSIG"} <= disponiveis


def test_fgts_consig_declara_pessoa_por_filial(repo):
    """A regra do FGTS_CONSIG: Pessoa vem da filial, não do imposto.
    Se essa flag voltar pra False, o RPA preenche pessoa errada."""
    fgts = repo.imposto("FGTS_CONSIG")
    assert fgts.pessoa_por_filial is True
    assert "MFGTS" in fgts.especie_por_coluna.values()
    assert "CONSIG" in fgts.especie_por_coluna.values()


def test_resolve_filial_por_nome_exato(repo):
    """Nome idêntico ao cadastro tem que resolver sem fuzzy."""
    f = repo.resolve_filial("Contagem")
    assert f is not None
    assert f.codigo == 6


def test_resolve_filial_por_alias(repo):
    """Aliases são o mecanismo que carrega variações que o PDF vem.
    'LEM' é um dos apelidos de Luis Eduardo Magalhães."""
    f = repo.resolve_filial("LEM")
    assert f is not None
    assert f.codigo == 20


def test_resolve_filial_case_insensitive(repo):
    """A normalização joga tudo em uppercase antes do match."""
    f_lower = repo.resolve_filial("contagem")
    f_upper = repo.resolve_filial("CONTAGEM")
    assert f_lower is not None and f_upper is not None
    assert f_lower.codigo == f_upper.codigo


def test_resolve_filial_com_acento(repo):
    """Acentos são strippados na normalização — 'Poços' encontra 'Pocos'
    e vice-versa."""
    com_acento = repo.resolve_filial("Poços de Caldas")
    sem_acento = repo.resolve_filial("Pocos de Caldas")
    assert com_acento is not None and sem_acento is not None
    assert com_acento.codigo == sem_acento.codigo == 11


def test_resolve_filial_fuzzy_tolera_variacao(repo):
    """O operador digita "Rib. Neves" — o cadastro é "Ribeirao das Neves"
    com alias "RIB NEVES". Fuzzy tem que casar."""
    f = repo.resolve_filial("Rib. Neves")
    assert f is not None
    assert f.codigo == 14


def test_resolve_filial_desconhecida_devolve_none(repo):
    """Nome que não existe nem via fuzzy tem que devolver None (não
    inventar uma filial errada). O RPA usa isso pra pular a linha."""
    f = repo.resolve_filial("Empresa Que Não Existe SA")
    assert f is None


def test_cd_e_loja_tem_tipo_diferente(repo):
    """Depende disso pra pintar diferente na UI e pro rerank do fuzzy
    (build-109 — evitar CD virar Loja)."""
    cd = next((f for f in repo.filiais if f.tipo == TipoFilial.CD), None)
    loja = next((f for f in repo.filiais if f.tipo == TipoFilial.LOJA), None)
    assert cd is not None
    assert loja is not None


def test_filial_por_codigo(repo):
    """Lookup direto, usado pelo menu contextual de edição da tabela."""
    f = repo.filial_por_codigo(6)
    assert f is not None and f.nome == "Contagem"

    assert repo.filial_por_codigo(99999) is None
