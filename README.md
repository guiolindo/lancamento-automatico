# Auto Conferi

> Automação de lançamento de guias/resumos de impostos no **TOTVS/Consinco**
> a partir de PDF ou imagem do relatório.

O documento é enviado ao Gemini, que extrai as linhas estruturadas; o app
monta os lançamentos usando o de-para de filiais e executa cada um na
tela **Inclusão de Títulos** (janela "Operador Financeiro") via automação
de teclado/mouse — funciona com o TOTVS aberto no PC local **ou** rodando
dentro de VM via RemoteApp (Auto Sky), onde a janela aparece com sufixo
"(Remoto)".

> **Nome interno / repositório**: `lancamento-automatico` (histórico).
> **Nome comercial exibido ao usuário e no `.exe`**: **Auto Conferi**.
> Todo texto voltado ao usuário — janela, splash, dialogs, updater — usa
> "Auto Conferi". Só o repo Git e o nome do zip publicado
> (`LancamentoAutomatico-portatil.zip`) mantêm o nome antigo por
> compatibilidade com o updater embarcado em builds já distribuídos.

## Módulos

O app tem **dois módulos** na sidebar, cada um automatizando uma tela
diferente do TOTVS:

### 1. Novo lote (Operador Financeiro / Inclusão de Títulos)

Guias/resumos de impostos sobre folha de pagamento.

| Imposto | Status |
| ------- | ------ |
| IRRF (folha, férias, rescisão, adiantamento) | ✅ funcionando |
| INSS (folha, coluna única, ref = mês anterior à emissão) | ✅ funcionando |
| ICMS ST, ISS, PIS/COFINS | 🕓 roadmap — adicionar em `mapeamento.json` |

### 2. Orçamento (Notas Fiscais de Despesa)

Automatiza o form **Notas Fiscais de Despesa** do módulo Orçamento do
TOTVS. Cada fornecedor recorrente vira um **template** em
`mapeamento_orcamento.json` que define TODOS os campos fixos do form; só
3–6 variáveis por documento (número, data, valor, etc.) mudam por lote.

| Fornecedor / documento | Status | Extração via Gemini |
| ---------------------- | ------ | ------------------- |
| Ótimo (Consórcio de Bilhetagem — vale-transporte, NFS-e) | ✅ | Multi-página, 3 campos por nota |
| DAE Bahia — ICMS sobre energia elétrica (regime normal + adic fundo pobreza) | ✅ | Resolve empresa por CNPJ, identifica tipo automaticamente |
| Outros fornecedores recorrentes | 🕓 roadmap — novo entry em `mapeamento_orcamento.json` |

Fluxo idêntico ao módulo principal:
1. Combo → escolhe fornecedor.
2. Arrasta PDF (pode ter várias notas na mesma folha — Gemini deduplica).
3. Extrai → grid mostra 1 linha por documento; edições manuais aceitas.
4. Executar → RPA preenche as 3 abas (Nota / Financeiro / Contabilização),
   clica "+" **uma vez no final**, trata popup de duplicidade (`OK` → `F2`
   borracha → `Sim` → nota marcada IGNORADA — nunca inventa número), e
   clica "Autorizar".

Detalhes técnicos em [ARCHITECTURE.md → Módulo Orçamento](ARCHITECTURE.md).

## Fluxo de uso

1. Abrir o `LancamentoAutomatico.exe` (ou `python -m src.main` em dev).
2. Na primeira execução, o app pede a **chave da API do Gemini** e salva
   em `~/.lancamento-automatico/settings.json`.
3. Abrir o TOTVS na tela **Inclusão de Títulos** (em branco).
4. Selecionar o PDF/imagem do relatório e o Imposto → **Extrair**.
   - Também é possível **arrastar o arquivo** (`.pdf/.png/.jpg/.jpeg/.webp`)
     para dentro da janela (drag-and-drop).
5. Revisar a tabela — corrigir filial, valor ou data se necessário.
6. Opcional: marcar **Não apertar '+' automaticamente** (revisão manual
   entre lançamentos) ou **Testar só o primeiro** (dry-run).
7. **Executar** — o app cria cada título no TOTVS.

