# Arquitetura

Documento vivo dos **contratos internos** — coisas que não estão óbvias
lendo um arquivo só, e que fatalmente causam bug se contribuidor novo
(humano ou IA) mudar sem entender.

> Se você é uma IA acabando de entrar no projeto: **leia este documento
> inteiro antes de tocar em `updater.py`, `launcher.py`, `main.py` ou
> `.github/workflows/build-exe.yml`**. As três camadas conversam por
> convenções que não estão declaradas no código.

---

## 1. Camadas do app

```
┌───────────────────────────────────────────────────────────────┐
│  launcher.py         (entrypoint Nuitka, roda ANTES de src/)  │
│  - blinda stdio                                                │
│  - silencia warnings/telemetria                                │
│  - mutex single-instance                                       │
│  - APLICA update pendente (_next/READY) — antes de importar Qt │
│  - reinicia via subprocess + os._exit(0)                       │
│  - envolve tudo em try/except → MessageBox + startup_error.log │
└───────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌───────────────────────────────────────────────────────────────┐
│  src/main.py         (boot do app Qt)                          │
│  - BUILD_MARKER (string da versão)                             │
│  - QApplication + splash IMEDIATO                              │
│  - depois importa módulos pesados (com etapas no splash)       │
│  - abre MainWindow                                             │
└───────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌───────────────────────────────────────────────────────────────┐
│  src/core/          (lógica de negócio, sem Qt)                │
│    updater.py       check + download + hash + extract          │
│    rpa_totvs.py     automação de teclado/mouse                 │
│    visao_totvs.py   detecção de campos                         │
│    gemini_client.py extração via API                           │
│    mapping.py       de-para de filiais                         │
│    settings_store.py + calibracao.py                           │
└───────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌───────────────────────────────────────────────────────────────┐
│  src/gui/           (PySide6/Qt)                               │
│    theme.py         PALETTE_DARK, PALETTE_LIGHT, QSS           │
│    main_window.py   single-screen operacional                  │
│    splash.py        AutoConferiSplash — logo animada           │
│    updater_bar.py   barra laranja de estado do updater         │
│    workers.py       QThreads (extração e execução do lote)     │
└───────────────────────────────────────────────────────────────┘
```

Regra dura: `core/` **nunca** importa `PySide6`. Isso permite testar a
lógica sem stack Qt e mantém o updater executável mesmo se algo do Qt
quebrar.

---

## 2. Auto-update diferido (Opção D)

O ponto de contrato mais delicado do projeto. Três participantes:

1. **`src/core/updater.py`** — quem baixa.
2. **`launcher.py`** — quem aplica.
3. **`.github/workflows/build-exe.yml`** — quem publica.

### 2.1 Ciclo de vida

```
[usuário abre o app]
     │
     ▼
launcher.py: existe <install>/_next/READY?
     │
     ├── NÃO → segue boot normal → src/main.py → MainWindow
     │                                              │
     │                                              ▼
     │                        MainWindow._check_atualizacao_boot()
     │                        - retry em 4s → 30s → 60s → 120s
     │                        - roda updater.check() em QThread
     │                        - watchdog 22s pra não travar
     │                              │
     │                              ▼
     │                        Tem versão nova?
     │                              │
     │                              ▼
     │                        updater.baixar_e_preparar()
     │                        (streaming, SHA256, extract p/ _next_dl/,
     │                         move pra _next/, escreve READY POR ÚLTIMO)
     │                              │
     │                              ▼
     │                        UpdaterBar mostra "Atualização pronta —
     │                        vai aplicar na próxima abertura"
     │
     └── SIM → abre splash Qt com progresso
              │
              ▼
              _aplicar_pendente(cb):
                1. renomeia <exe> → <exe>.old
                2. copia _next/<exe> pro lugar do <exe>
                3. copia demais arquivos de _next/ por cima
                4. deleta _next/ se 0 falhas (senão: só deleta READY
                   pra não re-aplicar em loop, mas mantém arquivos
                   pra o próximo boot tentar de novo)
              │
              ▼
              subprocess.Popen do <exe> novo (DETACHED_PROCESS)
              os._exit(0)  ← esse processo carrega o binário ANTIGO
                             em RAM, então NÃO adianta tentar re-importar
                             — precisa lançar um processo novo.
```

### 2.2 Contrato do marker `_next/READY`

- É um **arquivo JSON** com `{build_marker, sha256, asset_tamanho}`.
- **Só é criado como último passo** de `baixar_e_preparar()` —
  se ele existe, TODOS os arquivos já foram validados e movidos.
