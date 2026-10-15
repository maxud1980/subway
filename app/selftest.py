"""Checks that the packaged app can do what it needs on this computer.

Run it with `Subway --self-test`. The release workflows run it against the
built app, so packaging mistakes (a missing certificate bundle, a runtime
that cannot start) fail the build instead of reaching users.
"""
from __future__ import annotations

import ssl
import sys
import urllib.request

from pathlib import Path

from app import net
from app.media import find_ffmpeg
from app.paths import config_dir, runtime_dir, user_models_dir
from app.process import run
from app.transcription.engine import RuntimeSelector
from app.transcription.models import MODELS


_report: list[str] = []


def _say(text: str) -> None:
    """Collect a line, and print it when there is somewhere to print.

    A windowed build has no console: sys.stdout is None there, so print()
    raises. The report is written to a file instead.
    """
    _report.append(text)
    try:
        print(text, flush=True)
    except Exception:
        pass


def _check(name: str, function) -> bool:
    try:
        detail = function()
    except Exception as exc:  # noqa: BLE001 - every failure is a result here
        _say(f"FAIL  {name}: {type(exc).__name__}: {exc}")
        return False
    _say(f"ok    {name}: {detail}")
    return True


def _certificates() -> str:
    context = net.ssl_context()
    count = len(context.get_ca_certs())
    if not count:
        raise RuntimeError("no certificate authorities are available")
    source = "certifi bundle" if net._is_empty(ssl.create_default_context()) else "system store"
    return f"{count} authorities from the {source}"


def _range_request(context: ssl.SSLContext) -> tuple[int, int]:
    model = MODELS[0]
    request = urllib.request.Request(model.url, headers={"User-Agent": "Subway/0.2", "Range": "bytes=0-1023"})
    with urllib.request.urlopen(request, timeout=60, context=context) as response:
        return len(response.read(1024)), response.status


def _model_download() -> str:
    """Fetch the first kilobyte of the model file, the request that must work."""
    size, status = _range_request(net.ssl_context())
    if size < 1024:
        raise RuntimeError(f"only {size} bytes arrived")
    return f"{size} bytes from huggingface.co (HTTP {status})"


def _bundled_certificates() -> str:
    """The path a user's computer takes: verify through the bundled certifi file.

    The build machine has its own trust store, so the check above can pass
    there while failing everywhere else. This one fails unless the bundle
    that ships inside the app really works.
    """
    bundle = net._certifi_bundle()
    if not bundle:
        raise RuntimeError("no certifi bundle is packaged with the app")
    size, status = _range_request(ssl.create_default_context(cafile=bundle))
    if size < 1024:
        raise RuntimeError(f"only {size} bytes arrived through the bundled certificates")
    return f"{bundle} verified huggingface.co ({size} bytes, HTTP {status})"


def _runtimes() -> str:
    selector = RuntimeSelector(runtime_dir())
    installed = selector.installed()
    if not installed:
        raise RuntimeError(f"no speech runtime in {runtime_dir()}")
    found = []
    for variant, binary in installed:
        devices = selector.devices(binary)
        if devices is None:
            raise RuntimeError(f"the {variant} runtime does not start")
        found.append(f"{variant}{devices}")
    return f"{', '.join(found)} → {selector.select('auto').label}"


def _ffmpeg() -> str:
    code, output = run([find_ffmpeg(runtime_dir()), "-hide_banner", "-version"], timeout=60)
    if code != 0:
        raise RuntimeError(f"ffmpeg exited with {code}")
    return output.splitlines()[0]


def _folders() -> str:
    for folder in (config_dir(), user_models_dir()):
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write-test"
        probe.write_bytes(b"")
        probe.unlink()
    return f"{config_dir()} is writable"


def main(log_path: str | None = None) -> int:
    _report.clear()
    _say(f"Subway self-test on {sys.platform}")
    results = [
        _check("certificates", _certificates),
        _check("model download", _model_download),
        _check("bundled certificates", _bundled_certificates),
        _check("speech runtime", _runtimes),
        _check("ffmpeg", _ffmpeg),
        _check("user folders", _folders),
    ]
    failed = results.count(False)
    _say("self-test failed" if failed else "self-test passed")
    if log_path:
        try:
            Path(log_path).write_text("\n".join(_report) + "\n", encoding="utf-8")
        except OSError as exc:
            _say(f"could not write {log_path}: {exc}")
            return 1
    return 1 if failed else 0
