"""HTTPS requests that also work inside a frozen app.

A PyInstaller app carries its own Python but not a certificate store: the
OpenSSL paths are baked in at build time and do not exist on the user's
computer, so every HTTPS request fails with "unable to get local issuer
certificate". When the default store comes up empty, use the certifi bundle
shipped inside the app instead.
"""
from __future__ import annotations

import ssl
import urllib.request
from pathlib import Path

_context: ssl.SSLContext | None = None


def _certifi_bundle() -> str | None:
    try:
        import certifi

        path = certifi.where()
    except Exception:
        return None
    return path if path and Path(path).is_file() else None


def _is_empty(context: ssl.SSLContext) -> bool:
    try:
        return not context.get_ca_certs()
    except Exception:
        return True


def ssl_context() -> ssl.SSLContext:
    global _context
    if _context is None:
        context = ssl.create_default_context()
        if _is_empty(context):
            bundle = _certifi_bundle()
            if bundle:
                context = ssl.create_default_context(cafile=bundle)
        _context = context
    return _context


def urlopen(request, timeout: float = 60):
    """urllib.request.urlopen with a usable certificate store."""
    return urllib.request.urlopen(request, timeout=timeout, context=ssl_context())
