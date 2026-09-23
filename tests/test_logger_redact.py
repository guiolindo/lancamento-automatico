"""
Testes da redação de chaves de API no logger (build-124). Cobrem os
formatos observados em produção: URL com `?key=...` (traceback do
requests), header `x-goog-api-key`, e chave solta com prefixos
Google (AIza... e AQ.Ab8...).
"""

from __future__ import annotations

from src.core.logger import _redact


def test_redige_url_com_key_query():
    """O caso do vazamento reportado: SSLError do requests inclui a URL
    completa com ?key=... no str(exc). Após redação, prefixo `key=`
    fica preservado pra contexto, mas o valor vai pra ***REDACTED***."""
    # String sintética com o mesmo prefixo AQ. do formato do Google.
    # Split em concatenação pra o secret-scanning do GitHub não bater
    # num pattern válido dentro do source.
    chave_fake = "AQ." + "Ab_FAKE_EXAMPLE_USED_IN_TEST_ONLY_XXXXXXXX"
    linha = f"SSLError: HTTPSConnectionPool ... url: /v1beta/models/x:generateContent?key={chave_fake}"
    saida = _redact(linha)
    assert chave_fake not in saida
    assert "key=***REDACTED***" in saida


def test_redige_variacoes_do_prefixo():
    """`key=` e `api_key=` e `api-key=` — todas as variações comuns
    tanto em URLs quanto em query strings."""
    assert "key=***REDACTED***" in _redact("?key=AIzaSyABCDEF123456789012345678901234567")
    assert "api_key=***REDACTED***" in _redact("&api_key=AIzaSyABCDEF123456789012345678901234567")
    assert "api-key=***REDACTED***" in _redact("&api-key=AIzaSyABCDEF123456789012345678901234567")


def test_redige_header_x_goog_api_key():
    """Se algum debug logar headers, o `x-goog-api-key: <chave>` cai
    aqui e também é redigido."""
    saida = _redact("headers: {'x-goog-api-key': 'AIzaSyABCDEF123456789012345678901234567'}")
    assert "AIzaSyABCDEF" not in saida
    assert "x-goog-api-key" in saida  # prefixo preservado


def test_redige_chave_google_prefix_aiza_solta():
    """Se a chave aparece solta em algum log (sem `key=` prefixo),
    o prefixo AIza + 20+ chars ainda é reconhecido e redigido."""
    saida = _redact("chave: AIzaSyABCDEF123456789012345678901234567")
    assert "AIzaSyABCDEF" not in saida
    assert "AIza***REDACTED***" in saida


def test_redige_chave_google_prefix_aq_solta():
    """API key v3 do Google. Padrão observado em log de produção."""
    chave_fake = "AQ." + "Ab_FAKE_EXAMPLE_USED_IN_TEST_ONLY_XXXXXXXX"
    saida = _redact(f"valor: {chave_fake}")
    assert "FAKE_EXAMPLE_USED_IN_TEST_ONLY" not in saida
    assert "AQ.Ab" in saida  # prefixo curto preservado
    assert "REDACTED" in saida


def test_nao_toca_em_texto_sem_chave():
    """Log normal sem chave nenhuma tem que passar intacto — nada de
    regex overzealous rasgando strings normais."""
    linhas = [
        "[INFO] Migrando gemini_api_key (plain) -> gemini_api_key_enc (DPAPI)",
        "Fuzzy match: 'Rib.Neves' -> 'Ribeirao das Neves' (score 92.5)",
        "extrair: HTTP 200",
    ]
    for l in linhas:
        assert _redact(l) == l


def test_multipla_ocorrencia_na_mesma_linha():
    """Se por algum motivo a chave aparece 2x na mesma linha, redige
    ambas."""
    linha = "?key=AIzaSyABCDEF123456789012345678901234567 fallback ?key=AIzaSyGHIJKL123456789012345678901234567"
    saida = _redact(linha)
    assert "AIzaSyABCDEF" not in saida
    assert "AIzaSyGHIJKL" not in saida
    assert saida.count("REDACTED") == 2
