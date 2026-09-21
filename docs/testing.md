# Testing

## Estado atual

Suite `pytest` enxuta — cobre correctness dos pontos que já quebraram
em produção. Não pretende testar RPA em si (impossível sem TOTVS
aberto); testa **as partes puras** que preparam os dados que o RPA usa.

```
tests/
├── conftest.py          # stub PySide6/pyautogui/pywinauto pro import não travar
├── test_models.py       # Filial/Imposto/NotaDespesa validam
├── test_mapping.py      # carrega mapeamento.json + resolve filial por fuzzy
└── test_keyboard.py     # digitar_texto — separa ASCII/unicode corretamente
```

## Rodando

```powershell
pip install -r requirements-dev.txt
pytest                      # todos
pytest tests/test_mapping.py  # um arquivo
pytest -k fuzzy             # só testes com "fuzzy" no nome
pytest --cov=src            # com cobertura (precisa pytest-cov)
```

Tempo total: ~1s. Sem GUI, sem TOTVS aberto, sem chave do Gemini
necessária.

## Onde os testes rodam no CI

`.github/workflows/lint.yml` roda `pytest` depois do `ruff check` em
todo push/PR. Ambiente Ubuntu; PySide6 é stubado (o `conftest.py` faz
o mesmo trick do smoke gate).

## Adicionando teste novo

Regras:

1. **Um bug de produção que reincidir vira teste**. O bug do "elétrica
   virou eltrica" (build-105) e o do "CD Feira ≠ Feira" (build-109)
   são testes que impedem regressão.
2. **Só testa código puro**. Nada que abra janela, chame pyautogui de
   verdade ou fale com Gemini. Se precisa, stuba no `conftest.py`.
3. **Nomeia como o bug**. `test_fuzzy_desambigua_cd_vs_loja` é melhor
   que `test_resolve_filial_case_5`.

Exemplo mínimo:

```python
def test_typewrite_recusa_acentos_e_manda_pro_clipboard(monkeypatch):
    from src.core.keyboard_utils import _eh_ascii_puro
    assert _eh_ascii_puro("ABC")
    assert not _eh_ascii_puro("Elétrica")   # o bug do 105
```

## O que não é testado

- **Pipeline RPA de verdade** — precisa TOTVS aberto na tela certa.
  Testado manualmente pelo Guilherme, uma vez por build antes do push.
- **Extração Gemini** — precisa chave viva e paga na cota. Testado por
  amostra: cada fornecedor novo tem 2-3 PDFs de referência guardados
  fora do repo.
- **Auto-update / auto-recovery** — precisa de release publicada e
  máquina Windows. Testado por observação de campo (o operador reporta
  se ficou preso no boot).
- **Nuitka bundle** — o `build-exe.yml` compila em CI toda push, o
  próprio compile passa/falha é o teste.

Ou seja: **o smoke gate + a suite de unit tests cobrem só a base pura**.
O resto é validação humana. Isso é aceitável porque o público-alvo é
único (operadores da Economart/Multicom) e feedback chega em minutos.
