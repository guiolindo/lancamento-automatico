"""
Criptografia at-rest da chave da API Gemini (build-85).

Motivação: até o build-84, `gemini_api_key` era gravado em plain text
em `settings.json` e o `SetupDialog` tinha botão 'Mostrar chave' que
exibia o valor. Qualquer pessoa com acesso ao PC do operador conseguia
pegar a chave — abusar de uma chave paga estoura o cartão.

Solução: encriptar com **Windows DPAPI** (`CryptProtectData`), a mesma
API que Chrome/Edge usa pra cookies. A chave só pode ser
descriptografada:
  - Pelo MESMO usuário Windows (login com senha)
  - Na MESMA máquina
Sem servidor, sem dependência nova, sem chave-mestra pra vazar.

Fallback: em dev/Linux (fora do Windows), usa scramble XOR com uma
key derivada do hostname + username. Não é criptografia real — só
evita leitura casual. Prod é 100% Windows, então DPAPI é o real deal.

Formato do valor guardado no settings.json:
    "gemini_api_key_enc": "<base64 do ciphertext>"

A chave antiga em plain text (`gemini_api_key`) é migrada automatica-
mente pra `gemini_api_key_enc` na primeira leitura pós-upgrade.
"""

from __future__ import annotations

import base64
import sys

from .logger import log


# ---------- Windows DPAPI (produção) ----------

def _dpapi_encrypt(data: bytes) -> bytes:
    """CryptProtectData via ctypes. Bytes cifrados só descriptografam
    no mesmo usuário/máquina. Levanta OSError se a chamada falhar."""
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    buf_in = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf_in, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()

    if not crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        None, None, None, None,
        0,  # flags — 0 pra permitir uso em serviços/sessões
        ctypes.byref(blob_out),
    ):
        raise OSError(f"CryptProtectData falhou (LastError={ctypes.get_last_error()})")

    result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    kernel32.LocalFree(blob_out.pbData)
    return result


def _dpapi_decrypt(data: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    buf_in = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf_in, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()

    if not crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None, None, None, None,
        0,
        ctypes.byref(blob_out),
    ):
        raise OSError(f"CryptUnprotectData falhou (LastError={ctypes.get_last_error()})")

    result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    kernel32.LocalFree(blob_out.pbData)
    return result


# ---------- Fallback dev/Linux (não é seguro, só scramble) ----------

def _fallback_key() -> bytes:
    """Deriva um bytes-key repetível a partir de hostname+user. Não é
    criptografia — só evita leitura casual em dev. Prod é Windows."""
    import getpass
    import socket
    seed = f"{socket.gethostname()}|{getpass.getuser()}|autoconferi-v1".encode("utf-8")
    # Estica pra 32 bytes ciclando
    return (seed * (32 // len(seed) + 1))[:32]


def _fallback_encrypt(data: bytes) -> bytes:
    key = _fallback_key()
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _fallback_decrypt(data: bytes) -> bytes:
    # XOR é auto-inverso
    return _fallback_encrypt(data)


# ---------- API pública ----------

def encrypt_str(plaintext: str) -> str:
    """Cifra e devolve base64 pronto pra JSON. Vazio → vazio (sentinela)."""
    if not plaintext:
        return ""
    data = plaintext.encode("utf-8")
    try:
        if sys.platform == "win32":
            cipher = _dpapi_encrypt(data)
        else:
            cipher = _fallback_encrypt(data)
        return base64.b64encode(cipher).decode("ascii")
    except Exception:  # noqa: BLE001
        log.exception("encrypt_str falhou — devolvendo string vazia por segurança")
        return ""


def decrypt_str(b64_cipher: str) -> str:
    """Recebe base64 do settings.json, devolve plaintext. Vazio → vazio.
    Se algo falhar (corrompido, usuário Windows diferente), devolve
    vazio — o operador vai ver a UI pedir chave de novo, o que é o
    fallback correto."""
    if not b64_cipher:
        return ""
    try:
        cipher = base64.b64decode(b64_cipher)
        if sys.platform == "win32":
            plain = _dpapi_decrypt(cipher)
        else:
            plain = _fallback_decrypt(cipher)
        return plain.decode("utf-8")
    except Exception as e:  # noqa: BLE001
        log.warning("decrypt_str falhou (%s: %s) — chave provavelmente veio de outro usuário/máquina",
                    type(e).__name__, e)
        return ""
