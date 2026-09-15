"""
Utilitários de teclado — o `pyautogui.typewrite` só sabe digitar ASCII
básico (SendInput com virtual keys). Qualquer caractere fora do teclado
US-ANSI vira NADA: `pyautogui.typewrite("Elétrica")` cai como "Eltrica"
(o "é" some, o "ê" some, o "ç" some).

Solução: pra strings com caracteres não-ASCII, colocamos no clipboard
via API Win32 pura (`OpenClipboard/SetClipboardData`) e mandamos Ctrl+V.
Sem dependência nova (evita adicionar `pyperclip` só pra isso), sem
loop de keystrokes lento, e o RemoteApp/RDP repassa o Ctrl+V como
sequência única que o TOTVS aceita.

ASCII puro continua indo pelo `typewrite` — mais rápido e não precisa
salvar/restaurar clipboard.
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


# ---------- Clipboard Win32 ----------

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def _abrir_clipboard(retries: int = 5) -> bool:
    """OpenClipboard pode falhar se outro processo (Zoom, screenshot) segurou
    ele por milissegundos. Retry algumas vezes antes de desistir."""
    user32 = ctypes.windll.user32
    for _ in range(retries):
        if user32.OpenClipboard(0):
            return True
        time.sleep(0.05)
    return False


def _ler_clipboard_unicode() -> Optional[str]:
    """Lê o clipboard atual em Unicode pra podermos restaurar depois.
    None se não tem texto ou falhou."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if not _abrir_clipboard():
        return None
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        ptr = kernel32.GlobalLock(h)
        if not ptr:
            return None
        try:
            texto = ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(h)
        return texto
    finally:
        user32.CloseClipboard()


def _setar_clipboard_unicode(texto: str) -> bool:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if not _abrir_clipboard():
        return False
    try:
        user32.EmptyClipboard()
        # +1 pra terminador NUL do wide string
        n_bytes = (len(texto) + 1) * ctypes.sizeof(ctypes.c_wchar)
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, n_bytes)
        if not h:
            return False
        ptr = kernel32.GlobalLock(h)
        if not ptr:
            kernel32.GlobalFree(h)
            return False
        try:
            ctypes.memmove(ptr, ctypes.create_unicode_buffer(texto), n_bytes)
        finally:
            kernel32.GlobalUnlock(h)
        if not user32.SetClipboardData(CF_UNICODETEXT, h):
            kernel32.GlobalFree(h)
            return False
        return True
    finally:
        user32.CloseClipboard()


def digitar_texto(texto: str, intervalo_ascii: float = 0.003) -> None:
    """Digita `texto` na janela ativa. ASCII puro vai por `pyautogui.typewrite`
    (rápido). Qualquer caractere não-ASCII (acentos, ç, etc.) força o
    caminho clipboard + Ctrl+V pra evitar o bug do typewrite que ignora
    silenciosamente esses chars.

    A gente salva o clipboard atual antes e restaura depois — se o
    operador tinha algo copiado, não perde.
    """
    import pyautogui

    if not texto:
        return

    if _eh_ascii_puro(texto):
        pyautogui.typewrite(texto, interval=intervalo_ascii)
        return

    # Backup do clipboard atual
    backup = _ler_clipboard_unicode()

    ok = _setar_clipboard_unicode(texto)
    if not ok:
        # Não conseguimos usar clipboard — cai no typewrite mesmo com
        # perda de acento (melhor que nada). Loga só uma vez.
        from .logger import log
        log.warning(
            "Falha ao usar clipboard pra texto com acentos — usando typewrite (vai perder chars)"
        )
        pyautogui.typewrite(texto, interval=intervalo_ascii)
        return

    # Ctrl+V (RemoteApp repassa como sequência única — TOTVS aceita).
    pyautogui.hotkey("ctrl", "v")
    # Dá tempo do paste rodar antes de mexer no clipboard de novo.
    time.sleep(0.08)

    # Restaura clipboard anterior (se tinha algo)
    if backup is not None:
        _setar_clipboard_unicode(backup)
