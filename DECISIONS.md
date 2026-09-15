# Decisões — log histórico

Ficam registradas aqui as decisões que exigiram discussão: contexto, opções
consideradas, o que foi escolhido, e por quê. Serve pra ninguém (humano
ou IA) precisar re-derivar o motivo quando bater dúvida meses depois.

Ordenado do mais antigo pro mais novo.

---

## 1. Auto-update do .exe ✅ IMPLEMENTADO (Opção D, build-50)

**Contexto**: projeto rodando como Shadow IT (sem sanção da TI da empresa,
sem budget pra servidor próprio ou certificado code-signing). Precisa
atualizar o `.exe` portátil sem drama de antivírus corporativo e sem pedir
pro operador baixar/descompactar/mover pasta.

**Opções descartadas:**

- **A (só notificação)**: app avisa, operador substitui manualmente.
  Muito trabalhoso.
- **B (auto-update tipo Squirrel)**: baixa + mata o app + roda
  `updater.exe` + reabre. Padrão clássico de malware, AV corporativo
  barra sem certificado assinado (R$400-800/ano).
- **C (servidor próprio de release)**: precisa VPS mensal e alguém pra
  manter. Sem budget em Shadow IT.

**Escolhida — D: update DIFERIDO** (implementada em `src/core/updater.py`
+ `launcher.py`):

- App verifica GitHub Releases na abertura (repo público).
- Nova versão? Download em background.
- Extrai o zip em `LancamentoAutomatico.dist/_next/` (pasta local,
  **não** em `%TEMP%`, o que evita signature clássica de malware).
- Marker `_next/READY` só é escrito depois que TUDO deu certo (SHA256
  batendo, extração ok).
- Usuário fecha o app quando quiser.
- Próxima abertura: `launcher.py` detecta `_next/READY`, renomeia `.exe`
  atual pra `.exe.old`, copia o novo por cima, apaga `_next/`, dispara
  `subprocess.Popen` do exe novo e faz `os._exit(0)`.

**Por que passa em AV corporativo:**
- Nunca mata a si mesmo pra reabrir (padrão que AV odeia).
- Nenhum binário externo (`updater.exe`) roda pra fazer replace —
  é o próprio `launcher.py` que já rodou antes.
- Só faz HTTP GET pra `github.com`.
- Escreve arquivos só na pasta local do app.
- Sem `%TEMP%`, sem registry, sem serviço, sem elevação.

**Integridade sem certificado pago:**
- Body da release inclui `SHA256=<hex>` do zip.
- `updater.py` confere antes de aplicar; se não bater, aborta e limpa.

Ver [ARCHITECTURE.md](ARCHITECTURE.md) → "Auto-update diferido" para
diagramas e contratos.

---

## 2. Rebrand: Economart → Auto Conferi ✅ (build-64)

**Contexto**: identidade inicial usava logo e paleta da Economart (empresa
do usuário), mas o app é um produto pessoal do Guilherme, não da empresa.
Ficaria estranho distribuir para outros clientes/uso pessoal futuro com
marca de uma companhia específica.

**Escolhida:** identidade própria "Auto Conferi".
- **Paleta**: índigo `#3B82F6` (accent) + teal `#14B8A6` (brand).
  Substituem o laranja Economart. `BRAND_ORANGE`/`BRAND_BLUE` mantidos
  como aliases apontando pros novos códigos (compat com código legado).
- **Logo**: gerado programaticamente via PIL — 3 chevrons ascendentes
  (2 índigo + 1 teal). 8 tamanhos em `src/assets/branding/`.
- **`.exe`**: `--file-version=0.2.0.0` no build.py (build-67) —
  o bump força o Windows Explorer a invalidar o cache de ícones antigo.

**Gotcha do rebrand:** o Explorer do Windows segura ícones de `.exe`
antigos com muita força. Se você renomear/editar o `.ico` sem bumpar
`--file-version`, o cache continua exibindo o ícone velho por dias.
Documentar no header do `build.py`.

---

## 3. File dialog: nativo vs Qt custom ✅ nativo (build-67)

**Sintoma reportado**: seletor de arquivos travava a UI por 15s (às
vezes 50s) ao abrir/selecionar. Culpa de shell extensions do Windows
(OneDrive, AV corporativo, verificadores de contexto) que rodam
sync no thread do dialog nativo.

**Tentativa 1 (build 64)**: `QFileDialog.DontUseNativeDialog` — Qt
renderiza o seletor próprio. Resolveu o freeze do OneDrive **mas**:
- Interface em inglês (Qt não localizou pro PT-BR).
- Sem preview de imagens.
- Sem ordenação por data.
- Ainda travava ~50s ao selecionar (o problema não era o dialog em si,
  era o handler pós-seleção).

**Escolhida (build 67)**: reverter pro dialog nativo E adicionar
**drag-and-drop** (`.pdf/.png/.jpg/.jpeg/.webp`) como caminho alternativo.
Usuário arrasta o arquivo direto do Explorer, evita abrir o dialog
travado.

