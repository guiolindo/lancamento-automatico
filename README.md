# Lançamento Automático — TOTVS + Gemini

Automação de lançamento de guias e resumos de impostos (IRRF sobre folha,
férias, rescisão, adiantamento) no TOTVS/Consinco a partir de PDF ou imagem
do relatório. O documento é enviado ao Gemini, que extrai as linhas
estruturadas; o robô monta os lançamentos usando o de-para de filiais e
executa cada um na tela **Inclusão de Títulos** do TOTVS.

## Rodando em desenvolvimento

```bash
python -m venv .venv
.venv\Scripts\activate         # Windows
pip install -r requirements.txt
python -m src.main
```

Na primeira execução o app pede a chave da API do Gemini e salva em
`~/.lancamento-automatico/settings.json`.

## Empacotando (.exe sem admin)

```bash
pip install pyinstaller
python build/build.py
```

Gera `dist/LancamentoAutomatico.exe` junto com `dist/mapeamento.json`
editável.

## Editando o de-para de filiais

O arquivo `src/config/mapeamento.json` (ou `mapeamento.json` ao lado do
`.exe`) contém o cadastro de filiais, aliases e configurações de imposto.
Adicione novas filiais/lojas editando esse JSON — não precisa recompilar.

## Estrutura

```
src/
  main.py                 entrada da aplicação (PySide6)
  config/mapeamento.json  de-para editável
  core/
    models.py             dataclasses (Lancamento, Filial, Imposto)
    logger.py             log arquivo + console
    mapping.py            loader + fuzzy match de filiais
    settings_store.py     persistência de settings.json local
    gemini_client.py      chamada Gemini + parser + montagem de lançamentos
    rpa_totvs.py          automação da tela via pywinauto/pyautogui
  gui/
    theme.py              QSS dark
    setup_dialog.py       primeiro uso — pede API key
    workers.py            QThread p/ Gemini e p/ execução do lote
    preview_table.py      tabela de revisão
    main_window.py        janela principal
build/
  build.py                script PyInstaller
```