- O launcher **só age** se ele existir. `_next/` sem READY é "sujeira"
  (download interrompido) e é apagado pelo próximo `limpar_download_parcial()`.
- Após aplicar com sucesso, `launcher._aplicar_pendente` remove READY
  **primeiro** — se algo abaixo falhar, o próximo boot não vai
  re-aplicar em loop.

Se você mexer no updater ou launcher: **preserve essa ordem**. É a única
proteção contra estados intermediários bagunçando a instalação.

### 2.3 Race condition do workflow (fix do build-68)

**Bug**: até o build-67, o workflow rodava "Limpar assets antigos"
**antes** do upload do novo zip. Isso abria uma janela de ~10s onde a
release ficava sem asset. Clientes que já tinham feito `check()` tinham
uma URL de asset que ia dar 404.

**Fix em duas camadas** (não redundância, defesa em profundidade):
1. **Workflow**: publica primeiro (softprops sobrescreve por nome, sem
   janela vazia), limpa depois preservando `$env:ZIP_NAME`.
2. **Updater**: `baixar_e_preparar()` retenta 1x com URL nova via
   `check()` se receber 404 no primeiro try. Cobre clientes com URL
   velha em memória e edge case onde o workflow ainda esteja rodando
   durante o download.

**Se você mudar o workflow**: nunca inverta essa ordem. Nunca delete o
asset atual sem já ter subido o substituto.

### 2.4 Estados de erro visíveis ao usuário

`src/gui/updater_bar.py` (barra laranja no topo) mostra:
- **Amarelo** — "Verificando…", "Baixando… X%".
- **Verde** — "Atualização pronta pra próxima abertura" (auto-esconde 6s).
- **Vermelho** — mensagem do erro (auto-esconde 8s).

Não tem botão X. Fecha sozinho. Decisão do build-63 (usuário achou o X
poluente).

### 2.5 BUILD_MARKER

Só é atualizado em um lugar: `src/main.py`, linha próxima ao topo:

```python
BUILD_MARKER = "build-XX (descrição curta)"
```

O workflow extrai essa string via regex, coloca no body da release como
`BUILD_MARKER=...`, e o `updater.check()` compara com o local pra decidir
se tem versão nova.

**Bumpar SEMPRE que push pra `main`**. Se esquecer, o updater não detecta
a nova versão porque o marcador remoto == local.

Formato preferido: `build-NN (descrição curta em português)`.
Ex.: `build-68 (fix race condition HTTP 404 no auto-update)`.

---

## 3. Splash inicial (build-66)

`src/main.py` foi reordenado no build-66 pra mostrar splash **antes**
dos imports pesados. Ordem:

1. `import sys, pathlib` (leve).
2. Imports **mínimos** do Qt (`QApplication`, `QMessageBox`, `QIcon`,
   `QTimer`).
3. Cria `QApplication`.
4. Cria e mostra `AutoConferiSplash` (logo + wordmark + progresso
   indeterminado).
5. `app.processEvents()` — força o splash a aparecer.
6. **Agora** importa o resto (core.logger, core.mapping, gui.main_window).
   Cada import atualiza `splash.set_etapa(...)`.

Antes disso, o usuário via ~10s de tela preta em cold boot. Agora vê o
splash em ~2s.

**Se você adicionar import pesado**: coloque-o **depois** do splash e
adicione uma linha `splash.set_etapa("...")` pra dar feedback.

---

## 4. Palette / theme

`src/gui/theme.py` define duas paletas (`PALETTE_DARK`, `PALETTE_LIGHT`)
e cores de marca (`BRAND_TEAL`, `BRAND_INDIGO`).

- **Nunca** hardcode hex em outros arquivos — puxe de `theme.PALETTE_DARK`
  ou dos `BRAND_*`.
- **Aliases legados**: `BRAND_ORANGE = BRAND_TEAL`, `BRAND_BLUE = BRAND_INDIGO`.
  Código antigo (pré-rebrand build-64) referencia os antigos e continua
  funcionando. **Código novo** deve usar `BRAND_TEAL`/`BRAND_INDIGO`
  diretamente.

Ícones: usar `src/gui/icons.py` (QPainter, resolução-agnóstico). Não usar
emoji Unicode em botões — renderização varia entre Windows 10 e 11 e
entre DPIs.

---

## 4b. Auto-detect visual de campos do TOTVS (builds 36-39)

