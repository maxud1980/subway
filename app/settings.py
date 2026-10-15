"""Secure storage for the Gemini API key.

Windows: encrypted with DPAPI for the current user.
macOS: stored in the user's login Keychain.
Other systems (development only): a file readable only by the current user.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
from pathlib import Path

from app.paths import IS_MAC, IS_WINDOWS, config_dir

CRYPTPROTECT_UI_FORBIDDEN = 0x01
KEYCHAIN_SERVICE = "Subway Gemini API key"
KEYCHAIN_ACCOUNT = "Subway"


def _key_file() -> Path:
    return config_dir() / ("gemini_api_key.bin" if IS_WINDOWS else "gemini_api_key")


# -- Windows DPAPI -------------------------------------------------------------
if IS_WINDOWS:
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    def _blob(data: bytes):
        buffer = ctypes.create_string_buffer(data, len(data))
        return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer

    def _dpapi_save(api_key: str) -> None:
        source, _source_buffer = _blob(api_key.encode("utf-8"))
        encrypted = DATA_BLOB()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        if not crypt32.CryptProtectData(ctypes.byref(source), "Subway Gemini API key", None, None, None,
                                        CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(encrypted)):
            raise ctypes.WinError()
        try:
            _key_file().write_bytes(ctypes.string_at(encrypted.pbData, encrypted.cbData))
        finally:
            kernel32.LocalFree(encrypted.pbData)

    def _dpapi_load() -> str:
        path = _key_file()
        if not path.exists():
            return ""
        encrypted, _buffer = _blob(path.read_bytes())
        decrypted = DATA_BLOB()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        if not crypt32.CryptUnprotectData(ctypes.byref(encrypted), None, None, None, None,
                                          CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(decrypted)):
            return ""  # Protected by another Windows account or installation.
        try:
            return ctypes.string_at(decrypted.pbData, decrypted.cbData).decode("utf-8")
        finally:
            kernel32.LocalFree(decrypted.pbData)


# -- macOS Keychain ------------------------------------------------------------
def _security(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/security", *args], capture_output=True, text=True, timeout=20)


def _keychain_save(api_key: str) -> None:
    result = _security("add-generic-password", "-U", "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE,
                       "-l", KEYCHAIN_SERVICE, "-w", api_key)
    if result.returncode != 0:
        raise RuntimeError(f"Keychain error: {result.stderr.strip() or result.returncode}")


def _keychain_load() -> str:
    result = _security("find-generic-password", "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE, "-w")
    return result.stdout.strip() if result.returncode == 0 else ""


def _keychain_delete() -> None:
    _security("delete-generic-password", "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE)


# -- public API ----------------------------------------------------------------
def save_api_key(api_key: str) -> None:
    api_key = api_key.strip()
    if not api_key:
        delete_api_key()
        return
    if load_api_key() == api_key:
        return
    if IS_WINDOWS:
        _dpapi_save(api_key)
    elif IS_MAC:
        _keychain_save(api_key)
    else:
        path = _key_file()
        path.write_text(api_key, encoding="utf-8")
        os.chmod(path, 0o600)


def load_api_key() -> str:
    try:
        if IS_WINDOWS:
            return _dpapi_load()
        if IS_MAC:
            return _keychain_load()
        path = _key_file()
        return path.read_text(encoding="utf-8").strip() if path.exists() else ""
    except Exception:
        return ""


def delete_api_key() -> None:
    try:
        if IS_MAC:
            _keychain_delete()
        else:
            _key_file().unlink(missing_ok=True)
    except Exception:
        pass
