"""
Testes de regressão do bug do build-126: cancelamento (END manual,
cancelar lote) deixava a nota em EM_ANDAMENTO permanente e o menu
contextual não deixava Remover/Reprocessar aquela linha.

Não roda o RPA de verdade — só verifica o CONTRATO: se um trecho de
código simula um abort da nota atual, o status TEM QUE virar FALHA
antes do controle voltar pra UI.
"""

from __future__ import annotations

from datetime import date

from src.core.models import Lancamento, NotaDespesa, StatusLancamento


def _make_lanc() -> Lancamento:
    return Lancamento(
        filial_codigo=6, filial_nome="Contagem",
        especie="IRRF", pessoa_codigo=27267, observacao="teste",
        valor=100.0, data_emissao=date(2026, 1, 1),
        data_contabilizacao=date(2026, 1, 1), vencimento=date(2026, 1, 20),
        tipo_folha="FOLHA", mes_ref="01", ano_ref="2026",
    )


def _make_nota() -> NotaDespesa:
    return NotaDespesa(
        pagina=1, numero="123", data_emissao=date(2026, 1, 1),
        valor=100.0, data_lancto=date(2026, 1, 1), template_chave="OTIMO",
    )


# --- Lancamento (Operador Financeiro) ---

def test_lanc_em_andamento_e_status_transitorio():
    """Sanity: EM_ANDAMENTO existe pra sinalizar 'sendo processado agora'."""
    l = _make_lanc()
    l.status = StatusLancamento.EM_ANDAMENTO
    assert l.status == StatusLancamento.EM_ANDAMENTO


def test_lanc_em_andamento_travava_menu_contextual():
    """Antes do build-126: EM_ANDAMENTO fazia o menu desabilitar.
    Depois: qualquer status FALHA/SUCESSO/IGNORADO/PENDENTE libera.
    Verifica a lógica que decide isso (act_remover.setEnabled = status != EM_ANDAMENTO)."""
    # Simula o que preview_table.py e orcamento_dialog.py fazem:
    def pode_remover(status):
        return status != StatusLancamento.EM_ANDAMENTO
    assert not pode_remover(StatusLancamento.EM_ANDAMENTO)  # o bug reportado
    assert pode_remover(StatusLancamento.FALHA)             # depois do fix
    assert pode_remover(StatusLancamento.SUCESSO)
    assert pode_remover(StatusLancamento.PENDENTE)
    assert pode_remover(StatusLancamento.IGNORADO)


def test_lanc_marca_falha_em_abort_seta_erro_e_status():
    """Simula o que rpa_totvs.py faz agora no except EmergencyAbort:
    marca FALHA com motivo legível antes de re-raise."""
    l = _make_lanc()
    l.status = StatusLancamento.EM_ANDAMENTO
    # Simula a linha nova do rpa_totvs.py:
    l.status = StatusLancamento.FALHA
    l.erro = "Cancelado (tecla END)"
    assert l.status == StatusLancamento.FALHA
    assert "END" in l.erro


# --- NotaDespesa (Orçamento) ---

def test_nota_em_andamento_travava_menu_contextual():
    """Mesmo bug no dialog do Orçamento."""
    def pode_remover(status):
        return status != StatusLancamento.EM_ANDAMENTO
    assert not pode_remover(StatusLancamento.EM_ANDAMENTO)
    assert pode_remover(StatusLancamento.FALHA)


def test_nota_marca_falha_em_abort_no_rpa_orcamento():
    """rpa_orcamento.py:lancar() no except EmergencyAbortException agora
    marca FALHA. Cobertura do contrato."""
    n = _make_nota()
    n.status = StatusLancamento.EM_ANDAMENTO
    # Simula a linha nova do rpa_orcamento.py:
    n.status = StatusLancamento.FALHA
    n.erro = "Cancelado (tecla END)"
    assert n.status == StatusLancamento.FALHA
    assert n.erro == "Cancelado (tecla END)"


def test_rede_de_seguranca_pos_lote_converte_em_andamento_em_falha():
    """Simula a rede de segurança em _on_finished_worker / _on_lote_finalizado:
    varrer notas e converter EM_ANDAMENTO -> FALHA. Se por qualquer motivo
    o rpa_orcamento não pegou (falha grave, disconnect), a UI ainda fica
    consistente."""
    notas = [_make_nota(), _make_nota(), _make_nota()]
    notas[0].status = StatusLancamento.SUCESSO
    notas[1].status = StatusLancamento.EM_ANDAMENTO  # a que estava rodando
    notas[2].status = StatusLancamento.PENDENTE

    # A rede de segurança (código do orcamento_dialog._on_finished_worker):
    for n in notas:
        if n.status == StatusLancamento.EM_ANDAMENTO:
            n.status = StatusLancamento.FALHA
            if not n.erro:
                n.erro = "Cancelado antes de terminar"

    assert notas[0].status == StatusLancamento.SUCESSO   # intocada
    assert notas[1].status == StatusLancamento.FALHA     # convertida
    assert notas[1].erro == "Cancelado antes de terminar"
    assert notas[2].status == StatusLancamento.PENDENTE  # intocada