Complementa (e na prática substitui) a calibração manual antiga.

### O que faz

`src/core/visao_totvs.py` expõe
`preencher_calibracao_automatica(calibracao) -> (ok: bool, msg: str)`.
Ele:

1. Detecta a janela `Operador Financeiro` (substring, case-insensitive
   — casa `Operador Financeiro (Remoto)` do RemoteApp/Auto Sky).
2. Captura a região da janela via `mss` (screenshot rápido).
3. Roda OpenCV / template matching contra os elementos conhecidos da
   tela **Inclusão de Títulos** pra localizar cada campo pixel-perfect.
4. Sobrescreve `calibracao.campos` com as coordenadas detectadas
   **em memória** — não persiste em disco. Isso é chave: a calibração
   manual salva em `calibracao.json` fica intacta como fallback.

### Quando é chamado

Uma vez por lote, dentro de `LoteWorker.run()` em `src/gui/workers.py:135`,
**antes** de instanciar `RpaTotvs`. Se falhar (`ok=False`), o worker
loga `[visão] fallback pra calibração manual salva` e segue usando o
que estiver em `calibracao.campos` — vindo de `calibracao.json`.

### Papel do dialog "Recalibrar (backup)"

O botão em `MainWindow._toolbar_acoes` (label "Recalibrar (backup)"
desde build-70) abre `CalibracaoDialog` só como rede de segurança. Em
máquina padrão o usuário nunca precisa apertar — o auto-detect resolve.
Serve pra:

- Versão do TOTVS com layout customizado que o template matching não
  reconhece.
- DPI/tema exótico que muda proporções da janela.
- Debug: forçar posições conhecidas quando o auto-detect está errando
  silenciosamente.

### Contrato importante

- **Auto-detect nunca falha silenciosamente pro usuário**: sempre loga
  `[visão] <mensagem>` no console/log_file. Se você mexer em
  `visao_totvs.py`, preserve essa contract.
- **`calibracao.campos` é escrito em memória, não em disco** pelo
  auto-detect. Nunca chame `calib_store.salvar(calibracao)` a partir
  do `visao_totvs.py` — ia sobrescrever o fallback do usuário.
- **`CAMPOS_OPCIONAIS`** em `src/core/calibracao.py` define quais campos
  podem faltar sem o lote quebrar. Auto-detect que só acha campos
  obrigatórios ainda é `ok=True`.

---

## 4c. Auto-posicionamento e HUD (build-71)

Resolve o problema clássico de single-monitor: se a MainWindow está
maximizada e o operador clica "Executar", ela cobre o TOTVS — o RPA
não consegue nem enxergar a janela alvo.

### Regra de decisão (em `_executar()`)

Antes de instanciar o `LoteWorker`, chama `_preparar_janela_para_execucao()`:

1. `QGuiApplication.screens()` → conta monitores.
2. **1 monitor** → devolve `availableGeometry()` da tela. Caller
   minimiza (`self.showMinimized()`) e instancia `HudExecucao`,
   posicionando-o no canto superior direito.
3. **2+ monitores** → tenta achar a janela do TOTVS
   (`_encontrar_totvs_geometry()` via `EnumWindows` + `GetWindowRect`)
   e verifica qual monitor a contém. Se a MainWindow está na
   **mesma tela** do TOTVS, move-a pra outra e re-maximiza. Se está
   noutra tela, nada muda. Devolve `None` (sem HUD).

Em ambos os casos guarda `_estado_pre_lote` (`maximized`, `geometry`)
pra restaurar depois via `_restaurar_janela_pos_lote()`.

### O HUD (`src/gui/hud_execucao.py`)

Widget top-level (parent `None`, senão herdaria o estado minimizado da
MainWindow). Flags: `Qt.Tool | FramelessWindowHint | WindowStaysOnTopHint`.
Tamanho fixo 380×132 no modo normal, 380×232 com painel de confirmação.

Sinais espelham os do `LoteWorker`:
- `parar_clicado` → conectado ao `_cancelar()` da MainWindow.
- `confirmacao_respondida(bool)` → chamado quando o operador aperta
  Próximo/Parar no painel de confirmação manual. MainWindow encaminha
  pro `worker.responder_confirmacao(prosseguir)`.

Métodos públicos:
- `iniciar(total, geo_tela)` — abre o HUD posicionado
- `on_progresso(i, total, msg)` — atualiza barra e label
- `pedir_confirmacao_manual(index, resumo)` — só chamado se o
  checkbox "Não apertar '+' automaticamente" estiver marcado.
  Cresce o HUD e mostra painel Prosseguir/Parar.
