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

## Empacotando um executável portátil (sem admin, sem antivírus dando ruim)

O alvo é um PC corporativo trancado: sem admin, sem instalador, e antivírus
que barra qualquer executável Python "empacotado". Por isso **NÃO usamos
PyInstaller** — ele descompacta Python em `%TEMP%` em runtime, exatamente o
comportamento que AVs marcam como malware.

Em vez disso, **compilamos com Nuitka em modo `--standalone`**: gera código
C→binário nativo real, com muito menor taxa de falso-positivo. A saída é uma
**pasta portátil** que roda em qualquer Windows sem instalação.

### Build (na SUA máquina de desenvolvimento, não na do TOTVS)

Requisitos: Windows x64, Python 3.11 ou 3.12.

```bash
pip install -r requirements.txt
python build/build.py
```

Na primeira compilação o Nuitka baixa o compilador C (MSVC ou MinGW) — aceite.
Demora ~5–10 min. Ao final você tem:

```
dist/LancamentoAutomatico.dist/
├── LancamentoAutomatico.exe    ← execute este
├── mapeamento.json             ← editável sem recompilar
├── config/mapeamento.json      ← cópia interna (fallback)
└── ... (DLLs e recursos)
```

### Levando para o PC do TOTVS

1. Zipe a pasta `LancamentoAutomatico.dist/` inteira.
2. Copie o `.zip` via USB / rede / e-mail para o PC alvo.
3. Descompacte para uma pasta qualquer (Documentos, Desktop, etc — não precisa
   `Program Files`, não precisa admin).
4. Clique em `LancamentoAutomatico.exe`.

O app cria seus dados em `%USERPROFILE%\.lancamento-automatico\` (settings + logs)
— nenhum registro de sistema, nenhuma modificação em pastas protegidas.

### Se ainda assim o antivírus reclamar

Ordem de recurso:
1. **Ícone customizado**: coloque um `build/app.ico` no repositório; o script
   já o usa automaticamente. AV corporativos punem exes sem ícone.
2. **Assinatura digital**: um certificado code-signing (mesmo self-signed
   confiado no domínio) faz o Windows SmartScreen parar de brigar. Falar com TI.
3. **Whitelist por hash**: TI adiciona o hash do `.exe` ao AV corporativo.
   O jeito mais rápido em ambientes muito restritos.

## Editando o de-para de filiais

O arquivo `mapeamento.json` (ao lado do `.exe` na pasta portátil, ou em
`src/config/` em dev) contém o cadastro de filiais, aliases e configurações
de imposto. Adicione novas filiais/lojas editando esse JSON — não precisa
recompilar.

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
  build.py                script Nuitka (portátil, anti-AV)
  app.ico                 (opcional) ícone do executável
```
