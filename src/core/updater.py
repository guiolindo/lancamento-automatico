"""
Auto-update diferido — Opção D dos DECISIONS.md.

Fluxo seguro:
1. check() consulta a última release rolling no GitHub e devolve info
   comparando com o BUILD_MARKER local.
2. baixar_e_preparar() baixa o zip via streaming (progresso em callback),
   valida SHA256 antes de sequer descompactar, descompacta pra pasta
   temp <install>/_next_dl/, e SÓ escreve o marker READY quando TUDO
   deu certo. Se qualquer passo falhar (rede caiu, SHA errado, zip
   corrompido, disco cheio), apaga tudo e retorna erro — NUNCA deixa
   estado intermediário que o launcher aplicaria por engano.
3. launcher.aplicar_pendente() (em launcher.py) só age se
   <install>/_next/READY existir.

Downloads são só de github.com — HTTPS + certifi. Sem servidor próprio,
sem token, sem certificado assinado. Adequado pra Shadow IT.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import tempfile
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests

from .logger import log


REPO = "guiolindo/lancamento-automatico"
TAG_ROLLING = "latest"

# Chunk size do download — 256KB é boom pra rede corporativa.
CHUNK = 256 * 1024

# Nome do asset no release (definido pelo workflow — LancamentoAutomatico-latest.zip
# ou -dev-<sha>.zip). Detectamos qualquer zip que comece com "LancamentoAutomatico".
ASSET_PREFIX = "LancamentoAutomatico"


@dataclass
class InfoAtualizacao:
    build_marker_remoto: str
    build_marker_local: str
    sha256_esperado: Optional[str]
    asset_url: str
    asset_tamanho: int         # bytes
    tem_atualizacao: bool


class UpdateError(RuntimeError):
    pass


class UpdateCancelled(RuntimeError):
    pass


# ---------------- Helpers ----------------

def _install_dir() -> Path:
    """Pasta onde o app está instalado — próxima do .exe no bundle."""
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        return Path(sys.executable).resolve().parent
    # Dev: raiz do repo
    return Path(__file__).resolve().parent.parent.parent


def _pasta_next() -> Path:
    return _install_dir() / "_next"


def _pasta_next_download() -> Path:
    return _install_dir() / "_next_dl"


def _marker_ready() -> Path:
    return _pasta_next() / "READY"


def limpar_download_parcial() -> None:
    """Chamado no boot pra apagar sujeira de download que não completou."""
    dl = _pasta_next_download()
    if dl.exists():
        shutil.rmtree(dl, ignore_errors=True)
    # Se tem _next mas SEM READY, também é sujeira (extração incompleta)
    nx = _pasta_next()
    if nx.exists() and not _marker_ready().exists():
        shutil.rmtree(nx, ignore_errors=True)


# ---------------- Check ----------------

def check(build_marker_local: str, tentativas: int = 2) -> Optional[InfoAtualizacao]:
    """Consulta a release 'latest' e devolve info comparando com local.
    Devolve None se não conseguir conectar (não é erro fatal).
    Tuple timeout (connect, read) = (5, 8) — total máximo ~13s por tentativa,
    26s pra 2 tentativas com backoff. Antes eram 30s×3 = 90s (parecia
    travado)."""
    import time as _time
    url = f"https://api.github.com/repos/{REPO}/releases/tags/{TAG_ROLLING}"
    r = None
    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        log.info("[updater] check tentativa %d/%d: GET %s (timeout 5+8s)",
                 tentativa, tentativas, url)
        try:
            # Timeout tuple: 5s pra estabelecer conexão, 8s pra ler resposta
            r = requests.get(url, timeout=(5, 8),
                             headers={
                                 "Accept": "application/vnd.github+json",
                                 "User-Agent": "LancamentoAutomatico-updater/1.0",
                             })
            break  # sucesso
        except requests.RequestException as e:
            ultimo_erro = e
            log.warning("[updater] tentativa %d falhou: %s: %s",
                        tentativa, type(e).__name__, e)
            if tentativa < tentativas:
                _time.sleep(1.0)  # backoff curto — 1s só
    if r is None:
        log.warning("[updater] todas as %d tentativas falharam. último erro: %s",
                    tentativas, ultimo_erro)
        return None
    log.info("[updater] check: HTTP %d", r.status_code)
    if r.status_code == 404:
        log.info("[updater] release 'latest' ainda não publicada")
        return None
    if r.status_code == 403:
        log.warning("[updater] 403 — possível rate limit da API (60 req/h sem token) OU firewall bloqueando api.github.com")
        return None
    if r.status_code != 200:
        log.warning("[updater] resposta inesperada da API: %d — %s",
                    r.status_code, r.text[:200])
        return None

    dados = r.json()
    body = dados.get("body") or ""
    nome_release = dados.get("name") or ""

    m = re.search(r"BUILD_MARKER=(.+)", body)
    build_marker_remoto = m.group(1).strip() if m else nome_release.strip()

    m = re.search(r"SHA256=([A-Fa-f0-9]{64})", body)
    sha256_esperado = m.group(1).lower() if m else None

    assets = dados.get("assets") or []
    log.info("[updater] release %r, %d assets, SHA256=%s",
             build_marker_remoto, len(assets),
             (sha256_esperado[:12] + "…") if sha256_esperado else "sem")

    # Escolha do asset: pega o MAIS NOVO (por updated_at) que casa com o
    # prefixo. Antes pegava o primeiro da lista, o que causava problema
    # quando assets antigos ficavam acumulados no release.
    candidatos = [a for a in assets
                  if (a.get("name") or "").startswith(ASSET_PREFIX)
                  and (a.get("name") or "").endswith(".zip")]
    if not candidatos:
        log.warning("[updater] nenhum asset .zip com prefixo %r no release", ASSET_PREFIX)
        return None
    # Ordena por updated_at desc — o mais recente é o certo (é o que o
    # workflow acabou de publicar com SHA256 que bate com o body)
    candidatos.sort(key=lambda a: a.get("updated_at") or "", reverse=True)
    asset = candidatos[0]
    log.info("[updater] asset escolhido: %s (%d bytes, updated %s)",
             asset.get("name"), asset.get("size"), asset.get("updated_at"))

    return InfoAtualizacao(
        build_marker_remoto=build_marker_remoto,
        build_marker_local=build_marker_local,
        sha256_esperado=sha256_esperado,
        asset_url=asset["browser_download_url"],
        asset_tamanho=int(asset.get("size") or 0),
        tem_atualizacao=(build_marker_remoto != build_marker_local
                         and bool(build_marker_remoto)),
    )


# ---------------- Download ----------------

def baixar_e_preparar(
    info: InfoAtualizacao,
    on_progress: Callable[[int, int, str], None],
    cancel_event: Optional[threading.Event] = None,
) -> None:
    """Baixa o zip, valida SHA256, extrai pra _next/, escreve READY.

    on_progress(bytes_baixados, bytes_total, mensagem) chamado durante.
    Raise UpdateError com mensagem clara em qualquer falha.
    Raise UpdateCancelled se cancel_event for setado.
    """
    if cancel_event is None:
        cancel_event = threading.Event()

    # Sempre parte de estado limpo
    limpar_download_parcial()

    dl_dir = _pasta_next_download()
    dl_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dl_dir / "download.zip"

    # ---- Baixa em streaming
    # Retenta 1x com URL nova se der 404 — o workflow substitui o asset
    # com o mesmo nome, e clientes que fizeram check() logo antes podem
    # cair na janela em que o URL antigo já foi expirado. Buscar release
    # info de novo dá a URL nova.
    on_progress(0, info.asset_tamanho, "Conectando…")
    url_atual = info.asset_url
    tentativa_download = 0
    baixados = 0
    total = 0
    sha = hashlib.sha256()
    while True:
        tentativa_download += 1
        try:
            with requests.get(url_atual, stream=True, timeout=30,
                              headers={"Accept": "application/octet-stream"}) as r:
                if r.status_code == 404 and tentativa_download == 1:
                    log.warning("[updater] download 404 — buscando release info de novo (workflow pode ter republicado o asset)")
                    on_progress(0, info.asset_tamanho, "Atualizando URL do arquivo…")
                    info_novo = check(info.build_marker_local, tentativas=2)
                    if info_novo and info_novo.asset_url:
                        url_atual = info_novo.asset_url
                        continue
                    raise UpdateError("GitHub retornou HTTP 404 (asset não encontrado após retry)")
                if r.status_code != 200:
                    raise UpdateError(f"GitHub retornou HTTP {r.status_code}")

                total = int(r.headers.get("Content-Length") or info.asset_tamanho or 0)
                baixados = 0
                sha = hashlib.sha256()

                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=CHUNK):
                        if cancel_event.is_set():
                            raise UpdateCancelled("Cancelado pelo operador")
                        if not chunk:
                            continue
                        f.write(chunk)
                        sha.update(chunk)
                        baixados += len(chunk)
                        on_progress(baixados, total, "Baixando…")

                # Verifica que baixou tudo (não bateu)
                if total > 0 and baixados < total:
                    raise UpdateError(
                        f"Download incompleto: {baixados} de {total} bytes "
                        "(rede caiu antes do fim)"
                    )
                break  # sucesso

        except UpdateError:
            limpar_download_parcial()
            raise
        except UpdateCancelled:
            limpar_download_parcial()
            raise
        except requests.RequestException as e:
            limpar_download_parcial()
            raise UpdateError(f"Rede: {e}") from e
        except OSError as e:
            limpar_download_parcial()
            raise UpdateError(f"Disco: {e}") from e

    # ---- Valida SHA256
    on_progress(baixados, total, "Verificando integridade…")
    hash_baixado = sha.hexdigest().lower()
    if info.sha256_esperado and hash_baixado != info.sha256_esperado:
        limpar_download_parcial()
        raise UpdateError(
            "SHA256 do arquivo baixado NÃO bate com o publicado. "
            "Arquivo corrompido ou alterado."
        )

    # ---- Extrai
    on_progress(baixados, total, "Descompactando…")
    conteudo_dir = dl_dir / "conteudo"
    conteudo_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(conteudo_dir)
    except (zipfile.BadZipFile, OSError) as e:
        limpar_download_parcial()
        raise UpdateError(f"Zip inválido: {e}") from e

    # ---- Zip-em-zip: se o extract deu um único .zip dentro, extrai ele também
    #      (GitHub Actions Artifacts embrulham num zip extra; releases não,
    #      mas cobrimos os dois casos)
    itens = list(conteudo_dir.iterdir())
    if len(itens) == 1 and itens[0].is_file() and itens[0].suffix.lower() == ".zip":
        inner_zip = itens[0]
        inner_dir = dl_dir / "conteudo_inner"
        inner_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(inner_zip, "r") as z:
                z.extractall(inner_dir)
        except (zipfile.BadZipFile, OSError) as e:
            limpar_download_parcial()
            raise UpdateError(f"Zip interno inválido: {e}") from e
        conteudo_dir = inner_dir

    # ---- Localiza a pasta com o app dentro do que foi extraído
    raiz_conteudo = _localizar_raiz_app(conteudo_dir)
    if raiz_conteudo is None:
        limpar_download_parcial()
        raise UpdateError(
            "Zip não contém 'LancamentoAutomatico.exe' — arquivo errado?"
        )

    # ---- Move pra _next/ e escreve READY (última coisa!)
    on_progress(baixados, total, "Finalizando…")
    nx = _pasta_next()
    if nx.exists():
        shutil.rmtree(nx, ignore_errors=True)
    try:
        shutil.move(str(raiz_conteudo), str(nx))
    except OSError as e:
        limpar_download_parcial()
        raise UpdateError(f"Falha ao mover pra _next/: {e}") from e

    # Escreve marker de "prontidão" — o launcher só aplica se ele existir
    try:
        (nx / "READY").write_text(
            json.dumps({
                "build_marker": info.build_marker_remoto,
                "sha256": hash_baixado,
                "asset_tamanho": info.asset_tamanho,
            }, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        # Se falhou o marker, apaga _next pra não aplicar meia-boca
        shutil.rmtree(nx, ignore_errors=True)
        raise UpdateError(f"Falha ao gravar marker READY: {e}") from e

    # Limpa a pasta de download
    try:
        shutil.rmtree(dl_dir, ignore_errors=True)
    except OSError:
        pass

    on_progress(baixados, total, "Pronto — aplicar no próximo boot")


def _localizar_raiz_app(pasta: Path) -> Optional[Path]:
    """Procura a pasta que contém LancamentoAutomatico.exe. Pode estar em
    <pasta>/ ou em <pasta>/LancamentoAutomatico.dist/."""
    if (pasta / "LancamentoAutomatico.exe").exists():
        return pasta
    for filho in pasta.iterdir():
        if filho.is_dir() and (filho / "LancamentoAutomatico.exe").exists():
            return filho
    return None
