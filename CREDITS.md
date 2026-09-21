# Créditos

## Autor

**Guilherme Júnio** — arquitetura, código, calibração e testes de campo em
produção na Economart/Multicom.

## Bibliotecas open source usadas em runtime

| Lib | Uso | Licença |
|---|---|---|
| [PySide6](https://doc.qt.io/qtforpython-6/) | UI (Qt6) | LGPL-3.0 |
| [pyautogui](https://github.com/asweigart/pyautogui) | click/type na tela do TOTVS | BSD-3 |
| [pywinauto](https://github.com/pywinauto/pywinauto) | localizar janela do TOTVS por título/handle | BSD-3 |
| [pygetwindow](https://github.com/asweigart/PyGetWindow) | posição/tamanho da janela do TOTVS | BSD-3 |
| [Pillow](https://python-pillow.org/) | manipulação de imagem (screenshots, âncoras) | HPND (BSD-like) |
| [opencv-python-headless](https://github.com/opencv/opencv-python) | template matching pra auto-detecção de campos | Apache-2.0 |
| [numpy](https://numpy.org/) | arrays da OpenCV | BSD-3 |
| [mss](https://github.com/BoboTiG/python-mss) | captura de tela multi-monitor | MIT |
| [rapidfuzz](https://github.com/rapidfuzz/RapidFuzz) | fuzzy match de nomes de filial (WRatio + rerank) | MIT |
| [pydantic](https://pydantic.dev/) | validação/serialização dos modelos | MIT |
| [keyring](https://github.com/jaraco/keyring) | armazenamento seguro (fallback quando DPAPI não disponível) | MIT |
| [python-dateutil](https://github.com/dateutil/dateutil) | cálculos de data (mês anterior de emissão, etc) | Apache-2.0 / BSD-3 |
| [requests](https://requests.readthedocs.io/) | chamadas REST ao Gemini | Apache-2.0 |

## Ferramenta de empacotamento

| Ferramenta | Uso | Licença |
|---|---|---|
| [Nuitka](https://nuitka.net/) | compilar o .exe portátil (sem admin, sem descompressão em `%TEMP%` — AV-friendly) | Apache-2.0 |

## APIs externas

- **[Google Gemini](https://ai.google.dev/)** — extração estruturada dos
  PDFs/imagens e vision OCR de anotações a caneta. Chave da API é do
  próprio operador (tier gratuita ou paga, à escolha), armazenada
  criptografada por DPAPI em `~/.lancamento-automatico/settings.json`.

## ERPs alvo

- **TOTVS / Consinco** — o Auto Conferi automatiza a interface Win32 já
  existente do TOTVS/Consinco; **não** é um plugin nem uma integração
  oficial. Nomes de tela ("Inclusão de Títulos", "Operador Financeiro",
  "Notas Fiscais de Despesa", "Consinco") são marcas da TOTVS S.A. e são
  usadas aqui apenas para descrever o alvo da automação.

## Ícones

- [Feather Icons](https://feathericons.com/) — ícones internos da sidebar
  e dialogs, remixados em SVG com paleta do tema. Licença MIT.

## Reconhecimentos

- Operadores financeiros da Economart/Multicom que reportaram bugs em
  produção, mandaram PDFs de amostra e testaram builds — os últimos 20
  builds foram guiados por esses feedbacks reais.
