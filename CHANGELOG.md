# Changelog

Histórico de builds do **Auto Conferi**. Cada entrada corresponde a um
`BUILD_MARKER` em `src/main.py` e a um commit em `main`.

Formato: `## build-N — título` seguido de bullets curtos. Do mais novo
para o mais antigo.

## build-125 — OTIMO revisão: coluna Emissor + reprocessar de verdade

Dois bugs de UX que o operador reportou depois do build-122:

**1. Tabela do OTIMO sem info suficiente pra conferir.**
Desde o build-121 o roteamento por CNPJ tomador decide pra qual filial
a nota vai. Mas a tabela do OTIMO (COLS_NFSE) só mostrava
`#, Pág., Número NF, Data Emissão, Valor, Status` — o operador não via
PRA QUEM cada nota estava indo. Um "Status: OK" na linha não dizia
nada sobre o destino. Agora tem coluna **"Emissor"** entre Data e Valor,
mostrando `"codigo — nome"` da filial resolvida (ou `"?"` quando não
bateu — vira revisão manual óbvia).

**2. "Marcar como pendente (reprocessar)" não funcionava de verdade.**
Só resetava `status = PENDENTE`. Se a nota tinha sido barrada por
"filial não cadastrada" (RAIZ_GRUPO do build-121) e o operador
cadastrasse a filial nova em `cnpjs_filiais.json` entre tanto, o dict
em memória continuava velho e a linha continuava sem filial resolvida
— reprocessar ficava sem efeito prático. Agora:
- Recarrega `cnpjs_filiais.json` do disco.
- Re-roda a resolução da nota (`_rerresolver_nota`): filial de emissão
  pelo CNPJ tomador, filial da caneta pelo rabisco, filial DAE pelo
  CNPJ do próprio DAE.
- Reaplica a validação do tomador — se ainda não resolveu, volta pra
  IGNORADO com o motivo atualizado (não fica "meio-pendente" mentindo
  que vai lançar).

**Adicional:**
- Menu contextual do OTIMO ganhou **"Editar filial de emissão…"** —
  antes só tinha pro DAE. Ajusta `filial_emissao_codigo`/`filial_emissao_nome`
  quando o auto-resolve falha e o operador sabe qual é a filial certa.
- `_executar_lote` do OTIMO agora exige `filial_emissao_codigo` na
  lista de "pendentes" quando o template pede `validar_cnpj_tomador`.
  Sem isso, o RPA cairia no fallback `empresa_codigo: "6"` (Contagem)
  silenciosamente pra qualquer linha sem tomador resolvido — combinação
  que voltaria a lançar em Contagem à força, defeat the whole build-121.

## build-124 — Segurança: chave em header + logger redator + erros PT-BR

Log de produção mostrou dois problemas convergentes:

1. **Vazamento da chave**: `requests.exceptions.SSLError` colocava a
   URL completa no `str(exc)`, incluindo `?key=<CHAVE>`. Quando o
   `log.exception("Falha na extração")` rodava, a chave ia parar em
   `logs/lancamento.log` em plaintext. O caso reportado teve a chave
   aparecendo duas vezes num arquivo de log.
2. **UX ruim de erro**: mensagens em inglês + JSON + traceback Python
   apareciam pro operador via `f"{type(e).__name__}: {e}"`. Um operador
   leigo não sabe o que é "SSLError certificate verify failed"; um
   traceback intimida.

Correções em 3 camadas:

- **Chave em header**: `gemini_client._post_gemini()` centraliza
  todos os 3 POSTs pro Gemini e passa a chave em `x-goog-api-key`, não
  em `params={"key": ...}`. URL nunca mais carrega a chave, então
  tracebacks do `requests` não vazam.
- **Logger redator**: `logger._RedactApiKeys` (Filter) +
  `_RedactingFormatter` rodam sobre TODA mensagem/traceback logada,
  redigindo `?key=…`, `&api-key=…`, `x-goog-api-key: …`, e chaves
  soltas com prefixos Google (`AIza…`, `AQ.Ab8…`). Retroativo:
  protege até código antigo que ainda logue URL manual.
- **Erros amigáveis**: `GeminiError` (subclasse de `RuntimeError` pra
  compat) carrega mensagem já em PT-BR — `_mensagem_para_http()` e
  `_mensagem_para_exception()` traduzem HTTP 400/401/403/429/5xx e
  exceptions do `requests` (SSLError, ConnectTimeout, ReadTimeout,
  ConnectionError) pra frases claras: **"Chave inválida"**, **"Limite
  atingido — espera 1 min"**, **"Antivírus interceptando — chama o
  TI"**, etc. Nunca expõe `str(exc)` original ao operador — traceback
  detalhado fica só no log (agora redigido).

`workers.py` e `orcamento_dialog.py` emitem `str(GeminiError)` puro
pra UI. Erro fora dos padrões vira "Falha inesperada — chama o
suporte".

Suite pytest: 31 → **51 testes** (+13 tradutores Gemini, +7 redação
logger). `docs/operations.md` e `docs/faq.md` atualizados com a tabela
dos erros e a nota de segurança.

## build-123 — Orçamento: delays exclusivos para + e Autorizar

Módulo Orçamento faz transação real (natureza despesa, plano de contas
como subforms internos) — precisa de mais tempo em cada click
estrutural. Antes reutilizava as chaves do Operador Financeiro, o que
forçava um empate impossível: subir os delays quebrava a velocidade do
Operador (que roda bem em 100-200ms), abaixar quebrava o Orçamento.

Chaves novas, exclusivas do Orçamento (defaults 4000 ms cada):

- `orcamento_apos_plus_ms` — após clicar "+" (absorve a janela de
  detecção de popup de duplicidade).
- `orcamento_apos_autorizar_ms` — após clicar "Autorizar".

Removidos os delays redundantes que se somavam (`apos_confirmar_ms`
antes do Autorizar e `entre_notas_ms` depois). Fluxo agora é: **click +
→ 4s → popup check → click Autorizar → 4s → próxima nota**.

`delays_version` bumpado 2 → 3 — usuário existente pega os novos
defaults automaticamente via `_migrar_delays()` no próximo boot.

## build-122 — OTIMO Contab: troca filial das 2 linhas pro CNPJ tomador

Completa o roteamento por tomador do build-121. Antes as duas linhas
da Contab ficavam na filial default (fixa em Contagem no modo simples
`replicar_valor_nas_linhas: 2`). Agora usam o modo estruturado
`linha1`+`linha2`, ambas com `trocar_filial_para: "filial_emissao"` —
a mesma filial resolvida pelo CNPJ tomador é aplicada nas duas linhas
da contabilização.

Zero código novo — só troca no template `mapeamento_orcamento.json`.
A mecânica `trocar_filial_para` já existia desde o build-107 (PLUXEE).

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
