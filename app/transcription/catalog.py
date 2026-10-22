"""Online list of recognition models, so new model versions reach users without a new Subway build.

models.json in the repository lists the newest version of each model. Subway reads it at
startup, keeps a copy for offline use, and offers to download a version it does not have.
Each entry is pinned to a Hugging Face revision and a SHA-256 checksum like the built-in list.
"""
from __future__ import annotations

import json
import re
import urllib.request

from app.net import urlopen
from app.paths import config_dir

from .models import ModelInfo

CATALOG_URL = "https://raw.githubusercontent.com/maxud1980/subway/main/models.json"

_ID = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,63}$")
_REPO = re.compile(r"^[A-Za-z0-9][\w.\-]*/[\w.\-]+$")
_FILENAME = re.compile(r"^[\w.\-]+\.gguf$")
_WHISPER_FILENAME = re.compile(r"^[\w.\-]+\.(?:bin|gguf)$")
_ENGINES = ("nemo", "whisper")
_REVISION = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CODE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,4})?$")


def _text(entry: dict, key: str, limit: int = 300) -> str:
    value = entry.get(key, "")
    return value.strip()[:limit] if isinstance(value, str) else ""


def _codes(entry: dict, key: str) -> tuple[str, ...]:
    values = entry.get(key, [])
    if not isinstance(values, list):
        return ()
    return tuple(v for v in values if isinstance(v, str) and _CODE.match(v))


def parse_entry(entry) -> ModelInfo | None:
    """A catalog entry as ModelInfo, or None when anything needed is missing or malformed."""
    if not isinstance(entry, dict):
        return None
    model_id, name = _text(entry, "id"), _text(entry, "name", 80)
    repo, revision = _text(entry, "repo"), _text(entry, "revision")
    filename, sha256 = _text(entry, "filename"), _text(entry, "sha256")
    size = entry.get("size")
    engine = _text(entry, "engine") or "nemo"
    filename_pattern = _WHISPER_FILENAME if engine == "whisper" else _FILENAME
    if not (_ID.match(model_id) and name and _REPO.match(repo) and _REVISION.match(revision)
            and engine in _ENGINES and filename_pattern.match(filename) and _SHA256.match(sha256)
            and isinstance(size, int) and not isinstance(size, bool) and size > 0):
        return None
    return ModelInfo(
        id=model_id, name=name, repo=repo, revision=revision, filename=filename, size=size, sha256=sha256,
        languages=_text(entry, "languages"),
        language_codes=_codes(entry, "language_codes"),
        recognizes=_codes(entry, "recognizes"),
        version=_text(entry, "version", 40),
        notes=_text(entry, "notes", 500),
        min_app_version=_text(entry, "min_app_version", 20),
        engine=engine,
    )


def parse_catalog(data) -> list[ModelInfo]:
    entries = data.get("models") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return []
    return [model for model in map(parse_entry, entries) if model is not None]


def _cache_path():
    return config_dir() / "models.json"


def load_cached() -> list[ModelInfo]:
    try:
        return parse_catalog(json.loads(_cache_path().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return []


def fetch(timeout: float = 10) -> list[ModelInfo]:
    """Download the catalog and keep a copy for the next start. Raises on network errors."""
    request = urllib.request.Request(CATALOG_URL, headers={"User-Agent": "Subway-Model-Catalog"})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(1024 * 1024)
    data = json.loads(raw.decode("utf-8"))
    models = parse_catalog(data)
    if models:
        try:
            _cache_path().write_bytes(raw)
        except OSError:
            pass
    return models
