"""
Entrypoint para empacotamento com Nuitka.

Fica na raiz do projeto (fora de src/) porque o Nuitka compila o entrypoint
como módulo top-level. Se src/main.py fosse o entrypoint, os imports
relativos ('from .core.logger') quebrariam porque main viraria top-level
sem contexto de pacote.

Além disso, o launcher:
- Blinda sys.stdin/stdout/stderr contra None (evita STATUS_FATAL_APP_EXIT).
- Silencia warnings e telemetria antes de qualquer import pesado.
- Envolve o boot em try/except; qualquer exceção vira MessageBox +
  'startup_error.log' ao lado do exe.
- Cada etapa do boot escreve num 'boot_trace.log' pra facilitar
  diagnóstico quando algo trava sem gerar exceção.
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path


# ---------- 1. Blindar stdio ANTES de qualquer coisa ----------
def _garantir_stdio() -> None:
    for nome in ("stdin", "stdout", "stderr"):
        atual = getattr(sys, nome, None)
        if atual is None or getattr(atual, "closed", False):
            try:
                modo = "r" if nome == "stdin" else "w"
                setattr(sys, nome, open(os.devnull, modo, encoding="utf-8", errors="ignore"))
            except Exception:  # noqa: BLE001
                pass


_garantir_stdio()


# ---------- 2. Silenciar warnings e telemetria ----------
# Muitas libs (google.*, grpc, urllib3, pydantic) emitem DeprecationWarning
# ou RuntimeWarning durante o import. Em modo GUI standalone uma linha
# desviada pra stderr pode virar STATUS_FATAL_APP_EXIT.
import warnings

warnings.filterwarnings("ignore")
os.environ.setdefault("PYTHONWARNINGS", "ignore")
os.environ.setdefault("GRPC_VERBOSITY", "NONE")
os.environ.setdefault("GRPC_TRACE", "")
os.environ.setdefault("GLOG_minloglevel", "3")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("ABSL_LOGGING_MIN_LOG_LEVEL", "3")


# ---------- 3. Utilitários de log de boot ----------
def _exe_dir() -> Path:
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        return Path(sys.argv[0]).resolve().parent
    return Path(__file__).resolve().parent


def _boot_trace(mensagem: str) -> None:
    """Marca cada etapa do boot num arquivo, mesmo se o Python travar depois."""
    try:
        with open(_exe_dir() / "boot_trace.log", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%H:%M:%S.%f}] {mensagem}\n")
    except Exception:  # noqa: BLE001
        pass


def _log_startup_error(err: BaseException) -> None:
    try:
        log_path = _exe_dir() / "startup_error.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
            f.write(f"exe: {sys.argv[0]}\n")
            f.write(f"cwd: {os.getcwd()}\n")
            f.write(f"python: {sys.version}\n")
            f.write(f"platform: {sys.platform}\n")
            f.write(f"sys.path (primeiros 10):\n")
            for p in sys.path[:10]:
                f.write(f"  - {p}\n")
            f.write("\n")
            traceback.print_exception(type(err), err, err.__traceback__, file=f)
            f.write("\n")
    except Exception:  # noqa: BLE001
        try:
            traceback.print_exc(file=sys.stderr)
        except Exception:
            pass


def _show_error_dialog(msg: str) -> None:
    try:
        import ctypes  # type: ignore[import-not-found]
        ctypes.windll.user32.MessageBoxW(
            None, msg, "Lançamento Automático — erro no início", 0x10
        )
    except Exception:  # noqa: BLE001
        pass


# ---------- 4. Aplicar update pendente (Opção D) ----------
def _aplicar_pendente() -> bool:
    """Se existe <install>/_next/READY, copia arquivos por cima do install
    atual. Chamado ANTES de importar src.main — assim o próximo boot já
    roda a versão nova. Devolve True se aplicou algo."""
    import shutil
    import json as _json
    install = _exe_dir()
    next_dir = install / "_next"
    marker = next_dir / "READY"
    if not marker.exists():
        # Se tem _next incompleto (sem READY), limpa
        if next_dir.exists():
            shutil.rmtree(next_dir, ignore_errors=True)
        return False

    _boot_trace(f"update pendente detectado em {next_dir}")
    try:
        info = _json.loads(marker.read_text(encoding="utf-8"))
        _boot_trace(f"update: build {info.get('build_marker')}")
    except Exception:  # noqa: BLE001
        pass

    # No Windows dá pra RENOMEAR o .exe rodando (mas não apagar). Usamos
    # isso pra swap: renomeia atual .exe pra .old, copia o novo no lugar.
    exe_atual = Path(sys.argv[0]).resolve()
    exe_nome = exe_atual.name
    exe_novo = next_dir / exe_nome

    # Limpa .old de updates anteriores
    for f in install.glob("*.old"):
        try:
            f.unlink()
        except OSError:
            pass  # ainda locked, tenta no próximo boot

    if exe_novo.exists() and exe_novo.stat().st_size > 0:
        try:
            # Renomeia self, sem problema no Windows
            old_path = exe_atual.with_suffix(exe_atual.suffix + ".old")
            if old_path.exists():
                try:
                    old_path.unlink()
                except OSError:
                    pass
            exe_atual.rename(old_path)
            shutil.copy2(exe_novo, exe_atual)
            _boot_trace(f"exe substituído: {exe_atual}")
        except OSError as e:
            _boot_trace(f"FALHA ao swap exe: {e}")
            # Não bloqueia — segue e tenta copiar os outros arquivos

    # Copia todos os outros arquivos por cima
    aplicados = 0
    falhas = 0
    for src in next_dir.rglob("*"):
        if src.is_dir():
            continue
        if src.name == "READY":
            continue
        rel = src.relative_to(next_dir)
        if rel.name == exe_nome:
            continue  # já foi feito acima
        dst = install / rel
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            aplicados += 1
        except OSError:
            falhas += 1

    _boot_trace(f"update aplicado: {aplicados} arquivos, {falhas} falhas")

    # Limpa _next SÓ se não houve falhas — assim próximo boot re-tenta
    if falhas == 0:
        shutil.rmtree(next_dir, ignore_errors=True)
    else:
        # Remove pelo menos o READY pra não ficar re-aplicando em loop
        try:
            marker.unlink()
        except OSError:
            pass

    return True


# ---------- 5. Boot com tracing ----------
def main() -> int:
    _boot_trace("launcher: início")
    try:
        _boot_trace("verificando update pendente")
        try:
            aplicou = _aplicar_pendente()
            if aplicou:
                _boot_trace("update pendente aplicado")
        except Exception as e:  # noqa: BLE001
            _boot_trace(f"aviso: erro aplicando update pendente: {e}")

        _boot_trace("importando src.main")
        from src.main import main as run
        _boot_trace("src.main importado com sucesso")

        _boot_trace("executando src.main.main()")
        rc = run()
        _boot_trace(f"src.main.main() retornou {rc}")
        return rc
    except BaseException as e:  # noqa: BLE001
        _boot_trace(f"EXCEÇÃO: {type(e).__name__}: {e}")
        _log_startup_error(e)
        _show_error_dialog(
            "O aplicativo não conseguiu iniciar.\n\n"
            f"{type(e).__name__}: {e}\n\n"
            "Foram criados 'startup_error.log' e 'boot_trace.log' na "
            "mesma pasta do executável com mais detalhes."
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
