"""
Testes das mensagens amigáveis de erro do Gemini (build-124).

Não faz chamada real ao Gemini — só exercita os tradutores puros que
mapeiam HTTP code / tipo de exception → texto em PT-BR pro operador.
"""

from __future__ import annotations

import pytest
import requests

from src.core.gemini_client import (
    GeminiError,
    _mensagem_para_exception,
    _mensagem_para_http,
)


# --- HTTP status codes ---

def test_http_400_diz_arquivo_invalido():
    msg = _mensagem_para_http(400)
    assert "rejeitou o arquivo" in msg
    assert "PDF" in msg or "imagem" in msg


def test_http_401_diz_chave_invalida():
    msg = _mensagem_para_http(401)
    assert "chave" in msg.lower()


def test_http_403_mesma_mensagem_que_401():
    """401 e 403 mostram a mesma coisa pro operador — ambos são
    chave inválida/revogada na prática do Gemini."""
    assert _mensagem_para_http(401) == _mensagem_para_http(403)


def test_http_429_diz_cota_e_da_saida():
    """O caso mais comum de tier gratuita. Menciona limite E dá 2
    opções pro operador (esperar OU trocar chave)."""
    msg = _mensagem_para_http(429)
    assert "limite" in msg.lower() or "cota" in msg.lower()
    assert "outra chave" in msg.lower() or "espera" in msg.lower()


def test_http_5xx_diz_google_fora_do_ar():
    """500-504: menciona Google e dá tempo de espera concreto."""
    for code in (500, 502, 503, 504):
        msg = _mensagem_para_http(code)
        assert "Google" in msg
        assert "segundos" in msg


def test_http_desconhecido_tem_fallback_pt_br():
    """HTTP 418 ou qualquer coisa fora da tabela: fallback ainda em
    PT-BR e menciona o código pra o suporte identificar."""
    msg = _mensagem_para_http(418)
    assert "418" in msg
    # Nada de inglês
    assert "error" not in msg.lower()
    assert "failed" not in msg.lower()


# --- Exceptions do requests ---

def test_ssl_error_menciona_antivirus_e_ti():
    """Foi o erro real no log de produção — SSL cert self-signed no
    interceptor corporativo."""
    exc = requests.exceptions.SSLError("blabla")
    msg = _mensagem_para_exception(exc)
    assert "antivírus" in msg.lower() or "proxy" in msg.lower()
    assert "TI" in msg


def test_connect_timeout_menciona_internet():
    exc = requests.exceptions.ConnectTimeout("timeout")
    msg = _mensagem_para_exception(exc)
    assert "internet" in msg.lower() or "conexão" in msg.lower()


def test_read_timeout_menciona_arquivo_grande():
    """Diferencia do connect-timeout — read é lento porque o PDF é grande."""
    exc = requests.exceptions.ReadTimeout("read")
    msg = _mensagem_para_exception(exc)
    assert "arquivo" in msg.lower() or "PDF" in msg


def test_connection_error_menciona_bloqueio():
    exc = requests.exceptions.ConnectionError("no route")
    msg = _mensagem_para_exception(exc)
    assert "conexão" in msg.lower() or "internet" in msg.lower()


def test_exception_desconhecida_nao_expoe_str_exc():
    """RegressÃo do vazamento: NUNCA passa `str(exc)` — pode conter
    URL com chave. Fallback é uma linha genérica em PT-BR."""
    exc = ValueError("segredo AQ.AbXYZ pode estar aqui")
    msg = _mensagem_para_exception(exc)
    assert "AQ.AbXYZ" not in msg
    assert "segredo" not in msg


# --- GeminiError API ---

def test_gemini_error_e_subclasse_de_runtime_error():
    """Compat: código antigo captura RuntimeError; novo captura
    GeminiError. Ambos funcionam."""
    with pytest.raises(RuntimeError):
        raise GeminiError("teste")
    with pytest.raises(GeminiError):
        raise GeminiError("teste")


def test_gemini_error_preserva_causa_no_from():
    """A causa técnica original fica em __cause__ pra log detalhado,
    mas nunca aparece no str(exc) que vai pra UI."""
    try:
        try:
            raise requests.exceptions.SSLError("cert com chave AQ.Ab8 no meio")
        except Exception as orig:
            raise GeminiError("Antivírus interceptando") from orig
    except GeminiError as e:
        assert "AQ.Ab8" not in str(e)
        assert isinstance(e.__cause__, requests.exceptions.SSLError)