> **Configuração de tela detectada automaticamente:**
> - **1 monitor**: ao apertar Executar, a janela principal se **minimiza
>   sozinha** e aparece um HUD compacto no canto superior direito com
>   contador, tempo, ETA e botão de parar — sem cobrir o TOTVS.
> - **2+ monitores**: se a janela principal estiver na mesma tela do
>   TOTVS, ela **se move automaticamente pra outra tela**. Sem HUD,
>   porque você já vê tudo.
>
> Não precisa arrastar nada manualmente.

> **Não precisa calibrar antes.** Todo lote começa com uma **detecção
> automática dos campos por visão computacional** (`src/core/visao_totvs.py`),
> que localiza cada campo pixel-perfect na janela do TOTVS. A janela é
> detectada por substring `Operador Financeiro` (casa também
> `Operador Financeiro (Remoto)` do RemoteApp).
>
> O botão **"Recalibrar (backup)"** existe só como rede de segurança:
> se o auto-detect falhar por causa de mudança de tema/DPI/versão do
> TOTVS, você calibra manualmente uma vez e o resultado fica salvo em
> `~/.lancamento-automatico/calibracao.json` como fallback pros próximos
> lotes. Em máquina padrão, nunca precisa apertar esse botão.

### Parada de emergência

Pressione **END** a qualquer momento durante a execução do lote. O robô
aborta imediatamente (leitura via `GetAsyncKeyState` com `restype=c_short`
+ confirmação de 2 amostras, corrige o falso positivo do build 49;
funciona mesmo se a janela do app não estiver em foco).

### Popup de duplicidade

Se o TOTVS reclamar que o `Nro. Documento` já existe, o app detecta o
popup (via snapshot-diff dos títulos de janela — sem falsos positivos
com "aviso" no browser) e tenta novamente com um número aleatório novo,
até `max_tentativas_duplicidade` vezes (padrão 10, ajustável no settings).

### Instância única

Uma segunda tentativa de abrir o `.exe` **não abre outra janela** — traz
a janela existente pra frente (via `EnumWindows` + `SetForegroundWindow`).
Mutex nomeado `Local\LancamentoAutomatico_SingleInstance_v1`.

## Rodando em desenvolvimento

```bash
python -m venv .venv
.venv\Scripts\activate         # Windows
pip install -r requirements.txt
python -m src.main
```

## Baixando o executável pronto

**Todo commit em `main` publica automaticamente uma versão nova** — o
próprio app se atualiza sozinho na próxima abertura (ver
[ARCHITECTURE.md](ARCHITECTURE.md) → "Auto-update diferido"). Para
instalar do zero:

1. Baixe `LancamentoAutomatico-portatil.zip` de
   https://github.com/guiolindo/lancamento-automatico/releases/tag/latest
2. Descompacte em qualquer pasta (Desktop, Documentos — sem admin).
3. Clique em `LancamentoAutomatico.exe`.

A partir daí o updater cuida das próximas versões.

## Empacotando um executável portátil (sem admin, sem antivírus dando ruim)

O alvo é um PC corporativo trancado: sem admin, sem instalador, e AV
que barra qualquer executável Python "empacotado". Por isso **não usamos
PyInstaller** — ele descompacta Python em `%TEMP%` em runtime, exatamente
o comportamento que AVs marcam como malware.

Em vez disso, **compilamos com Nuitka em modo `--standalone`**: gera
código C→binário nativo real, com taxa muito menor de falso-positivo.
A saída é uma **pasta portátil** que roda em qualquer Windows sem
instalação.

### Build local (na máquina de desenvolvimento)

Requisitos: Windows x64, Python 3.11 ou 3.12.

