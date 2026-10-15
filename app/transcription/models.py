from __future__ import annotations

import hashlib
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.paths import models_live_in_app_folder, runtime_dir, user_models_dir
from app.process import CancelToken, Cancelled


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str
    repo: str
    revision: str
    filename: str
    size: int  # bytes
    sha256: str
    languages: str
    language_codes: tuple[str, ...] = ()  # Codes accepted by --language; empty = no choice.

    @property
    def url(self) -> str:
        return f"https://huggingface.co/{self.repo}/resolve/{self.revision}/{self.filename}"

    @property
    def size_mb(self) -> int:
        return round(self.size / 1024 / 1024)

    @property
    def supports_language(self) -> bool:
        return bool(self.language_codes)


# Pinned to the same revisions and checksums as NeMo-Speech.cpp's model index.
MODELS = [
    ModelInfo(
        id="parakeet-tdt-v3",
        name="Parakeet TDT v3 — 0.6B",
        repo="nvidia/parakeet-tdt-0.6b-v3",
        revision="541d1f99c6b0c3cd0b11a95167540bb8edefd82b",
        filename="parakeet-tdt-0.6b-v3.q8_0.gguf",
        size=713975456,
        sha256="e3880d0aaaaf2c308ea2c35016b2b895c423eb3fda924c1b463d1c19b7f4d32e",
        languages="25 European languages, including Ukrainian and Russian",
    ),
    ModelInfo(
        id="nemotron-3.5-asr",
        name="Nemotron 3.5 ASR — 0.6B",
        repo="nvidia/nemotron-3.5-asr-streaming-0.6b",
        revision="1c8deaecc64b91f034d73e08dd8b64625eb3395d",
        filename="nemotron-3.5-asr-streaming-0.6b.q8_0.gguf",
        size=741548352,
        sha256="a5c435f294eea8f88ce68dd27b8c3bfea7f777cb2fbba04fcd30eaa555f429ae",
        languages="40 languages incl. Ukrainian, Russian, English, Arabic, Hindi, Japanese, Chinese",
        language_codes=(
            "en-US", "en-GB", "es-US", "es-ES", "fr-FR", "fr-CA", "it-IT", "pt-BR", "pt-PT",
            "nl-NL", "de-DE", "tr-TR", "ru-RU", "ar-AR", "hi-IN", "ja-JP", "ko-KR", "vi-VN",
            "uk-UA", "pl-PL", "sv-SE", "cs-CZ", "nb-NO", "da-DK", "bg-BG", "fi-FI", "hr-HR",
            "sk-SK", "zh-CN", "hu-HU", "ro-RO", "et-EE",
        ),
    ),
]


def get_model(model_id: str) -> ModelInfo:
    return next((m for m in MODELS if m.id == model_id), MODELS[0])


def default_runtime_dir() -> Path:
    return runtime_dir()


def _writable(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write-test"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


class ModelManager:
    def __init__(self, runtime_dir: Path | None = None):
        self.runtime_dir = runtime_dir or default_runtime_dir()
        # Models live beside the app when that folder is writable (portable
        # install), otherwise in the user's profile (e.g. Program Files).
        self.models_dir = self.runtime_dir / "models"
        self.fallback_dir = user_models_dir()
        if not models_live_in_app_folder():
            self.models_dir = self.fallback_dir

    def available_models(self) -> list[ModelInfo]:
        return MODELS

    def _candidates(self, model: ModelInfo) -> list[Path]:
        return [self.models_dir / model.filename, self.fallback_dir / model.filename]

    def path_for(self, model: ModelInfo) -> Path:
        for path in self._candidates(model):
            if self._complete(path, model):
                return path
        return self._candidates(model)[0]

    @staticmethod
    def _complete(path: Path, model: ModelInfo) -> bool:
        try:
            return path.is_file() and path.stat().st_size == model.size
        except OSError:
            return False

    def is_downloaded(self, model: ModelInfo) -> bool:
        return any(self._complete(path, model) for path in self._candidates(model))

    def download(
        self,
        model: ModelInfo,
        progress: Callable[[int, int], None] | None = None,
        cancel: CancelToken | None = None,
    ) -> Path:
        """Download with resume support and SHA-256 verification."""
        folder = self.models_dir if _writable(self.models_dir) else self.fallback_dir
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / model.filename
        partial = target.with_suffix(target.suffix + ".download")

        digest = hashlib.sha256()
        received = 0
        if partial.exists():
            if partial.stat().st_size > model.size:
                partial.unlink()
            else:
                with partial.open("rb") as existing:
                    for block in iter(lambda: existing.read(4 * 1024 * 1024), b""):
                        digest.update(block)
                        received += len(block)

        if received < model.size:
            headers = {"User-Agent": "Subway/0.2"}
            if received:
                headers["Range"] = f"bytes={received}-"
            request = urllib.request.Request(model.url, headers=headers)
            with urllib.request.urlopen(request, timeout=60) as response:
                if received and response.status != 206:
                    # Server ignored the range request: start over.
                    digest = hashlib.sha256()
                    received = 0
                    mode = "wb"
                else:
                    mode = "ab" if received else "wb"
                with partial.open(mode) as output:
                    while True:
                        if cancel is not None and cancel.cancelled:
                            raise Cancelled()
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        digest.update(chunk)
                        received += len(chunk)
                        if progress:
                            progress(received, model.size)

        if received != model.size or digest.hexdigest() != model.sha256:
            partial.unlink(missing_ok=True)
            raise RuntimeError(
                f"The downloaded model is damaged (size {received} of {model.size} bytes "
                "or checksum mismatch). Please try again."
            )
        partial.replace(target)
        return target
