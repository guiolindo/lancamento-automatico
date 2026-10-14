"""
Testes dos templates TAP e DL (recibo de ressarcimento, build-130).
Cobre: templates carregam, campos obrigatórios presentes, placeholder
`{descricao}` nas observações, regra `mais_antiga_das_duas` do TAP.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MAPEAMENTO = REPO_ROOT / "src" / "config" / "mapeamento_orcamento.json"


@pytest.fixture(scope="module")
def templates() -> dict:
    with open(MAPEAMENTO, encoding="utf-8") as f:
        data = json.load(f)
    return data["templates"]


def test_tap_e_dl_existem(templates):
    assert "TAP" in templates
    assert "DL" in templates


def test_tap_tipo_extracao_recibo(templates):
    """Build-130 criou o tipo 'recibo' pra separar do fluxo NFSe."""
    assert templates["TAP"]["tipo_extracao"] == "recibo"
    assert templates["DL"]["tipo_extracao"] == "recibo"


def test_tap_dl_tem_cnpj_esperado(templates):
    """Protege contra PDF de outro fornecedor cair no lote (igual OTIMO/PLUXEE)."""
    assert templates["TAP"]["cnpj_esperado"] == "31548807000197"
    assert templates["DL"]["cnpj_esperado"] == "38321120000163"


def test_tap_dl_validam_tomador(templates):
    """3 níveis do build-121 ligados: exato / raiz do grupo / outra empresa."""
    assert templates["TAP"]["validar_cnpj_tomador"] is True
    assert templates["DL"]["validar_cnpj_tomador"] is True


def test_tap_dl_roteiam_por_cnpj_tomador(templates):
    """A filial de destino vem do CNPJ tomador (igual OTIMO/PLUXEE —
    não força Contagem)."""
    assert templates["TAP"]["aba_nota"]["empresa_por_cnpj_tomador"] is True
    assert templates["DL"]["aba_nota"]["empresa_por_cnpj_tomador"] is True


def test_tap_dl_natureza_despesa_265(templates):
    assert templates["TAP"]["aba_nota"]["nat_despesa_codigo"] == "265"
    assert templates["DL"]["aba_nota"]["nat_despesa_codigo"] == "265"


def test_tap_pessoa_80088(templates):
    assert templates["TAP"]["aba_nota"]["pessoa_codigo"] == "80088"


def test_dl_pessoa_108101(templates):
    assert templates["DL"]["aba_nota"]["pessoa_codigo"] == "108101"


def test_observacao_usa_placeholder_descricao(templates):
    """A observação é dinâmica (texto literal da nota, extraído pelo
    Gemini). Resolver em `rpa_orcamento._formatar_template` substitui
    `{descricao}` pelo campo da NotaDespesa."""
    for chave in ("TAP", "DL"):
        assert templates[chave]["aba_nota"]["observacao_fiscal_template"] == "{descricao}"
        assert templates[chave]["aba_financeiro"]["observacao_financeira_template"] == "{descricao}"


def test_tap_cr_150001(templates):
    """TAP: CR na linha 2 da Contab = 150001."""
    assert templates["TAP"]["aba_contabilizacao"]["linha2"]["cr"] == "150001"


def test_dl_cr_150004(templates):
    """DL: CR na linha 2 da Contab = 150004."""
    assert templates["DL"]["aba_contabilizacao"]["linha2"]["cr"] == "150004"


def test_contab_troca_filial_nas_duas_linhas(templates):
    """Mesma pattern de OTIMO/PLUXEE: as 2 linhas da Contab recebem a
    filial resolvida pelo CNPJ tomador (não o empresa_codigo fixo)."""
    for chave in ("TAP", "DL"):
        contab = templates[chave]["aba_contabilizacao"]
        assert contab["linha1"]["trocar_filial_para"] == "filial_emissao"
        assert contab["linha2"]["trocar_filial_para"] == "filial_emissao"


def test_tap_regra_data_emissao_mais_antiga(templates):
    """TAP tem 2 datas no doc (DATA + Emissão). Regra pega a mais antiga."""
    assert templates["TAP"]["regras"]["data_emissao_regra"] == "mais_antiga_das_duas"


def test_dl_sem_regra_de_emissao_especial(templates):
    """DL tem 1 data só — não precisa regra. Conversor pega a única."""
    assert "data_emissao_regra" not in (templates["DL"].get("regras") or {})


def test_conta_debito_ausente_na_l2(templates):
    """Resposta do usuário: `conta_debito` da L2 é fixo/não preencher.
    Pros recibos TAP/DL, não especificamos — rpa pula a linha quando
    `cfg.get('conta_debito')` é falsy."""
    for chave in ("TAP", "DL"):
        assert "conta_debito" not in templates[chave]["aba_contabilizacao"]["linha2"]


def test_tap_dl_vencimento_manual(templates):
    """Build-131: TAP e DL exigem vencimento_igual_a = vencimento_manual
    na aba_financeiro (local que o rpa_orcamento lê). O picker separado
    na UI preenche a data; sem esse flag o RPA cairia no default
    data_lancto, perdendo a escolha do operador."""
    for chave in ("TAP", "DL"):
        assert templates[chave]["aba_financeiro"]["vencimento_igual_a"] == "vencimento_manual"


def test_otimo_pluxee_nao_mexeram_no_vencimento(templates):
    """Regressão: ao atualizar TAP/DL, mantive OTIMO/PLUXEE inalterados —
    vencimento_manual é opt-in. OTIMO/PLUXEE declaram só em `regras`
    (default `data_lancto`, que o RPA já aplica como fallback)."""
    assert templates["OTIMO"]["regras"]["vencimento_igual_a"] == "data_lancto"
    assert templates["PLUXEE"]["regras"]["vencimento_igual_a"] == "data_lancto"
    # Nenhum dos dois ganhou override em aba_financeiro
    assert "vencimento_igual_a" not in templates["OTIMO"]["aba_financeiro"]
    assert "vencimento_igual_a" not in templates["PLUXEE"]["aba_financeiro"]
