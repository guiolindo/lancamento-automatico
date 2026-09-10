# Lançamento Automático — TOTVS + Gemini

Automação de lançamento de guias/resumos de impostos no TOTVS/Consinco a
partir de PDF ou imagem do relatório. O documento é enviado ao Gemini, que
extrai as linhas estruturadas; o app monta os lançamentos usando o de-para
de filiais e executa cada um na tela **Inclusão de Títulos** (janela
"Operador Financeiro") via automação de teclado/mouse — funciona com o
TOTVS aberto no PC local **ou** rodando dentro da VM via RemoteApp
(Auto Sky), onde a janela aparece com sufixo "(Remoto)".

## Impostos suportados

| Imposto | Status |
| ------- | ------ |
| IRRF (folha, férias, rescisão, adiantamento) | ✅ funcionando |
| ICMS ST, INSS, ISS, PIS/COFINS | 🕓 roadmap — adicionar em `mapeamento.json` |

## Fluxo de uso

1. Abrir o `LancamentoAutomatico.exe` (ou `python -m src.main` em dev).
2. Na primeira execução, o app pede a **chave da API do Gemini** e salva
   em `~/.lancamento-automatico/settings.json`.
3. Abrir o TOTVS na tela **Inclusão de Títulos** (em branco).
4. Clicar em **Calibrar campos do TOTVS** — para cada campo o app mostra
   um countdown de 3s, o usuário passa o mouse por cima do campo real no
   TOTVS, e a posição é gravada em `~/.lancamento-automatico/calibracao.json`.
   A janela é detectada automaticamente por substring `Operador Financeiro`
   (casa também `Operador Financeiro (Remoto)`).
5. Selecionar o PDF/imagem do relatório e o Imposto → **Extrair**.
6. Revisar a tabela — corrigir filial, valor ou data se necessário.
7. Opcional: marcar **Não apertar '+' automaticamente** (revisão manual
   entre lançamentos), ou **Testar só o primeiro** (dry-run).
8. **Executar** — o app cria cada título no TOTVS.

### Parada de emergência

Pressione **END** a qualquer momento durante a execução do lote. O robô
aborta imediatamente (leitura via `GetAsyncKeyState`, funciona mesmo se a
janela do app não estiver em foco).

### Popup de duplicidade

Se o TOTVS reclamar que o `Nro. Documento` já existe, o app detecta o
popup (via snapshot-diff dos títulos de janela — sem falsos positivos com
"aviso" no browser) e tenta novamente com um número aleatório novo, até
`max_tentativas_duplicidade` vezes (padrão 10, ajustável no settings).

## Rodando em desenvolvimento

```bash
python -m venv .venv
.venv\Scripts\activate         # Windows
pip install -r requirements.txt
python -m src.main
```

## Baixando o executável pronto (mais rápido)

Todo commit em `main` dispara o workflow `.github/workflows/build-exe.yml`
no GitHub Actions, que compila com Nuitka num runner Windows e publica o
zip portátil como artefato.

- **Aba Actions** → última execução verde de "Build .exe portátil" → baixe
  `LancamentoAutomatico-portatil.zip`.
- Ou crie uma tag `v0.1.0` e o mesmo zip vira uma **Release** oficial.

Descompacte em qualquer pasta do PC alvo (Desktop, Documentos — sem admin)
e clique em `LancamentoAutomatico.exe`.

## Empacotando um executável portátil (sem admin, sem antivírus dando ruim)

O alvo é um PC corporativo trancado: sem admin, sem instalador, e antivírus
que barra qualquer executável Python "empacotado". Por isso **não usamos
PyInstaller** — ele descompacta Python em `%TEMP%` em runtime, exatamente
o comportamento que AVs marcam como malware.

Em vez disso, **compilamos com Nuitka em modo `--standalone`**: gera código
C→binário nativo real, com taxa muito menor de falso-positivo. A saída é
uma **pasta portátil** que roda em qualquer Windows sem instalação.