---

## 4. Ordem no workflow: race condition HTTP 404 ✅ corrigido (build-68)

**Sintoma reportado pelo usuário**: barra vermelha "GitHub retornou HTTP
404" tentando baixar build-67, mesmo com o release publicado correto.

**Causa raiz**: o workflow (`.github/workflows/build-exe.yml`) tinha um
passo "Limpar assets antigos" que rodava **antes** do upload do novo zip.
Isso abria uma janela de ~5-10s onde a release ficava sem asset.
Clientes que tinham feito `check()` logo antes tinham a URL do asset
antigo em mãos, e ao tentar baixar recebiam 404.

**Escolhida — correção em duas camadas:**

1. **Workflow**: publicar primeiro (`softprops/action-gh-release@v2`
   sobrescreve o asset de mesmo nome in-place, sem janela vazia) e
   **depois** limpar assets restantes, preservando o atual pelo nome
   `$env:ZIP_NAME`.
2. **Updater** (`src/core/updater.py`): se o download retornar 404,
   refazer `check()` uma vez pra pegar a URL nova do asset e retentar.
   Cobre o caso em que o cliente já tinha uma URL velha em memória há
   minutos (ex.: `_check_atualizacao_boot` com retry 4s→30s→60s→120s).

---

## 5. Módulo Orçamento: dialog modal vs página integrada ✅ página (build-99)

**Contexto**: novo módulo (build-95) implementado inicialmente como
`QDialog` modal — clicar em "Orçamento" na sidebar abria uma janela
Qt separada. Fácil de implementar, mas ficava "a nada com nada": sem
topbar, sem breadcrumb, sem log integrado, cada tema/tamanho tinha
que ser resetado, e visualmente parecia outra aplicação.

**Opções consideradas:**

- **Manter como dialog modal** (status quo, simples).
- **Página real embarcada** via `QStackedWidget`, sidebar troca de
  índice como qualquer nav.

**Escolhida**: página real. `OrcamentoDialog` virou
`OrcamentoPage(QWidget)`. O shell do `main_window` ganhou um
`QStackedWidget` (index 0 = dashboard, index 1 = orçamento).
`_trocar_secao` só muda `setCurrentIndex` em vez de `exec()`. Alias
`OrcamentoDialog = OrcamentoPage` mantido pra backcompat de código
externo que possa ter importado o nome antigo.

Mapeamento, Config e Sobre continuam como dialog modal — decisão
histórica de custo/benefício (são acesso pontual, não uso contínuo
como o Orçamento).

---

## 6. Prioridade: calibração manual > visão automática ✅ manual ganha (build-100)

**Contexto**: bug em prod reportado como "botão Empresa clica
totalmente fora, e nem recalibrar resolve". Investigação mostrou que
tanto o Novo Lote quanto o Orçamento faziam
`preencher_calibracao_automatica(self.calibracao)` no INÍCIO de cada
lote — a função mutava `calibracao.campos` in-place, sobrescrevendo o
que o operador tinha calibrado manualmente. Se os offsets calculados
por template matching não batiam exatamente com a resolução real do
TOTVS do usuário, cliques caíam fora — E como sobrescrevia toda vez,
recalibrar era inútil (o próximo lote apagava).

**Opções:**

- **A**: adicionar setting "modo visão automática" ligado/desligado.
- **B**: se calibração manual está completa, respeita ela e pula a
  visão. Visão vira fallback quando não há calib salva.

**Escolhida — B**: menos configuração pro usuário decidir, mais
intuitivo (quem calibrou espera que a calibração seja usada), zero UI
nova. Aplicado em 3 lugares:

- `workers.py::LoteOrcamentoWorker.run`
- `workers.py::LoteWorker.run` (Novo Lote — mesmo bug potencial)
- `rpa_orcamento.py::_clicar_popup_via_visao` (popups em runtime:
  calibração manual do botão do popup > visão em runtime)

**Consequência**: o log agora mostra explicitamente a decisão —
`[calibração] manual completa — usando ela (visão automática ignorada)`
vs `[visão] Visão OK — confiança 87%, 23 campos.` — facilita o
diagnóstico se algo der errado em prod.

---

## 7. Resolver filial por CNPJ (DAE Bahia) ✅ tabela separada (build-101)

**Contexto**: DAE (Documento de Arrecadação Estadual) da Bahia é
endereçado por CNPJ — cada guia tem `CNPJ / CPF: 28.548.486/0010-07`
que identifica a filial destinatária. Diferente do módulo Novo Lote
(onde a filial vem do nome no relatório e resolve via fuzzy match no
`mapeamento.json`) e do template OTIMO original do Orçamento (onde a
filial é FIXA no template = "empresa_codigo: 6"), aqui cada documento
do lote vai pra uma filial diferente.

**Opções:**

- **A**: espalhar os 31 CNPJs dentro do `mapeamento_orcamento.json`
  no template DAE (JSON grande, alinhamento manual entre 2 fontes).
