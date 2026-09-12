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
            None, msg, "Auto Conferi — erro no início", 0x10
        )
    except Exception:  # noqa: BLE001
        pass


# ---------- Single instance (mutex Windows) ----------
_MUTEX_NAME = r"Local\LancamentoAutomatico_SingleInstance_v1"
_JANELA_PREFIXO = "Auto Conferi"


def _lock_instancia_unica():
    """Cria mutex nomeado. Devolve handle se somos a 1ª instância, None se
    outra já tá rodando, -1 se algo deu errado (segue normalmente)."""
    try:
        import ctypes
        from ctypes import wintypes
        k = ctypes.windll.kernel32
        k.CreateMutexW.restype = wintypes.HANDLE
        k.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        handle = k.CreateMutexW(None, True, _MUTEX_NAME)
        ERROR_ALREADY_EXISTS = 183
        if ctypes.GetLastError() == ERROR_ALREADY_EXISTS:
            if handle:
                k.CloseHandle(handle)
            return None
        return handle
    except Exception:  # noqa: BLE001
        return -1


def _trazer_janela_existente_ao_topo() -> bool:
    """Encontra a janela do app já aberto e traz pra frente. Best effort."""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        achado = [0]

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def _callback(hwnd, _lparam):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if buf.value and buf.value.startswith(_JANELA_PREFIXO):
                achado[0] = hwnd
                return False
            return True

        user32.EnumWindows(_callback, 0)
        hwnd = achado[0]
        if hwnd:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _aviso_ja_aberto() -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None,
            "O Auto Conferi já está aberto.\n\n"
            "Verifique a barra de tarefas ou os cantos da tela.",
            "Aplicativo já aberto",
            0x40 | 0x1000,  # MB_ICONINFORMATION | MB_SYSTEMMODAL
        )
    except Exception:  # noqa: BLE001
        pass


