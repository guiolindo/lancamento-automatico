# FAQ — perguntas frequentes

Q&A curto pro operador. Cada resposta linka pra seção profunda quando existe.

## Operação

### O app não detectou minha filial "CD Feira de Santana" — pegou "Feira de Santana" (loja). Por quê?

Bug corrigido no build-109. WRatio dava 1 ponto de diferença. Agora tem
rerank pós-fuzzy com boost +15 se o prefixo "CD" bate e penalty −20 se
cruza (CD virou Loja ou vice-versa).

Se ainda acontece em build ≥ 109, provavelmente falta um **alias** pra
essa filial em `cnpjs_filiais.json`. Menu → Filiais → editar → adiciona
a variação que aparece no PDF (ex.: "Feira Sta.").

### Por que o app minimiza sozinho quando eu aperto Executar?

Só quando você está em **monitor único**. Ele minimiza pra não cobrir o
TOTVS e mostra um HUD compacto no canto superior direito com contador,
tempo, ETA e botão de parar. Em multi-monitor não minimiza — só move
pra outra tela se estava na mesma do TOTVS.

Detalhes: [ARCHITECTURE.md §4c HUD](../ARCHITECTURE.md#4c-auto-posicionamento-e-hud-build-71).

### Apertei END e ele parou. Vai ficar tudo pela metade?

Sim, o lançamento em andamento fica pela metade e é marcado como
FALHA. Os posteriores nem começam. Você pode revisar a tabela, mudar
status de FALHA pra PENDENTE em quem quer refazer, e Executar de novo.

### O popup de "duplicidade" apareceu e o app tentou de novo. É normal?

Sim. TOTVS reclama que o `Nro. Documento` já existe (geralmente porque
o número foi digitado antes). O app aperta OK → F2 (borracha) → Sim, e
tenta com um número aleatório novo, até 10 vezes (ajustável em Config).

### Uma nota do Orçamento veio marcada IGNORADA. Por quê?

Duplicidade que estourou as 10 tentativas, OU a nota já existia no
sistema (mesmo número + mesmo fornecedor). Em vez de inventar número
novo, o app marca IGNORADA — nunca falsifica documento.

### Quero revisar cada lançamento antes do TOTVS confirmar

Marca o checkbox **"Não apertar '+' automaticamente"** antes de
Executar. O app preenche cada linha, para, você confere na tela do
TOTVS e aperta você mesmo quando quiser continuar.

## Instalação e atualização

### Precisa de admin pra instalar?

Não. Descompacta o zip em qualquer pasta (Desktop serve) e roda. Nuitka
gera bundle portátil que não escreve fora da pasta dele + AppData do
usuário.

### Como saber qual build eu tenho?

Menu → Sobre. Aparece "build-N (descrição curta)". A rolling release
sempre é o build mais recente de `main`.

### O app tá pedindo pra atualizar toda hora

Deve estar em build antigo (< 66). A partir do 66 o auto-update é
diferido — baixa em background e só aplica no próximo boot. Se ainda
insiste, apaga a pasta `_next/` ao lado do exe e reinicia.

## Chave do Gemini

### Onde fica salva? Alguém consegue ler?

Em `%USERPROFILE%\.lancamento-automatico\settings.json`, criptografada
com DPAPI (Windows Data Protection API). Só o mesmo usuário Windows na
mesma máquina consegue decifrar. Backup em outra máquina não abre.

### Passei do limite gratuito do Gemini. O que acontece?

O app mostra "erro na extração" pra o PDF que falhou e pula pro próximo.
Você troca a chave em Menu → Configurações → salva → tenta de novo.

### Tem como usar chave paga?

Sim, mesmo campo. Só cola a chave (paga ou gratuita, o app não sabe a
diferença — o Gemini que trata).

## Desenvolvimento

### Como adiciono um imposto novo?

Edita `src/config/mapeamento.json` — copia a entrada de um imposto
existente e ajusta chave, `especie_totvs`, `pessoa_codigo`,
`observacao_template`. Não precisa recompilar — o app relê o arquivo
no boot.

Se o imposto tem **múltiplos valores por linha** (tipo FGTS_CONSIG que
gera MFGTS + CONSIG), usa `especie_por_coluna` e `observacao_por_coluna`.

### Como adiciono um fornecedor novo no Orçamento?

Edita `src/config/mapeamento_orcamento.json`. Cria um bloco novo com
todos os campos fixos do form (aba Nota, aba Financeiro, aba Contab). O
Gemini vai preencher só as variáveis (número, valor, data, filial).

Mais detalhes: [ARCHITECTURE.md §4e Módulo Orçamento](../ARCHITECTURE.md#4e-módulo-orçamento-build-95101).

### Como adiciono uma filial nova?

`src/config/cnpjs_filiais.json`: acrescenta o objeto com `codigo`,
`nome`, `tipo` (`LOJA`/`CD`/`ADM`), `aliases` (variações que aparecem
em documentos) e `codigo_consinco` se for usar em impostos que precisam
disso (FGTS_CONSIG).
