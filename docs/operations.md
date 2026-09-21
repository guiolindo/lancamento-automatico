# Operações — produção e troubleshooting

Como o Auto Conferi é distribuído, atualizado e como diagnosticar quando
algo trava na máquina do operador.

## Distribuição

**Não existe instalador**. O app é um bundle Nuitka portátil (~200MB)
que roda de qualquer pasta — Desktop, `\\servidor\publico\autoconferi`,
pendrive. Zero admin necessário.

- **Primeiro deploy**: baixar `LancamentoAutomatico-portatil.zip` de
  https://github.com/guiolindo/lancamento-automatico/releases/tag/latest,
  descompactar em qualquer pasta, clicar em `LancamentoAutomatico.exe`.
- **Depois disso**: nunca mais precisa baixar zip. O próprio app se
  atualiza sozinho (ver "Auto-update" abaixo).

## Auto-update

Todo push em `main` publica automaticamente um `.zip` novo na rolling
release `latest` (via `.github/workflows/build-exe.yml`).

O launcher, ao subir, compara `BUILD_MARKER` local com o remoto:

- **Igual** → boot direto na MainWindow.
- **Diferente** → baixa o zip novo em background, extrai pra
  `_next/`, escreve o marker `_next/READY`, boota a versão atual. **No
  próximo boot**, o launcher vê o `READY` e faz swap atômico
  (`atual/ ↔ _next/`).

Detalhes: [ARCHITECTURE.md §2 Auto-update diferido](../ARCHITECTURE.md#2-auto-update-diferido-opção-d).

## Auto-recovery de boot quebrado

Se o app crashou no boot (não escreveu `boot_ok.marker`), o launcher no
próximo boot detecta e força um download+swap de uma versão anterior. É
uma rede de segurança para o caso de um build ruim ter subido.

Detalhes: [ARCHITECTURE.md §2.4b](../ARCHITECTURE.md#24b-auto-recovery-de-boot-quebrado-build-76).

## Diagnóstico — arquivos que o operador tem que anexar

Quando algo dá errado, os 3 arquivos que resolvem 90% dos casos:

| Arquivo | Onde fica | O que contém |
|---|---|---|
| `boot_trace.log` | ao lado do `.exe` | Timeline milissegundo-a-ms do boot. Só o boot — não continua depois que MainWindow abriu. Sobrescrito a cada boot. |
| `logs/YYYY-MM-DD.log` | `logs/` na pasta do exe | Log do dia inteiro (RotatingFileHandler). Inclui todas as extrações Gemini, cliques do RPA, popups tratados. |
| Screenshot do TOTVS | — | Se o RPA errou clique, a foto do que estava na tela vale mais que qualquer log. |

## Problemas frequentes

### App não abre — tela preta / nada acontece

- Cliente rodou como admin sem querer? O RPA precisa **NÃO** rodar como
  admin pra conseguir interagir com o TOTVS aberto sem admin (UIPI).
  Fecha e reabre normal.
- Antivírus quarentenou o `.exe`? Nuitka gera binário nativo (sem
  descompressão em `%TEMP%` — motivo pelo qual escolhemos Nuitka e não
  PyInstaller), mas alguns AVs corporativos ainda barram. Adicionar
  exceção na pasta.

### Cabo de rede desligado — app abriu normalmente (build < 112)

Bug corrigido no build-112. `USERDNSDOMAIN` é cacheada no logon, então
sozinha não detectava perda de rede. Agora usa `socket.gethostbyname`
com timeout 3s como segundo estágio.

### Janela do TOTVS não encontrada

- **Nome errado?** O RPA procura substring "Operador Financeiro" ou
  "Inclusão de Títulos" (também casa "(Remoto)" do RemoteApp). Se seu
  TOTVS abre com outro título, a detecção falha silenciosamente.
- **Multi-monitor?** Desde o build-104 o app procura em todas as telas.

### Popup de duplicidade não detectado

Se o TOTVS reclamou "número já existe" e o app não tratou:

- Verifica se está em build ≥ 103 (Orçamento) ou ≥ 45 (Operador Financeiro).
- Verifica no `logs/` do dia se aparece `popup detectado` — se não, a
  cor do popup mudou (tema/versão nova do TOTVS) e precisa recalibrar.
  Menu → Recalibrar → apontar o ponto do indicador amarelo do popup.

### RPA cai fora da célula (Contab / REGULARBA na coluna errada)

Bug do build-111. TOTVS Consinco rola a tabela quando um campo ganha
foco. Fix: preencher Valor **antes** da Filial. Está em builds ≥ 111.

### Acento sumiu do texto ("Elétrica" → "eltrica")

Bug do build-105. `pyautogui.typewrite` ignora silenciosamente
non-ASCII. Fix: `keyboard_utils.digitar_texto` usa clipboard + Ctrl+V
quando o texto tem char non-ASCII. Está em builds ≥ 105.

## Procedimentos manuais

### Forçar update

Menu → Sobre → botão "Atualizar app". Puxa a release `latest` mesmo se
os markers dizem que já estamos na última.

### Rollback pra build anterior

Não tem UI. Se a rolling release atual está ruim, baixa manualmente um
asset de uma tag antiga (Releases → tag `v1.x.y` → asset zip),
descompacta por cima da instalação existente. O auto-update vai puxar
o próximo build quando ele subir em `main`.

### Rodar em outra máquina rapidamente

Compacta a pasta `dist/LancamentoAutomatico.dist/` inteira e copia. Vai
com todas as deps embutidas.

### Trocar chave do Gemini

Menu → Configurações → Chave da API do Gemini → cola nova → Salvar. A
antiga é sobrescrita.
