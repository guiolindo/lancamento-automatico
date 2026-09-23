# Changelog

Histórico de builds do **Auto Conferi**. Cada entrada corresponde a um
`BUILD_MARKER` em `src/main.py` e a um commit em `main`.

Formato: `## build-N — título` seguido de bullets curtos. Do mais novo
para o mais antigo.

## build-121 — OTIMO: validação do CNPJ tomador em 3 níveis

Fecha o gap deixado pelo build-120. Antes: OTIMO validava só o
prestador (que a nota veio do Ótimo mesmo) e sempre lançava na
Contagem, mesmo que a nota fosse endereçada a outra filial ou a uma
empresa fora do grupo por engano. Agora:

- **CNPJ tomador bate exato com filial cadastrada** → OK, lança na
  filial resolvida (não mais Contagem à força).
- **Só a raiz (8 primeiros dígitos) bate** → IGNORADA, motivo "Filial
  não cadastrada" — operador cadastra a filial em `cnpjs_filiais.json`
  e reprocessa.
- **Nem a raiz bate** → IGNORADA, motivo "CNPJ de outra empresa" —
  nota chegou por engano.
- **CNPJ tomador nem veio na extração** → IGNORADA — não dá pra
  validar destino.

Custo de token no Gemini: zero. `_PROMPT_NFSE` já pedia `cnpj_tomador`
desde build-107 (Pluxee).

Ativado via `validar_cnpj_tomador: true` no template. Lógica pura em
`src/core/cnpj_utils.py` (9 unit tests cobrindo os 4 resultados).
Total da suite: 31 passing.

## build-120 — OTIMO: CNPJ preenchido

Preenche `cnpj_esperado` do template OTIMO em `mapeamento_orcamento.json`
(`10426715000164`). Ao lançar um lote do Ótimo, o app rejeita PDFs
que sejam de outro fornecedor — mesma proteção do PLUXEE (build-107).

## build-119 — docs split + suite de tests

Inspirado no repo irmão `guiolindo/Notas-despesas` (o backend web que
alimenta a fila do Auto Conferi). Sem mudança de comportamento no app.

