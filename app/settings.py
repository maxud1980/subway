from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

APP_NAME = "Subway"
CRYPTPROTECT_UI_FORBIDDEN = 0x01


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> tuple[DATA_BLOB, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data, len(data))
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _app_data_path() -> Path:
    root = os.environ.get("APPDATA")
    if not root:
        raise RuntimeError("Windows user profile directory is unavailable.")
    folder = Path(root) / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "gemini_api_key.bin"


def save_api_key(api_key: str) -> None:
    """Store the API key encrypted with Windows DPAPI for the current user."""
    if not api_key:
        delete_api_key()
        return
    if os.name != "nt":
        raise RuntimeError("Secure API-key storage is supported on Windows only.")

    source, source_buffer = _blob(api_key.encode("utf-8"))
    encrypted = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptProtectData(
        ctypes.byref(source), "Subway Gemini API key", None, None, None,
        CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(encrypted)
    ):
        raise ctypes.WinError()

    try:
        data = ctypes.string_at(encrypted.pbData, encrypted.cbData)
        _app_data_path().write_bytes(data)
    finally:
        kernel32.LocalFree(encrypted.pbData)


def load_api_key() -> str:
    """Load the API key encrypted by the current Windows user."""
    if os.name != "nt":
        return ""
    path = _app_data_path()
    if not path.exists():
        return ""
    encrypted_data = path.read_bytes()
    encrypted, encrypted_buffer = _blob(encrypted_data)
    decrypted = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(
        ctypes.byref(encrypted), None, None, None, None,
        CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(decrypted)
    ):
        # A key protected by another Windows account or installation is unusable here.
        return ""
    try:
        return ctypes.string_at(decrypted.pbData, decrypted.cbData).decode("utf-8")
    finally:
        kernel32.LocalFree(decrypted.pbData)


def delete_api_key() -> None:
    if os.name != "nt":
        return
    try:
        _app_data_path().unlink(missing_ok=True)
    except OSError:
        pass
