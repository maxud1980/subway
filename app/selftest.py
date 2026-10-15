"""Checks that the packaged app can do what it needs on this computer.

Run it with `Subway --self-test`. The release workflows run it against the
built app, so packaging mistakes (a missing certificate bundle, a runtime
that cannot start) fail the build instead of reaching users.
"""
from __future__ import annotations

import ssl
import sys
import urllib.request

from app import net
from app.media import find_ffmpeg
from app.paths import config_dir, runtime_dir, user_models_dir
from app.process import run
from app.transcription.engine import RuntimeSelector
from app.transcription.models import MODELS


def _check(name: str, function) -> bool:
    try:
        detail = function()
    except Exception as exc:  # noqa: BLE001 - every failure is a result here
        print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
        return False
    print(f"ok    {name}: {detail}")
    return True


def _certificates() -> str:
    context = net.ssl_context()
    count = len(context.get_ca_certs())
    if not count:
        raise RuntimeError("no certificate authorities are available")
    source = "certifi bundle" if net._is_empty(ssl.create_default_context()) else "system store"
    return f"{count} authorities from the {source}"


def _model_download() -> str:
    """Fetch the first kilobyte of the model file, the request that must work."""
    model = MODELS[0]
    request = urllib.request.Request(model.url, headers={"User-Agent": "Subway/0.2", "Range": "bytes=0-1023"})
    with net.urlopen(request, timeout=60) as response:
        data = response.read(1024)
    if len(data) < 1024:
        raise RuntimeError(f"only {len(data)} bytes arrived")
    return f"{len(data)} bytes from huggingface.co (HTTP {response.status})"


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


def main() -> int:
    print(f"Subway self-test on {sys.platform}")
    results = [
        _check("certificates", _certificates),
        _check("model download", _model_download),
        _check("speech runtime", _runtimes),
        _check("ffmpeg", _ffmpeg),
        _check("user folders", _folders),
    ]
    failed = results.count(False)
    print("self-test failed" if failed else "self-test passed")
    return 1 if failed else 0