- `docs/` com 4 arquivos temáticos: `getting-started.md`,
  `operations.md`, `faq.md`, `testing.md`. Cada um resolve um perfil
  ("nunca rodou", "produção quebrou", "dúvida do operador", "vai mexer
  no código"). ARCHITECTURE.md continua sendo o mergulho profundo.
- `CREDITS.md` com todas as libs, licenças e a atribuição do TOTVS /
  Consinco como marca registrada da TOTVS S.A.
- `requirements-dev.txt` separado (ruff pinado + pytest + pytest-cov).
- `tests/` com 22 unit tests em 3 arquivos: `test_models.py` (dataclasses
  + retrocompat do FGTS_CONSIG), `test_mapping.py` (carrega
  mapeamento.json real do repo + fuzzy exato/alias/acento/case), e
  `test_keyboard.py` (regressão do bug de acento do build-105).
  `conftest.py` stuba PySide6/pyautogui/pywinauto pra rodar em Linux.
- `.github/workflows/lint.yml` ganha o job `pytest` (~1s).
- `keyboard_utils.py`: setup Win32 guardado por `hasattr(ctypes, "windll")`.
  O runtime real continua 100% Windows, mas o módulo importa limpo em
  Linux/macOS pra os unit tests rodarem no CI.
- README ganha sumário no topo e um bloco "Documentação técnica completa"
  no rodapé com ponteiros por perfil.

## build-118 — housekeeping (LICENSE, CHANGELOG, CI de lint, templates)

- Adicionado `LICENSE` (uso interno restrito).
- Adicionado `CHANGELOG.md` com histórico consolidado dos builds 98–117.
- Adicionado workflow `.github/workflows/lint.yml` (ruff) — roda em todo
  push e PR. Separado do `build-exe.yml` pra não gastar 10 min por lint.
- Adicionado `.github/pull_request_template.md` + templates de issue
  (bug / feature).
- README com badges (build, versão, licença) e nota do módulo padronizada
  ("Operador Financeiro" no lugar de "Novo lote", alinhando com build-117).

## build-117 — UX: vocabulário do TOTVS

- Sidebar e breadcrumb: **"Operador Financeiro"** no lugar de "Novo lote"
  (nome real da tela do TOTVS).
- Cabeçalhos simétricos entre os 2 módulos: título + subtítulo antes do
  stepper.
- Corrigida narrativa da calibração (dizia "auto ativo, manual como
  backup" — desde build-100 é o contrário: manual PREVALECE).
- Botão "Recalibrar (backup)" → "Recalibrar" com tooltip honesto.
- Botão "Atualizar" → "Atualizar app".

## build-116 — docs sync

- README/ARCHITECTURE/DECISIONS atualizados até build-115. 19 gotchas
  documentadas em ARCHITECTURE, 12 decisões em DECISIONS.

## build-115 — Operador Financeiro: mais 3 delays cortados

- `apos_confirmar` 500ms (era mais); `apos_especie` 150ms; `apos_pessoa`
  200ms. Lote de 30 linhas ficou ~2min mais rápido.

## build-114 — Operador Financeiro: delays enxutos

- Paridade com o Orçamento: default 150ms, apos_click 120ms,
  apos_selectall 100ms, entre_campos 100ms, typewrite 1ms.

## build-113 — imposto FGTS_CONSIG

- Novo tipo de imposto que gera 2 lançamentos por linha (MFGTS + CONSIG),
  cada um com sua espécie, pessoa = código Consinco da própria filial.
- `Imposto` model ganhou `pessoa_por_filial`, `especie_por_coluna`,
  `observacao_por_coluna`.

## build-112 — fix check de rede

- Cabo desligado não bloqueava o app: `USERDNSDOMAIN` fica cacheada no
  logon. Adicionado segundo estágio com `socket.gethostbyname` (timeout
  3s) que valida conectividade real.

## build-111 — fix Contab do Orçamento

- Ordem invertida: **Valor antes da Filial** — o TOTVS Consinco rola a
  tabela horizontalmente ao ganhar foco de edição, então preencher
  Valor por último jogava "REGULARBA" na coluna Percentual.
- Adicionado `contab_linha2_filial` (Pluxee troca filial nas 2 linhas).

## build-110 — Orçamento: painel Atividade + menu contextual

- Delays enxutos no Orçamento; +1s entre Autorizar e próxima nota.
- Painel de Atividade (log ao vivo) igual ao do Operador Financeiro.
- Menu contextual: editar número/valor/data/filial/caneta, marcar
  pendente, remover linha.

## build-109 — fuzzy caneta desambigua LOJA vs CD

- "CD Feira de Santana" caía como "Feira de Santana" (loja) por 1 ponto
  no WRatio. Fix: rerank pós-fuzzy com boost +15 se prefixo CD bate,
  penalty −20 se cruza.

## build-108 — fix access violation no clipboard

- `keyboard_utils.py` chamava Win32 sem `argtypes`/`restype` → HANDLE
  truncado em Win x64 → memória inválida. Configurados types nas 8 APIs.
- Aliases pro fuzzy (Linha Verde → Serra Verde, LEM → Luis Eduardo).

## build-107 — Pluxee vale combustível

- NFS-e Pluxee (vale-combustível), multi-página.
- Valida CNPJ do prestador contra template.
- Extrai anotação a caneta via Gemini Vision + fuzzy match com aliases
  pra resolver filial de destino.

## build-106 — docs sync + Sobre reescrito

- README/ARCHITECTURE/DECISIONS até build-105.
- Diálogo "Sobre" reescrito, sem jargão genérico de I.A.

## build-105 — fix acentos + UI enxuta

- "Elétrica" virava "eltrica": `pyautogui.typewrite` ignora silenciosamente
  non-ASCII. Fix: `keyboard_utils.digitar_texto` usa clipboard + Ctrl+V
  quando o texto tem non-ASCII.
- Textos genéricos com "cara de I.A." removidos da UI.

## build-104 — Orçamento: offsets visão corrigidos + multi-monitor

- Offsets da visão computacional reescritos usando calibração real que o
  usuário mandou.
- Suporte a multi-monitor: janela procura o TOTVS onde ele estiver.

## build-103 — fix duplicidade Orçamento

- Detecta duplicidade LOGO após digitar Nota Fiscal (aba Nota), antes de
  perder tempo preenchendo Financeiro/Contab.

## build-102 — docs (Orçamento + DAE)

- Documentado módulo Orçamento, DAE Bahia e gotchas novas.

## build-101 — DAE Bahia (ICMS energia elétrica)

- Regime normal + adicional Fundo de Pobreza (2 lançamentos).
- Resolve empresa por CNPJ, identifica tipo automaticamente.

## build-100 — manual PREVALECE sobre visão automática

- Ao calibrar manualmente, a config salva ganha da auto-detecção da
  visão. Antes a visão sobrescrevia a cada boot, frustrando o operador.

## build-99 — Orçamento como página integrada

- Deixa de ser diálogo modal. QStackedWidget navegável na sidebar,
  paridade UX com o Operador Financeiro.

## build-98 — fix ordem do fluxo Orçamento

- `+` e `Autorizar` UMA vez, no final, depois de todas as abas — não a
  cada aba.