- **B**: campo `aliases_cnpj` nas filiais do `mapeamento.json`
  original — o loader `mapping.py` acha por CNPJ também.
- **C**: novo arquivo `cnpjs_filiais.json` dedicado. O template DAE
  só marca `empresa_por_cnpj: true` e o dialog resolve o CNPJ
  quando o Gemini extrai.

**Escolhida — C**: separa preocupações (`mapeamento.json` é sobre
apelidos de filiais em relatórios de folha; `cnpjs_filiais.json` é
sobre identificação fiscal); adicionar filial nova = editar um JSON
enxuto de 40 linhas; e futuros documentos que resolvem por CNPJ
reusam a mesma tabela.

**Gotcha**: se o CNPJ vier "quase certo" do PDF (Gemini errou 1
dígito de OCR), o lookup falha silenciosamente — a linha vai marcar
"Revisar" na grid. **NÃO tentamos fuzzy match** de CNPJ: é
documento fiscal, um dígito errado é filial errada, e um lançamento
errado é problema real. Melhor o usuário conferir manualmente.

---

## 8. Digitação de acentos: clipboard + Ctrl+V ✅ (build-105)

**Contexto**: bug em prod — "ao lançar notas que têm acentos, ele
simplesmente ignora a letra com acento. Elétrica vira eltrica." Causa:
`pyautogui.typewrite` só sabe digitar ASCII básico (envia virtual keys
do teclado US-ANSI). Qualquer char fora disso — é, ê, ç, á, à, ó etc.
— é **ignorado silenciosamente**, sem warning, sem erro.

**Opções consideradas:**

- **A**: substituir `pyautogui.typewrite` por `keyboard.write(str)` da
  lib `keyboard` — suporta unicode via WM_UNICHAR. Mas puxa dep nova,
  e ela é famosa por trigger de AV corporativo (ela usa
  `SetWindowsHookEx(WH_KEYBOARD_LL)` — hook de teclado global, padrão
  clássico de keylogger — build-86 documenta que a gente EVITA esse
  padrão).
- **B**: `pyperclip.copy(texto)` + `pyautogui.hotkey('ctrl','v')`.
  Simples, mas dep nova (só clipboard, ~200 linhas).
- **C**: clipboard via ctypes puro (Win32 `OpenClipboard` /
  `SetClipboardData(CF_UNICODETEXT)`) + `pyautogui.hotkey('ctrl','v')`.

**Escolhida — C**. Sem dep nova (o app já tem `ctypes` da stdlib),
sem hook de teclado global (AV concern), e `Ctrl+V` é sequência
mainstream que Zoom/Slack/Chrome mandam o tempo todo — zero AV
flag no perfil heurístico.

**Detalhes de implementação:**

- `src/core/keyboard_utils.py::digitar_texto(texto)` decide por char:
  - `texto.encode("ascii")` sem exceção → `pyautogui.typewrite`
    (rápido, sem tocar clipboard).
  - Erro → caminho clipboard: salva o clipboard atual do usuário
    (`GetClipboardData(CF_UNICODETEXT)`), coloca o texto novo com
    `SetClipboardData(CF_UNICODETEXT)`, manda `Ctrl+V`, sleep 80ms,
    **restaura o clipboard anterior**.
- `OpenClipboard` pode falhar transiente (outro processo — Zoom,
  screenshot — segurou por milissegundos). Retry 5×, 50ms cada,
  antes de desistir.
- Fallback: se o clipboard falhar completamente, cai no typewrite
  puro (perde acento, mas grava o resto — melhor que travar).

Aplicado em `rpa_totvs._preencher` e `rpa_orcamento._preencher` +
`_digitar_multilinha`. Todo lugar novo que precise digitar strings de
template no TOTVS deve usar `digitar_texto` e NUNCA
`pyautogui.typewrite` direto.

---

## Convenções do projeto

Registradas aqui pra IA/contribuidor novo não precisar adivinhar.

- **Idioma**: código, docstrings, comentários, commits e mensagens ao
  usuário — **tudo em português BR**. Só o nome de conceitos técnicos
  universais fica em inglês (ex.: "thread", "mutex", "callback").
- **Comentários**: só quando o "porquê" não é óbvio (workaround, invariante
  escondida, gotcha específica). Nunca explicar o "quê" — o nome
  identificador já faz isso.
- **BUILD_MARKER** (em `src/main.py`): string curta descrevendo a versão.
  **Sempre bumpar** antes de push pra `main` — é ele que o updater
  compara pra decidir se tem versão nova.
- **Nomes de branch**: `claude/<slug>` pra branches feitas por IA.
- **Aliases legados**: `BRAND_ORANGE`/`BRAND_BLUE` em `theme.py` viraram
  aliases pros novos `BRAND_TEAL`/`BRAND_INDIGO` (mantém código
  antigo funcionando; novo código deve usar os novos nomes).