# ---------- Splash Qt com progresso durante aplicação de update ----------
def _criar_splash_update():
    """Cria e mostra uma janelinha Qt com progress bar + ETA. Devolve
    (app, splash, cb) onde cb(feito, total, msg) atualiza. splash.close()
    fecha; se relaunch com os._exit(0), morre junto sem drama."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget
    )
    import time as _time

    app = QApplication.instance() or QApplication(sys.argv)

    splash = QWidget()
    splash.setWindowFlag(Qt.SplashScreen)
    splash.setWindowFlag(Qt.WindowStaysOnTopHint)
    splash.setFixedSize(440, 150)
    # Centraliza na tela primária
    try:
        from PySide6.QtGui import QGuiApplication
        tela = QGuiApplication.primaryScreen().availableGeometry()
        splash.move(
            tela.center().x() - splash.width() // 2,
            tela.center().y() - splash.height() // 2,
        )
    except Exception:  # noqa: BLE001
        pass

    v = QVBoxLayout(splash)
    v.setContentsMargins(24, 20, 24, 20)
    v.setSpacing(10)

    titulo = QLabel("Aplicando atualização…")
    titulo.setStyleSheet(
        "font-size: 15px; font-weight: 700; color: #0F172A;"
    )
    v.addWidget(titulo)

    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(0)
    bar.setTextVisible(False)
    bar.setFixedHeight(10)
    bar.setStyleSheet(
        "QProgressBar { background: #E7EBF2; border: none; border-radius: 5px; }"
        "QProgressBar::chunk { background: qlineargradient("
        "x1:0, y1:0, x2:1, y2:0, stop:0 #FF6900, stop:1 #FF7A1A);"
        " border-radius: 5px; }"
    )
    v.addWidget(bar)

    detalhe = QLabel("Preparando…")
    detalhe.setStyleSheet("font-size: 12px; color: #64748B;")
    v.addWidget(detalhe)

    splash.setStyleSheet(
        "QWidget { background: #FFFFFF; border: 1px solid #D5DBE5; "
        "border-radius: 10px; }"
    )
    splash.show()
    app.processEvents()

    inicio = _time.monotonic()

    def cb(feito, total, msg=""):
        try:
            if total <= 0:
                total = 1
            pct = int(feito * 100 / total)
            bar.setValue(pct)
            elapsed = _time.monotonic() - inicio
            if feito > 0 and feito < total:
                restante = elapsed * (total - feito) / feito
                if restante < 1:
                    txt = f"{pct}% · {msg}  ·  quase pronto"
                else:
                    txt = f"{pct}% · {msg}  ·  faltam ~{int(restante)}s"
            elif feito >= total:
                txt = "100% · Concluído · reiniciando…"
            else:
                txt = msg or "Iniciando…"
            detalhe.setText(txt)
            app.processEvents()
        except Exception:  # noqa: BLE001
            pass

    return app, splash, cb


# ---------- 4. Aplicar update pendente (Opção D) ----------
def _aplicar_pendente(progress_cb=None) -> bool:
    """Se existe <install>/_next/READY, copia arquivos por cima do install
    atual. Chamado ANTES de importar src.main — assim o próximo boot já
    roda a versão nova. Devolve True se aplicou algo.

    progress_cb(feito, total, msg): callback opcional pra feedback."""
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

    # Conta arquivos pra progress
    todos_arquivos = [
        f for f in next_dir.rglob("*")
        if f.is_file() and f.name != "READY"
    ]
    total = len(todos_arquivos)
    _boot_trace(f"update: {total} arquivos pra copiar")

    if progress_cb:
        progress_cb(0, total, "Preparando…")

    feito = 0

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
            feito += 1
            if progress_cb:
                progress_cb(feito, total, exe_nome)
        except OSError as e:
            _boot_trace(f"FALHA ao swap exe: {e}")
            # Não bloqueia — segue e tenta copiar os outros arquivos

    # Copia todos os outros arquivos por cima
    aplicados = 0
    falhas = 0
    for src in todos_arquivos:
        rel = src.relative_to(next_dir)
        if rel.name == exe_nome:
            continue  # já foi feito acima
        dst = install / rel
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            aplicados += 1
            feito += 1
            if progress_cb and feito % 5 == 0:  # não atualiza a cada file (custa)
                progress_cb(feito, total, rel.name)
        except OSError:
            falhas += 1

    if progress_cb:
        progress_cb(total, total, "Concluído")

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


def _reiniciar_como_novo_exe() -> None:
    """Após aplicar update, esse mesmo processo AINDA está rodando com o
    binário antigo carregado em RAM. Dispara o exe novo em outro processo
    e mata esse — usuário vê UMA vez fechando/abrindo, não duas."""
    import subprocess
    exe_atual = Path(sys.argv[0]).resolve()
    _boot_trace(f"reiniciando pra pegar código novo: {exe_atual}")
    try:
        # DETACHED_PROCESS = 0x00000008 (Windows) — spawnfilho independente
        # do console/terminal do pai. CREATE_NEW_PROCESS_GROUP = 0x00000200.
        flags = 0
        if sys.platform == "win32":
            flags = 0x00000008 | 0x00000200
        subprocess.Popen(
            [str(exe_atual)] + sys.argv[1:],
            close_fds=True,
            creationflags=flags,
        )
        _boot_trace("processo novo lançado — encerrando o atual")
    except Exception as e:  # noqa: BLE001
        _boot_trace(f"FALHA ao reiniciar: {e} — usuário terá que abrir de novo manualmente")
        return
    # Encerra esse processo — sem imports pesados, sem app.exec()
    os._exit(0)


# ---------- 4b. Auto-recovery de boot quebrado ----------
# Se o boot ANTES da MainWindow.show() crashou (ex: import de tema
# quebrado, NameError em f-string, DLL faltando), o updater interno da
# MainWindow nunca roda — o usuário fica preso num app que não abre.
# Este bloco roda ANTES de importar src.main, detecta boot anterior
# quebrado, e se houver update NOVO no GitHub, baixa e aplica.
#
# Detecção: main.py escreve boot_ok.marker LOGO APÓS showMaximized().
# Se esse marker é MAIS VELHO que o .exe atual (ou não existe), sabemos
# que o exe atual nunca chegou até a UI.

def _boot_ok_path() -> Path:
    return _exe_dir() / "boot_ok.marker"


def _build_marker_local() -> str:
    """Lê o BUILD_MARKER do build_marker.txt (escrito pelo build.py).
    Se não existir (dev), tenta importar src.main — em dev não tem
    updater pra rodar mesmo, então tanto faz."""
    try:
        p = _exe_dir() / "build_marker.txt"
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


def _boot_anterior_falhou() -> bool:
    """True se o exe atual foi trocado mas boot_ok.marker não foi
    atualizado desde então — significa que o boot novo nunca chegou
    até MainWindow.show()."""
    try:
        exe_path = Path(sys.argv[0]).resolve()
        if not exe_path.exists():
            return False
        ok = _boot_ok_path()
        if not ok.exists():
            # Nunca teve boot bem-sucedido — pode ser primeiro uso OU
            # sempre crashou. Trata como "primeiro uso" pra não gastar
            # rede se for legítimo.
            return False
        # Se exe é mais NOVO que o marker, o exe novo nunca subiu OK
        return ok.stat().st_mtime < exe_path.stat().st_mtime
    except Exception:  # noqa: BLE001
        return False


def _auto_recovery_boot(splash_cb=None) -> bool:
    """Se o boot anterior falhou E há update NOVO no GitHub, baixa e
    aplica. Devolve True se aplicou (caller deve reiniciar)."""
    if not _boot_anterior_falhou():
        return False

    bm_local = _build_marker_local()
    if not bm_local:
        _boot_trace("recovery: sem build_marker.txt — não sei minha versão, pulando")
        return False

    _boot_trace(f"recovery: boot anterior falhou (local={bm_local}) — buscando update no GitHub")

    # updater não importa Qt nem theme — deve ser seguro mesmo se src.gui
    # estiver quebrado. Se import falhar, sem opção.
    try:
        from src.core import updater
    except Exception as e:  # noqa: BLE001
        _boot_trace(f"recovery: import updater falhou ({e}) — sem opção de auto-fix")
        return False

    try:
        info = updater.check(bm_local, tentativas=2)
    except Exception as e:  # noqa: BLE001
        _boot_trace(f"recovery: check falhou: {e}")
        return False

    if info is None:
        _boot_trace("recovery: sem resposta do GitHub — sem opção")
        return False
    if not info.tem_atualizacao:
        _boot_trace(
            f"recovery: versão remota ({info.build_marker_remoto}) == local — "
            "sem correção disponível pra baixar"
        )
        return False

    _boot_trace(
        f"recovery: update novo disponível ({info.build_marker_remoto}) — "
        "baixando pra corrigir boot"
    )
    try:
        updater.baixar_e_preparar(
            info,
            on_progress=(splash_cb if splash_cb else (lambda a, b, m: None)),
        )
    except Exception as e:  # noqa: BLE001
        _boot_trace(f"recovery: download/preparação falhou: {e}")
        return False

    _boot_trace("recovery: download OK, aplicando update in-place")
    aplicou = _aplicar_pendente(progress_cb=splash_cb)
    if not aplicou:
        _boot_trace("recovery: _aplicar_pendente devolveu False — sem novo _next/READY (?)")
        return False
    return True


# ---------- 5. Boot com tracing ----------
def main() -> int:
    _boot_trace("launcher: início")

    # Single-instance: se o app já tá aberto, traz a janela pra frente
    # e sai. Evita usuário abrir 5 vezes por engano.
    lock_handle = _lock_instancia_unica()
    if lock_handle is None:
        _boot_trace("outra instância detectada — trazendo pra frente e saindo")
        if not _trazer_janela_existente_ao_topo():
            _aviso_ja_aberto()
        return 0

    try:
        _boot_trace("verificando update pendente")
        try:
            install = _exe_dir()
            splash_cb = None
            splash_widget = None
            if (install / "_next" / "READY").exists():
                _boot_trace("update pendente — abrindo splash com progresso")
                try:
                    _, splash_widget, splash_cb = _criar_splash_update()
                except Exception as e:  # noqa: BLE001
                    _boot_trace(f"splash Qt falhou ({e}) — segue sem feedback visual")

            aplicou = _aplicar_pendente(progress_cb=splash_cb)
            if aplicou:
                _boot_trace("update pendente aplicado — reiniciando pra pegar código novo")
                # Fecha splash antes de sair do processo
                if splash_widget is not None:
                    try:
                        splash_widget.close()
                    except Exception:  # noqa: BLE001
                        pass
                _reiniciar_como_novo_exe()
                # Se _reiniciar falhou (não deveria), segue com o código velho
                # e loga aviso. Usuário terá que abrir manualmente pra pegar
                # a nova versão.
        except Exception as e:  # noqa: BLE001
            _boot_trace(f"aviso: erro aplicando update pendente: {e}")

        # ----- Auto-recovery: se o boot anterior nunca chegou até a UI
        # (crash em import, tema quebrado, etc.), tenta baixar update
        # novo do GitHub e aplicar sozinho ANTES de tentar importar
        # src.main de novo. Sem isso, um build quebrado deixa o usuário
        # preso sem forma de auto-fix.
        try:
            if _boot_anterior_falhou():
                _boot_trace("boot anterior falhou — iniciando auto-recovery")
                rec_splash = None
                rec_cb = None
                if splash_widget is None:
                    try:
                        _, rec_splash, rec_cb = _criar_splash_update()
                    except Exception as e:  # noqa: BLE001
                        _boot_trace(f"recovery: splash Qt falhou ({e})")
                else:
                    rec_cb = splash_cb
                recuperou = _auto_recovery_boot(splash_cb=rec_cb)
                if rec_splash is not None:
                    try:
                        rec_splash.close()
                    except Exception:  # noqa: BLE001
                        pass
                if recuperou:
                    _boot_trace("recovery aplicado — reiniciando com versão corrigida")
                    _reiniciar_como_novo_exe()
        except Exception as e:  # noqa: BLE001
            _boot_trace(f"recovery: erro inesperado ({e}) — segue com código atual")

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
