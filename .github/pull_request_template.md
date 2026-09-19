## O que muda

<!-- 1–3 linhas descrevendo a mudança no lado do usuário: "corrige X",
     "adiciona template do fornecedor Y", "acelera Z". -->

## Por quê

<!-- Bug relatado, gotcha descoberta em produção, pedido do operador.
     Se veio de um erro em `boot_trace.log` ou de um crash, cole o
     trecho relevante aqui. -->

## Como testar

- [ ] `ruff check src/ launcher.py build/` passa
- [ ] Boot do app sobe até a MainWindow (splash → sidebar) em dev
- [ ] Fluxo relevante rodado ponta-a-ponta (Operador Financeiro / Orçamento)
- [ ] `BUILD_MARKER` bumpado em `src/main.py`
- [ ] Se afeta a UI: screenshot antes/depois anexado

## Notas pro revisor

<!-- Qualquer coisa que não é óbvia do diff: gotcha nova, decisão que
     entra em DECISIONS.md, plugin/fornecedor mapping novo. -->