- `finalizar(sucessos, falhas)` — mostra resumo e auto-fecha em 3s.

### Sobre a confirmação manual

Duplicidade de `Nro. Documento` NÃO precisa de HUD: já é resolvida
automaticamente desde o build-32 (snapshot-diff → OK → novo número
aleatório, até 10 tentativas). A confirmação manual só aparece quando
o operador ativou explicitamente "Não apertar '+' automaticamente"
(modo revisão manual), e nesse caso — em mono-monitor — vai pro HUD;
em multi-monitor vai pra QMessageBox normal.

### Contratos importantes

- **HUD é top-level sem parent** — se der `HudExecucao(self)` como
  parent, o Qt propaga o estado minimizado da MainWindow pro HUD e
  ele some junto com ela. Quebra tudo.
- **`_estado_pre_lote` guarda estado ANTES de qualquer mudança** —
  mesmo em multi-monitor (por causa da possível movimentação entre
  telas). Nunca sobrescrever no meio do lote.
- **HUD auto-fecha em 3s após finalizar** — MainWindow nunca deve
  chamar `hud.close()` diretamente após um lote normal, só usar
  `_encerrar_hud()` que aciona `finalizar()`.
- **No shutdown do app** (`_encerrar_threads`), o HUD é fechado
  explicitamente — como é janela top-level separada, não fecharia
  sozinho quando a MainWindow fechasse.

---

## 5. Empacotamento Nuitka

Ver comentários em `build/build.py` — mas o essencial:

- **`--standalone`** (pasta portátil), nunca `--onefile` (unpack em
  `%TEMP%` dispara AV).
- **`--windows-console-mode=attach`** — sem console em duplo clique, mas
  se rodar do CMD, saída vai pro terminal.
- **`--force-stdout-spec=%TEMP%/...`** — sem isso, alguma lib escrevendo
  em stdout durante o boot em modo GUI causa `STATUS_FATAL_APP_EXIT`
  (`0x40000015`).
- **`--file-version=X.Y.Z.0`** — bumpar sempre que trocar o ícone. É a
  única forma de forçar o Explorer a invalidar o cache de ícone antigo.
- **`--lto=no`** — LTO custa 20+ min extra e não muda anti-AV.
- **`--nofollow-import-to=tkinter,unittest,pydoc,doctest`** — corta peso
  de subpacotes stdlib que não usamos.

Após Nuitka, o script renomeia `dist/launcher.dist/` → `dist/LancamentoAutomatico.dist/`
e copia `config/mapeamento.json` pro root da pasta portátil (edição do
usuário sem descer em subpasta).

---

## 6. Changelog resumido de builds

Só os builds com mudança arquitetural relevante. Detalhes em `git log`.