```bash
pip install -r requirements.txt
pip install nuitka zstandard ordered-set
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

### Build no CI (recomendado)

Todo push em `main` dispara `.github/workflows/build-exe.yml`:

1. Roda Nuitka num runner Windows.
2. Compacta como `LancamentoAutomatico-portatil.zip` (**nome fixo**).
3. Publica na rolling release `latest` do repositório — `softprops`
   sobrescreve o asset in-place, sem janela vazia (fix do build-68).
4. Limpa assets antigos DEPOIS do upload, preservando o atual.

Body da release inclui `BUILD_MARKER=...` e `SHA256=...` — o updater
usa ambos pra detectar versão nova e validar integridade.

### Levando para o PC do TOTVS

1. Zipe a pasta `LancamentoAutomatico.dist/` inteira (ou baixe o zip do
   release).
2. Copie o `.zip` via USB / rede / e-mail.
3. Descompacte para qualquer pasta.
4. Clique em `LancamentoAutomatico.exe`.

## Arquivos de configuração

Tudo fica em `%USERPROFILE%\.lancamento-automatico\` — nenhum registro,
nenhuma modificação em pastas protegidas.

| Arquivo | Conteúdo |
| ------- | -------- |
| `settings.json` | Chave Gemini (cifrada via DPAPI), modelo, delays da automação, config RPA |
| `calibracao.json` | Posições dos 11 campos do TOTVS Operador Financeiro (relativas à janela) e cor RGB do popup |
| `calibracao_orcamento.json` | Posições dos 25 campos da tela Notas Fiscais de Despesa (aba Nota + Financeiro + Contabilização + popups Aviso/Atenção) |
| `lancamento.log` | Log da execução |
| `boot_trace.log` | Trace de inicialização (para depurar crash em startup) |
| `startup_error.log` | Stacktrace se o boot morrer com exceção não tratada |

Se a automação começar a errar depois de uma atualização do TOTVS,
apagar `calibracao.json` e recalibrar (mas antes disso, tenta rodar um
lote — o auto-detect visual pode absorver a mudança sozinho). Se algum
delay estiver curto d+
para o PC alvo (o robô "furando" antes do campo focar), editar
`settings.json` na seção `delays`.

Ao lado do `.exe` (pasta portátil):

| Arquivo | Papel |
| ------- | ----- |
| `mapeamento.json` | De-para de filiais e configurações por imposto (Novo lote) — **editável pelo usuário final sem recompilar** |
| `mapeamento_orcamento.json` | Templates de fornecedores do módulo Orçamento (OTIMO, DAE_ENERGIA, …) — **editável pelo usuário** |
| `cnpjs_filiais.json` | Mapa CNPJ→filial (usado por documentos que endereçam pelo CNPJ, como o DAE Bahia) — **editável** |
| `_next/` | Pasta temporária do updater. Só existe entre "download pronto" e "próximo boot aplica". |
| `_next/READY` | Marker JSON que sinaliza pro launcher aplicar o update no próximo boot |
| `*.exe.old` | Cópia do .exe antigo, deixada pra trás após swap. Removida no boot seguinte. |

### Modelo do Gemini

Padrão: `gemini-3.5-flash-lite`. Modelos antigos (`2.0-flash-exp`,
`2.5-flash-lite`, `2.5-flash`, `1.0-pro`, `gemini-pro`, `pro-vision`) são
migrados automaticamente ao subir uma versão nova do app.

## Editando o de-para de filiais

`mapeamento.json` (ao lado do `.exe` na pasta portátil, ou em
`src/config/` em dev) contém o cadastro de filiais, aliases e
configurações por imposto. Adicione novas filiais/lojas editando esse
JSON — sem recompilar.

Na UI existe também um dialog "De-Para" (menu lateral) que edita o mesmo
arquivo com validação.

## Adicionando um fornecedor novo ao módulo Orçamento

Cada fornecedor é um entry em `mapeamento_orcamento.json` com 3 seções:
`aba_nota`, `aba_financeiro`, `aba_contabilizacao` + um bloco `regras`.
Modos suportados:

- **Simples (tipo OTIMO)**: fornecedor único por template, obs fiscal
  fixa, campos empresa/nat.despesa/pessoa fixos, aba Contabilização só
  replica o valor em N linhas.
- **Por CNPJ (tipo DAE)**: cada documento é endereçado a uma filial
  diferente identificada por CNPJ. `empresa_por_cnpj: true` faz o app
  resolver a filial pela tabela `cnpjs_filiais.json`. A observação pode
  variar por `tipo` do documento (ex.: `regime_normal` vs
  `adic_fundo_pobreza`) via `observacao_por_tipo`. Aba Contabilização
  aceita `linha1.trocar_filial_para_da_loja` + `linha2.conta_debito` /
  `linha2.cr` fixos.

Depois de editar, extrator do Gemini precisa saber como ler esse tipo
de PDF — pra tipos totalmente novos, adicionar prompt em
`src/core/gemini_client.py` e ligar via `tipo_extracao` no template.

## Estrutura do repositório

```
launcher.py                    entrypoint Nuitka (single-instance, apply update, error dialog)
src/
  main.py                      boot do app PySide6 (splash IMEDIATO, depois imports pesados)
                               contém BUILD_MARKER — string que identifica a versão
  config/
    mapeamento.json            de-para de filiais + impostos (Novo lote)
    mapeamento_orcamento.json  templates de fornecedores (Orçamento)
    cnpjs_filiais.json         mapa CNPJ → filial (usado por DAE Bahia e afins)
  assets/
    branding/                  logos do Auto Conferi em 8 tamanhos (16..512 px)
    totvs_reference/           templates de visão computacional
      *.png                    âncoras do Operador Financeiro (child + popup)
      orcamento/               âncoras da tela Notas Fiscais de Despesa
        anchor_header.png      "Notas Fiscais de Despesas" (âncora principal)
        anchor_popup_aviso.png título do popup de duplicidade
        anchor_popup_atencao.png título do popup pós-F2
        aba_*.png              capturas de referência (3 abas × preenchida/branca)
  core/
    models.py                  dataclasses (Lancamento, Filial, Imposto, NotaDespesa)
    logger.py                  log com UTF-8 seguro + rotation 5MB × 3
    mapping.py                 loader + fuzzy match de filiais
    settings_store.py          settings.json + migração de modelo
    secret_store.py            DPAPI para cifrar chave Gemini
    calibracao.py              calibracao.json Operador Financeiro (11 pontos)
    calibracao_orcamento.py    calibracao_orcamento.json (25 pontos: 3 abas + popups)
    gemini_client.py           chamada REST v1beta + prompts (IRRF / INSS / NFS-e / DAE)
    rpa_totvs.py               automação da janela Operador Financeiro
    rpa_orcamento.py           automação da tela Notas Fiscais de Despesa
    visao_totvs.py             detecção pixel-perfect de campos (Operador Financeiro)
    visao_orcamento.py         detecção pixel-perfect (Orçamento) — mesma pattern
    keyboard_utils.py          digita texto no TOTVS — ASCII via typewrite, com
                               acento via clipboard+Ctrl+V (typewrite ignora acento)
    updater.py                 check GitHub Releases + download + SHA256 + extract p/ _next/
  gui/
    theme.py                   QSS + PALETTE_DARK/PALETTE_LIGHT (verde-fisco dark + azul SAP light)
    icons.py                   ícones vetoriais QPainter (não depende de font emoji)
    splash.py                  AutoConferiSplash — splash inicial com logo animada
    updater_bar.py             barra laranja no topo com estado do updater
    hud_execucao.py            HUD flutuante top-right (só em mono-monitor durante lote)
    setup_dialog.py            primeiro uso (API key)
    calibracao_dialog.py       captura das posições no TOTVS — parametrizável pros 2 módulos
    depara_dialog.py           editor do mapeamento.json
    orcamento_dialog.py        OrcamentoPage — página integrada ao main_window (não dialog)
    workers.py                 QThreads (extração + execução do lote — Novo lote e Orçamento)
    preview_table.py           tabela de revisão do Novo lote
    main_window.py             janela principal (QStackedWidget: dashboard + orçamento)
build/
  build.py                     script Nuitka (portátil, anti-AV)
  app.ico                      ícone do .exe (bump de file-version força cache do Explorer a atualizar)
.github/workflows/
  build-exe.yml                CI Windows → rolling release 'latest' + tag v* p/ release oficial
ARCHITECTURE.md                contrato interno (updater ↔ launcher, workflow, race conditions, changelog)
DECISIONS.md                   log de decisões (histórico do que foi discutido e implementado)
```

## Se ainda assim o antivírus reclamar

Ordem de recurso:
1. **Ícone customizado**: `build/app.ico` já está no script.
2. **Assinatura digital**: um certificado code-signing (mesmo self-signed
   confiado no domínio) faz o SmartScreen parar. Falar com TI.
3. **Whitelist por hash**: TI adiciona o hash do `.exe` ao AV corporativo.

## Documentação adicional

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — contratos internos, mecânica
  do auto-update, changelog de builds, gotchas conhecidos. **Leia antes
  de mexer em `updater.py`, `launcher.py` ou no workflow.**
- **[DECISIONS.md](DECISIONS.md)** — log das decisões tomadas ao longo
  do projeto.
