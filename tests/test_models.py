"""
Testes dos dataclasses do domínio. Cobre a superfície que impostos
FGTS_CONSIG (build-113) adicionou — `pessoa_por_filial`,
`especie_por_coluna`, `observacao_por_coluna` — porque foi ali que a
retrocompatibilidade era frágil.
"""

from __future__ import annotations

from datetime import date

from src.core.models import (
    Filial,
    Imposto,
    Lancamento,
    StatusLancamento,
    TipoFilial,
)


def test_filial_defaults():
    """Filial sem aliases nem codigo_consinco não pode explodir — a maioria
    das entradas em cnpjs_filiais.json ainda não tem codigo_consinco."""
    f = Filial(codigo=1, nome="Matriz", tipo=TipoFilial.ADM)
    assert f.aliases == []
    assert f.codigo_consinco is None


def test_filial_com_codigo_consinco():
    """FGTS_CONSIG precisa desse campo. Se sumir, o RPA vai preencher
    Pessoa com pessoa_codigo do imposto (errado)."""
    f = Filial(codigo=10, nome="Loja X", tipo=TipoFilial.LOJA, codigo_consinco=1010)
    assert f.codigo_consinco == 1010


def test_imposto_retrocompativel_sem_campos_novos():
    """Um imposto antigo (IRRF, INSS) não declara os campos multi-espécie.
    Não pode dar TypeError no construtor — os defaults têm que segurar."""
    i = Imposto(
        chave="IRRF",
        descricao="IRRF folha",
        especie_totvs="IRRF",
        especie_descricao="IRRF",
        pessoa_codigo=999,
        pessoa_nome="Receita Federal",
        observacao_template="IRRF REF: {mes_ref}/{ano_ref}",
    )
    assert i.pessoa_por_filial is False
    assert i.especie_por_coluna == {}
    assert i.observacao_por_coluna == {}


def test_imposto_multi_especie_fgts_consig():
    """FGTS_CONSIG: 2 lançamentos por linha, cada um com sua espécie."""
    i = Imposto(
        chave="FGTS_CONSIG",
        descricao="FGTS + Consignado",
        especie_totvs="MFGTS",  # fallback
        especie_descricao="FGTS",
        pessoa_codigo=0,  # não usado — pessoa_por_filial=True
        pessoa_nome="",
        observacao_template="",
        pessoa_por_filial=True,
        especie_por_coluna={"FGTS": "MFGTS", "CONSIG": "CONSIG"},
        observacao_por_coluna={"FGTS": "FGTS", "CONSIG": "CONSIG"},
    )
    assert i.pessoa_por_filial
    assert i.especie_por_coluna["CONSIG"] == "CONSIG"


def test_lancamento_status_default_pendente():
    """Regra: um Lancamento novo é sempre PENDENTE. A tabela da UI
    depende disso pra pintar linha e liberar Executar."""
    l = Lancamento(
        filial_codigo=1,
        filial_nome="Matriz",
        especie="IRRF",
        pessoa_codigo=999,
        observacao="teste",
        valor=100.0,
        data_emissao=date(2026, 1, 1),
        data_contabilizacao=date(2026, 1, 1),
        vencimento=date(2026, 1, 20),
        tipo_folha="FOLHA",
        mes_ref="01",
        ano_ref="2026",
    )
    assert l.status == StatusLancamento.PENDENTE


def test_status_enum_valores_esperados():
    """A UI depende desses 5 estados. Adicionar/remover valor daqui
    quebra pintura da tabela e serializacão de lote em progresso."""
    assert {s.value for s in StatusLancamento} == {
        "PENDENTE", "EM_ANDAMENTO", "SUCESSO", "FALHA", "IGNORADO",
    }