| Build | O que mudou | Onde |
| ----- | ----------- | ---- |
| 33 | Calibração com scroll + auto-detect da janela | `calibracao_dialog.py` |
| 34-35 | Redesign visual (paleta corporativa dark, KPIs) | `theme.py`, `main_window.py` |
| 36-39 | Visão automática (sem calibração manual) | `visao_totvs.py` |
| 40 | Delays enxutos + CapsLock off | `rpa_totvs.py` |
| 41-43 | De-para editável na UI + Gemini com catálogo | `depara_dialog.py`, `gemini_client.py` |
| 44-48 | Branding Economart + redesign dashboard | `theme.py`, assets |
| 49 | Fix crítico: END false positive via `restype=c_short` | `rpa_totvs.py` |
| 50 | **Auto-update Opção D — completa** | `updater.py`, `launcher.py` |
| 51 | Workflow: `permissions: contents: write` (fix 403) | `.github/workflows/build-exe.yml` |
| 53 | Update obrigatório + auto-restart pós-apply | `launcher.py`, `main_window.py` |
| 54 | Shutdown limpo (não segura desligamento do Windows) | `main_window.py`, `workers.py` |
| 55 | Updater: asset com nome fixo + escolha do mais novo | `updater.py`, workflow |
| 56 | Updater: retry + indicador visual de falha | `updater_bar.py` |
| 57 | Single-instance mutex + splash informativo no apply | `launcher.py` |
| 58 | Fim do "Verificando…" travado — thread + watchdog 22s | `main_window.py` |
| 60 | Auto-check no boot com retry 4→30→60→120s | `main_window.py` |
| 62 | Splash de update com % e ETA | `launcher.py` |
| 63 | Nav lateral: dialogs não mudam active state; X removido do updater | `main_window.py`, `updater_bar.py` |
| 64 | **Rebrand Auto Conferi + paleta índigo/teal** | tudo |
| 65 | Logo próprio + sidebar 184 + single-screen | `assets/branding/`, `main_window.py` |
| 66 | Splash de boot IMEDIATO (reordena imports em main.py) | `main.py` |
| 67 | File dialog nativo + drag-and-drop + fix data cortando + bump ícone | `main_window.py`, `build.py` |
| 68 | **Fix race condition HTTP 404 no auto-update** (workflow + updater) | workflow, `updater.py` |
| 69 | Docs completas: README + ARCHITECTURE + DECISIONS | `*.md` |
| 70 | UX + docs: deixa claro que auto-detect visual é padrão (botão "Recalibrar (backup)", status label, seção 4b) | `main_window.py`, `README.md`, `ARCHITECTURE.md` |
| 71 | Boot maximizado + HUD flutuante em mono-monitor; auto-move MainWindow pra tela sem TOTVS em multi-monitor | `main.py`, `main_window.py`, `hud_execucao.py` (novo) |
| 72 | Accent trocado pra petróleo `#0E4C6E` (não-Tailwind); border-radius 12→6→4 pra sair do "vibe SaaS 2024" | `theme.py`, `hud_execucao.py` |
| 73 | Sai do azul: dark = verde-fisco `#15803D` + âmbar-carimbo; light = azul-marinho SAP `#1E3A5F` + bordô. Duas identidades intencionais por tema. | `theme.py`, `main_window.py`, `hud_execucao.py`, `splash.py` |

---

## 7. Gotchas conhecidos

Coisas que vão pegar contribuidor novo (humano ou IA) de surpresa:

1. **`sys.argv[0]` no exe compilado** aponta pro `.exe`, não pro
   `launcher.py`. Usar `sys.executable` OU `Path(sys.argv[0]).resolve()`
   pra achar a pasta do install. `Path(__file__)` **não** funciona no
   bundle Nuitka.
2. **Renomear o `.exe` rodando** é permitido no Windows (mas não deletar).
   `launcher._aplicar_pendente` explora isso pra fazer swap in-place.
3. **`ctypes.GetAsyncKeyState`** sem `restype = c_short` retorna
   `c_int` com lixo nos bits altos — o teste `& 0x8000` dispara falso
   positivo. Corrigido no build-49; **nunca remover** o `restype`.
4. **Cache de ícones do Windows** é agressivo. Bumpar `--file-version`
   no `build.py` é a única forma confiável de forçar refresh.
5. **`shutil.rmtree` em `_next/`** com arquivo ainda locked → falha
   silenciosa. Sempre passar `ignore_errors=True`, e checar RETRY no
   próximo boot (READY já removido, mas arquivos podem sobrar).
6. **QThread + os._exit()**: se você mata o processo enquanto uma
   QThread tá rodando, Qt loga "QThread: Destroyed while thread is
   still running". Não é fatal, mas é feio. Ver `main_window._encerrar_threads`
   pro shutdown limpo (chamado via `app.aboutToQuit`).
7. **Rate limit da API do GitHub**: sem token, 60 req/h por IP.
   Rede corporativa compartilhada pode estourar. `updater.check()` trata
   403 como "sem update" (não erro fatal).
8. **Não use `sleep` em thread principal do Qt** — congela a UI. Ver
   `_check_atualizacao_boot` no `main_window.py` pro padrão de retry
   com `QTimer.singleShot`.

---

## 8. Como uma IA pega o projeto do zero

Ordem recomendada de leitura:

1. `README.md` — o quê e por quê.
2. **Este arquivo** — os contratos internos.
3. `DECISIONS.md` — decisões com contexto histórico.
4. `src/main.py` (< 150 linhas) — boot do app.
5. `launcher.py` (< 500 linhas) — o resto do boot.
6. `src/core/updater.py` — se for mexer em update.
7. `src/gui/main_window.py` — se for mexer em UI.

Antes de push:
- Rodar `python -c "import ast; ast.parse(open('src/main.py').read())"`
  em cada arquivo modificado (o CI não vai te pegar problemas de
  sintaxe rápido).
- Bumpar `BUILD_MARKER` em `src/main.py`.
- Commit em português BR.
