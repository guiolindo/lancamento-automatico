# Getting started

Setup do Auto Conferi em desenvolvimento — do zero à primeira execução.

## Pré-requisitos

- **Windows 10/11** (o RPA usa Win32 API + pywinauto; não funciona em
  Linux/macOS).
- **Python 3.12** (Nuitka 2.4 pinado nessa versão — outras versões geram
  bundle que dá crash em runtime).
- **Git**.
- Uma **chave da API do Gemini** (tier gratuita serve; pega em
  [ai.google.dev](https://ai.google.dev/)).
- Para testar o RPA de verdade: o **TOTVS Consinco aberto** com a janela
  do módulo alvo em branco (Inclusão de Títulos, ou Notas Fiscais de
  Despesa do Orçamento).

## Passos

**1. Clonar e criar venv**

```powershell
git clone https://github.com/guiolindo/lancamento-automatico
cd lancamento-automatico
python -m venv .venv
.venv\Scripts\activate
```

**2. Instalar deps de dev**

```powershell
pip install -r requirements-dev.txt
```

Inclui runtime (PySide6, pyautogui, opencv, etc), linter (`ruff`) e teste
(`pytest`).

**3. Rodar o app**

```powershell
python -m src.main
```

O splash aparece em ~2s, MainWindow em ~4s. Na primeira execução ele pede
a chave do Gemini — cola e clica Salvar. Fica cacheada criptografada em
`%USERPROFILE%\.lancamento-automatico\settings.json`.

**4. Testar o lint**

```powershell
ruff check src/ launcher.py build/
```

Precisa dar `All checks passed!` — o CI trava PRs que não passam.

**5. Rodar os testes**

```powershell
pytest
```

Suite atual roda em ~1s. Sem GUI, sem TOTVS aberto — o `conftest.py`
stuba PySide6 e pyautogui.

**6. Compilar (opcional)**

```powershell
python build/build.py
```

Gera `dist/LancamentoAutomatico.dist/` (~200MB, portátil). Só precisa
disso pra distribuir; em dev use `python -m src.main`.

## Erros comuns

- **"ModuleNotFoundError: PySide6"** — não ativou o venv, ou instalou
  no python global. Confirma com `where python`.
- **Chave do Gemini rejeitada** — verifica se copiou a chave inteira
  (39 chars) e se ela tá ativa em [console.cloud.google.com](https://console.cloud.google.com/).
- **App abre mas TOTVS não responde ao teste** — o RPA procura janela
  com título contendo "Operador Financeiro" ou "Inclusão de Títulos".
  Se o teu TOTVS abre em outra tela, o auto-detect falha. Ver
  [operations.md](operations.md) → "Janela do TOTVS não encontrada".

## Próximos passos

- [testing.md](testing.md) — como adicionar teste novo.
- [../ARCHITECTURE.md](../ARCHITECTURE.md) — o que faz cada módulo.
- [faq.md](faq.md) — dúvidas de operação.
