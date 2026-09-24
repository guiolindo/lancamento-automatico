# Guia pra IA (e humano novo no projeto)

> **Nome:** Auto Conferi (repo `lancamento-automatico`, nome histórico).
> Desktop Windows portátil (Nuitka standalone, sem admin) que automatiza
> lançamento fiscal no TOTVS/Consinco. Dois módulos: **Operador Financeiro**
> (IRRF/INSS/FGTS-Consig) e **Orçamento** (NFS-e de despesa: Ótimo, Pluxee,
> DAE). Gemini extrai PDF → app valida → RPA (pyautogui + pywinauto)
> executa. Rodando em produção na Economart/Multicom.

## Leia isto ANTES de tudo

Este arquivo é o mapa. Ele **não substitui** a documentação profunda —
aponta pra ela. A regra é: **leia só o que a tarefa exige**, não os
130KB de docs.

## Pra fazer X, leia Y

| Tarefa | Leia (nesta ordem) |
|---|---|
| Rodar em dev pela 1ª vez | `docs/getting-started.md` |
| Debugar bug em produção | `docs/operations.md` (tabela de erros) → `docs/faq.md` |
| Adicionar novo imposto (IRRF-like) | `src/config/mapeamento.json` (copia entrada existente) → `src/core/models.py` (`Imposto`) → `ARCHITECTURE.md` §1 |
| Adicionar novo fornecedor Orçamento | `src/config/mapeamento_orcamento.json` → `ARCHITECTURE.md` §4e → template PLUXEE como referência (mais completa) |
| Adicionar/renomear filial | `src/config/cnpjs_filiais.json` (CNPJ é a chave) + `src/config/mapeamento.json` (lista) |
| Mexer no auto-update / launcher | `ARCHITECTURE.md` §2 **inteira** → `launcher.py` → `src/core/updater.py`. NUNCA mexa aqui sem ler §2 — os 3 arquivos conversam por convenções não-explícitas |
| Mexer no RPA (mouse/teclado, delays) | `src/core/rpa_totvs.py` (Operador) ou `src/core/rpa_orcamento.py` (Orçamento) + `docs/faq.md` (delays diferentes por módulo — build-123) |
| Mexer na visão computacional (detecção de campos) | `ARCHITECTURE.md` §4b/§4e.3 → `src/core/visao_totvs.py` / `src/core/visao_orcamento.py` |
| Mexer na UI (main_window, dialogs) | `src/gui/main_window.py` (dashboard/Operador) → `src/gui/orcamento_dialog.py` (Orçamento). Ambos são grandes — use grep primeiro |
| Adicionar teste | `docs/testing.md` → `tests/conftest.py` (stubs de PySide6/pyautogui) |
| Chamar Gemini | `src/core/gemini_client.py` — SEMPRE via `_post_gemini()` (build-124: header em vez de query param, tradução de erro pra PT-BR) |
| Empacotar .exe | `build/build.py` + `ARCHITECTURE.md` §5 |
| Ler um build antigo | `CHANGELOG.md` (build-N título curto) → grep no código pelo número do build |

## Nunca faça isto

- **Não troque Nuitka por PyInstaller.** PyInstaller descompacta Python em `%TEMP%` em runtime, ativa AV corporativo. Nuitka gera binário nativo. Ver `ARCHITECTURE.md` §5.
- **Não use `google-generativeai`.** Foi removido no build-95: gRPC/Cython (cygrpc.pyd) crasha silenciosamente em Nuitka standalone. Usamos `requests` puro pra chamar a REST API.
- **Não use `params={"key": ...}` no `requests.post` do Gemini.** Vaza em traceback de SSLError. Sempre `x-goog-api-key` header via `_post_gemini()`.
- **Não force-push em `main`.** O `.github/workflows/build-exe.yml` publica release a cada push, o updater dos clientes lê essa release. Force-push quebra checkouts em produção.
- **Não commite chaves/segredos** (mesmo já rotadas). GitHub secret-scanning bloqueia; e o padrão fica indexado em forks/caches.
- **Não pinte de "melhorou o código" sem valor pra o operador.** Este é software de produção — cada build vai pra máquina que fatura. Só mexe se tem defeito real ou pedido explícito.
- **Não rewrite história git de commits já em `main`.** Merge conflicts se resolvem com commit novo, não com rebase.
- **Não passe `str(exc)` do `requests` pra o operador.** Usa `GeminiError` + tradutores em `gemini_client.py`.
- **Não `git add -A` sem `git status` antes.** `.env`, chaves, screenshots com dados sensíveis mordem.

