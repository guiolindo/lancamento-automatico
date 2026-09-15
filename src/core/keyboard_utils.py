"""
Utilitários de teclado — `pyautogui.typewrite` só sabe digitar ASCII
básico. Qualquer caractere fora do teclado US-ANSI vira NADA:
`pyautogui.typewrite("Elétrica")` cai como "Eltrica" (o "é" some).

Solução: pra strings com caracteres não-ASCII, colocamos no clipboard
via API Win32 e mandamos Ctrl+V. Sem dependência nova.

CUIDADO — build-108: TODAS as chamadas Win32 precisam `argtypes` e
`restype` configurados. Sem isso, ctypes assume `c_int` (32-bit), o
que TRUNCA ponteiros HANDLE/HGLOBAL de 64-bit no Windows x64 e causa
`access violation reading 0x…` na próxima vez que o handle é usado.
Bug em prod no build-105/107 — várias notas com valores em `Em curso`
crashavam com esse erro no meio do lote.

ASCII puro continua indo pelo `typewrite` — mais rápido e sem tocar
no clipboard.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Optional


def _eh_ascii_puro(texto: str) -> bool:
    try:
        texto.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


# ---------- Setup dos protótipos Win32 (executa uma vez no import) ----------

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

# user32
_user32.OpenClipboard.argtypes = [wintypes.HWND]
_user32.OpenClipboard.restype = wintypes.BOOL
_user32.CloseClipboard.argtypes = []
_user32.CloseClipboard.restype = wintypes.BOOL
_user32.EmptyClipboard.argtypes = []
_user32.EmptyClipboard.restype = wintypes.BOOL
_user32.GetClipboardData.argtypes = [wintypes.UINT]
_user32.GetClipboardData.restype = wintypes.HANDLE
_user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
_user32.SetClipboardData.restype = wintypes.HANDLE

# kernel32 — HGLOBAL == HANDLE == void* (64-bit no x64)
_kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
_kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
_kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalLock.restype = ctypes.c_void_p
_kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalUnlock.restype = wintypes.BOOL
_kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalFree.restype = wintypes.HGLOBAL
_kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalSize.restype = ctypes.c_size_t


def _abrir_clipboard(retries: int = 5) -> bool:
    """OpenClipboard pode falhar quando outro processo (Zoom, screenshot)
    tem o clipboard aberto. Retry alguns milissegundos."""
    for _ in range(retries):
        if _user32.OpenClipboard(None):
            return True
        time.sleep(0.05)
    return False


def _ler_clipboard_unicode() -> Optional[str]:
    """Lê o clipboard atual em Unicode. None se vazio ou falhou."""
    if not _abrir_clipboard():
        return None
    try:
        h = _user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        ptr = _kernel32.GlobalLock(h)
        if not ptr:
            return None
        try:
            texto = ctypes.wstring_at(ptr)
        finally:
            _kernel32.GlobalUnlock(h)
        return texto
    finally:
        _user32.CloseClipboard()


def _setar_clipboard_unicode(texto: str) -> bool:
    if not _abrir_clipboard():
        return False
    try:
        _user32.EmptyClipboard()
        # +1 pra terminador NUL do wide string
        n_bytes = (len(texto) + 1) * ctypes.sizeof(ctypes.c_wchar)
        h = _kernel32.GlobalAlloc(GMEM_MOVEABLE, n_bytes)
        if not h:
            return False
        ptr = _kernel32.GlobalLock(h)
        if not ptr:
            _kernel32.GlobalFree(h)
            return False
        try:
            # cria buffer temporário e copia bytes pro handle global
            buf = ctypes.create_unicode_buffer(texto)
            ctypes.memmove(ptr, buf, n_bytes)
        finally:
            _kernel32.GlobalUnlock(h)
        # SetClipboardData toma posse do handle SE der certo. Não damos
        # GlobalFree(h) depois — só em caso de falha do SetClipboardData.
        if not _user32.SetClipboardData(CF_UNICODETEXT, h):
            _kernel32.GlobalFree(h)
            return False
        return True
    finally:
        _user32.CloseClipboard()


def digitar_texto(texto: str, intervalo_ascii: float = 0.003) -> None:
    """Digita `texto` na janela ativa. ASCII puro vai por `pyautogui.typewrite`
    (rápido). Qualquer char não-ASCII força clipboard + Ctrl+V (pyautogui
    ignora acento silenciosamente).

    Salvamos o clipboard atual antes e restauramos depois — se o operador
    tinha algo copiado, não perde.
    """
    import pyautogui

    if not texto:
        return

    if _eh_ascii_puro(texto):
        pyautogui.typewrite(texto, interval=intervalo_ascii)
        return

    backup = _ler_clipboard_unicode()

    ok = _setar_clipboard_unicode(texto)
    if not ok:
        from .logger import log
        log.warning(
            "Falha ao usar clipboard pra texto com acentos — usando typewrite (perde chars)"
        )
        pyautogui.typewrite(texto, interval=intervalo_ascii)
        return

    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.08)

    if backup is not None:
        _setar_clipboard_unicode(backup)