### Build (na máquina de desenvolvimento, não na do TOTVS)

Requisitos: Windows x64, Python 3.11 ou 3.12.

```bash
pip install -r requirements.txt
python build/build.py
```

Na primeira compilação o Nuitka baixa o compilador C (MSVC ou MinGW) —
aceite. Demora ~5–10 min. Ao final:

```
dist/LancamentoAutomatico.dist/
├── LancamentoAutomatico.exe    ← execute este
├── mapeamento.json             ← editável sem recompilar
├── config/mapeamento.json      ← cópia interna (fallback)
└── ... (DLLs e recursos)
```

### Levando para o PC do TOTVS

1. Zipe a pasta `LancamentoAutomatico.dist/` inteira.
2. Copie o `.zip` via USB / rede / e-mail.
3. Descompacte para qualquer pasta (Documentos, Desktop, etc — não precisa
   `Program Files`, não precisa admin).
4. Clique em `LancamentoAutomatico.exe`.

## Arquivos de configuração

Tudo fica em `%USERPROFILE%\.lancamento-automatico\` — nenhum registro,
nenhuma modificação em pastas protegidas.

| Arquivo | Conteúdo |
| ------- | -------- |
| `settings.json` | Chave Gemini, modelo, delays da automação, config RPA |
| `calibracao.json` | Posições dos 11 campos do TOTVS (relativas à janela) e cor RGB do popup |
| `lancamento.log` | Log da execução |
| `boot_trace.log` | Trace de inicialização (para depurar crash em startup) |

Se a automação começar a errar depois de uma atualização do TOTVS, apagar
`calibracao.json` e recalibrar. Se algum delay estiver curto d+ para o PC
alvo (o robô "furando" antes do campo focar), editar `settings.json` na
seção `delays`.

### Modelo do Gemini

Padrão: `gemini-3.5-flash-lite`. Modelos antigos (`2.0-flash-exp`,
`2.5-flash-lite`, `2.5-flash`, `1.0-pro`, `gemini-pro`, `pro-vision`) são
migrados automaticamente ao subir uma versão nova do app.

## Editando o de-para de filiais

`mapeamento.json` (ao lado do `.exe` na pasta portátil, ou em `src/config/`
em dev) contém o cadastro de filiais, aliases e configurações por imposto.
Adicione novas filiais/lojas editando esse JSON — sem recompilar.

## Estrutura

```
launcher.py               entrypoint Nuitka (fix stdio, error dialog)
src/
  main.py                 boot do app (PySide6)
  config/mapeamento.json  de-para editável
  core/
    models.py             dataclasses (Lancamento, Filial, Imposto)
    logger.py             log com UTF-8 seguro
    mapping.py            loader + fuzzy match de filiais
    settings_store.py     settings.json + migração de modelo
    calibracao.py         calibracao.json (11 pontos + cor popup)
    gemini_client.py      chamada REST v1beta + parser
    rpa_totvs.py          automação da janela Operador Financeiro
  gui/
    theme.py              QSS dark
    setup_dialog.py       primeiro uso (API key)
    calibracao_dialog.py  captura das posições no TOTVS
    workers.py            QThread p/ extração e p/ execução do lote
    preview_table.py      tabela de revisão
    main_window.py        janela principal
build/
  build.py                script Nuitka (portátil, anti-AV)
  app.ico                 (opcional) ícone do executável
.github/workflows/
  build-exe.yml           CI Windows → artefato .zip / Release em tag v*
```

## Se ainda assim o antivírus reclamar

Ordem de recurso:
1. **Ícone customizado**: coloque um `build/app.ico`; o script já usa.
2. **Assinatura digital**: um certificado code-signing (mesmo self-signed
   confiado no domínio) faz o SmartScreen parar. Falar com TI.
3. **Whitelist por hash**: TI adiciona o hash do `.exe` ao AV corporativo.