## Convenções

**Commits.** Toda mudança bumpa o `BUILD_MARKER` em `src/main.py` (`build-N (descrição curta)`). O commit começa com `build-N: ...`. Termina com o footer de atribuição definido no system prompt (Co-Authored-By + Claude-Session). Ver últimos 5 commits pra referência.

**Idioma.** Todo texto voltado ao usuário (UI, mensagens de erro, comentários explicativos importantes) é PT-BR informal ("tenta de novo", "o operador"). Nomes de variável e código são inglês/PT misto — segue o dialeto do arquivo. Não faz mass-rename.

**Comentários.** Só quando o "porquê" não é óbvio: hidden constraint, workaround pra bug específico, decisão contra-intuitiva. Nunca "esta função retorna X".

**Testes.** `tests/` roda no CI (Ubuntu) — PySide6/pyautogui são stubados por `conftest.py`. Só testa a parte pura. RPA de verdade é validado manualmente na máquina do usuário. Ver `docs/testing.md`.

**BUILD_MARKER format.** Validado pelo CI (`build-\d+`). O texto entre parênteses aparece pro operador em Menu → Sobre — mantém curto e claro.

## Onde as coisas moram (mapa de arquivos)

```
src/
  main.py                    entrypoint + BUILD_MARKER
  core/
    logger.py                logger com filtro anti-vazamento (build-124)
    settings_store.py        settings.json + DPAPI da chave Gemini + migração de delays
    mapping.py               MappingRepository (mapeamento.json + fuzzy match filiais)
    models.py                dataclasses: Filial, Imposto, Lancamento, NotaDespesa, Status*
    cnpj_utils.py            validação CNPJ tomador (3 níveis: exato/raiz/outra empresa)
    keyboard_utils.py        digitação Windows: ASCII → pyautogui, unicode → clipboard+Ctrl+V
    gemini_client.py         REST Gemini (POST via _post_gemini) + tradução de erros PT-BR
    rpa_totvs.py             RPA Operador Financeiro
    rpa_orcamento.py         RPA Orçamento (Nota/Financeiro/Contab)
    visao_totvs.py           visão computacional Operador (auto-detecta 11 campos)
    visao_orcamento.py       visão computacional Orçamento
    updater.py               fala com GitHub Releases (rolling tag `latest`)
  gui/
    main_window.py           janela principal + dashboard Operador Financeiro
    orcamento_dialog.py      OrcamentoPage (embutida no QStackedWidget desde build-99)
    preview_table.py         tabela de revisão do Operador
    workers.py               QThreads (extração + execução de lote)
    splash.py                splash inicial
    calibracao_dialog.py     calibração manual dos campos (backup pra visão)
    depara_dialog.py         editor de mapeamento.json
    setup_dialog.py          primeira configuração (chave Gemini)
    hud_execucao.py          HUD compacto em execução mono-monitor
    theme.py                 QSS (temas escuro/claro)
    icons.py                 ícones SVG inline
  config/
    mapeamento.json          filiais + impostos (Operador Financeiro)
    mapeamento_orcamento.json templates por fornecedor (OTIMO, PLUXEE, DAE_ENERGIA)
    cnpjs_filiais.json       CNPJ → filial (chave de roteamento do Orçamento)
launcher.py                  auto-recovery de boot quebrado + hand-off pra src.main
build/build.py               script Nuitka --standalone
tests/                       unit tests (conftest stuba GUI)
```

## Como o boot funciona (resumo — detalhes em ARCHITECTURE §2)

1. `.exe` inicia com o **launcher** (não `src.main` direto).
2. Launcher checa `_next/READY` → se existe, faz swap atômico e boota versão nova.
3. Launcher checa `boot_ok.marker` do boot anterior → se ausente, aciona auto-recovery.
4. Launcher chama `src.main.main()`.
5. `src.main` mostra splash, carrega deps pesadas (Qt), instancia MainWindow.
6. Escreve `boot_ok.marker` uma vez que a UI subiu.
7. Em paralelo, o `updater` fala com GitHub Releases; se tem versão nova, baixa pra `_next/` e escreve `READY` (aplica no PRÓXIMO boot).

## Contato

Autor/mantenedor: Guilherme Júnio (`brzueira342386@gmail.com`).
Feedback em produção guiou os últimos ~30 builds — os operadores da
Economart/Multicom reportam bug/PDF/tela → build sai em horas.
