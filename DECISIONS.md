# Decisões pendentes / futuras

Log de coisas que a gente discutiu mas ainda não implementou — pra ninguém
esquecer o contexto quando voltar.

---

## 1. Auto-update do .exe (aberto — decisão do Guilherme em casa)

**Contexto**: projeto rodando como Shadow IT (sem sanção da TI da empresa,
sem budget pra servidor próprio ou certificado code-signing). Precisa
atualizar o .exe portátil sem drama de antivírus corporativo e sem pedir
pro operador baixar/descompactar/mover pasta.

**Opções que a gente descartou:**

- **A (só notificação)**: app avisa que tem versão nova, operador baixa o
  zip do GitHub e substitui manualmente. Muito trabalhoso pro usuário
  final ("descompactar e botar na pasta certa é um desespero").
- **B (auto-update tipo Squirrel)**: baixa + mata o app + roda updater.exe
  + reabre. Padrão clássico de malware, AV corporativo barra sem
  certificado assinado (custo R$400-800/ano).
- **C (servidor próprio de release)**: precisa VPS mensal e alguém pra
  manter. Sem budget em Shadow IT.

**Opção candidata — D: update DIFERIDO**

- App verifica GitHub Releases na abertura (repo tem que ficar público)
- Nova versão? Popup "Baixar em background?" → sim
- Download HTTPS pra `github.com` (domínio famoso — AV geralmente permite)
- Extrai o zip em `LancamentoAutomatico.dist/_next/` (pasta local, NÃO em
  `%TEMP%`, o que evita signature clássica de malware)
- Popup: "Atualização pronta — vai aplicar da próxima vez que abrir"
- Usuário fecha normalmente
- Próxima abertura: `launcher.py` detecta `_next/`, copia por cima dos
  arquivos antigos, apaga `_next/`, continua o boot normal

**Por que passa em AV corporativo (provavelmente):**
- Nunca mata a si mesmo pra reabrir (padrão que AV odeia)
- Nenhum binário externo (`updater.exe`) roda pra fazer replace —
  é o próprio `launcher.py` que já rodou antes
- Só faz HTTP GET pra github.com
- Escreve arquivos só na pasta local do app
- Sem `%TEMP%`, sem registry, sem serviço, sem elevação

**Integridade sem certificado pago:**
- Release notes no GitHub incluem o SHA256 do zip
- App confere antes de aplicar; se não bater, aborta

**Risco residual:**
- Se AV muito paranoico barrar HTTPS pra github.com (raro em corporativo,
  dev usa direto), cai no fallback: popup "não consegui baixar, abrir
  browser?" — vira semi-manual só nesse ambiente hostil.

**Esforço**: ~4h.
- `src/core/updater.py` novo: check + download + hash + extract em
  `_next/`.
- `launcher.py`: detecta `_next/` no boot, aplica, apaga.
- Botão discreto "Atualizar" no rodapé da sidebar.
- Config no `settings.json` pra desligar o check automático se quiser.

**Aberto**: Guilherme vai pensar em casa (2026-09-11) e decidir se
implementa. Documentação salva aqui pra não perder o contexto.
