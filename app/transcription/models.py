from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from app.languages import base_language
from app.net import urlopen
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
    recognizes: tuple[str, ...] = ()  # Languages the model knows; empty = those of language_codes.
    version: str = ""  # Shown to the user, e.g. "2025-08".
    notes: str = ""  # What changed in this version.
    min_app_version: str = ""  # Older Subway builds cannot run it (new runtime needed).
    store_as: str = ""  # Local file name when it differs from `filename`.
    engine: str = "nemo"  # Runtime that runs it: "nemo" (NeMo-Speech.cpp) or "whisper" (whisper.cpp).

    @property
    def url(self) -> str:
        return f"https://huggingface.co/{self.repo}/resolve/{self.revision}/{self.filename}"

    @property
    def size_mb(self) -> int:
        return round(self.size / 1024 / 1024)

    @property
    def local_filename(self) -> str:
        return self.store_as or self.filename

    @property
    def supports_language(self) -> bool:
        """True when the spoken language can be passed to the model."""
        return bool(self.language_codes)

    @property
    def recognized_languages(self) -> frozenset[str]:
        return frozenset(base_language(code) for code in (self.recognizes or self.language_codes))

    def recognizes_language(self, code: str) -> bool:
        return base_language(code) in self.recognized_languages


# Codes accepted by whisper.cpp's --language.
WHISPER_LANGUAGES = (
    "en", "zh", "de", "es", "ru", "ko", "fr", "ja", "pt", "tr", "pl", "ca", "nl", "ar", "sv", "it", "id",
    "hi", "fi", "vi", "he", "uk", "el", "ms", "cs", "ro", "da", "hu", "ta", "no", "th", "ur", "hr", "bg",
    "lt", "la", "mi", "ml", "cy", "sk", "te", "fa", "lv", "bn", "sr", "az", "sl", "kn", "et", "mk", "br",
    "eu", "is", "hy", "ne", "mn", "bs", "kk", "sq", "sw", "gl", "mr", "pa", "si", "km", "sn", "yo", "so",
    "af", "oc", "ka", "be", "tg", "sd", "gu", "am", "yi", "lo", "uz", "fo", "ht", "ps", "tk", "nn", "mt",
    "sa", "lb", "my", "bo", "tl", "mg", "as", "tt", "haw", "ln", "ha", "ba", "jw", "su", "yue",
)

# Silero voice activity detection for whisper.cpp: Whisper invents text over music and
# silence, so only the parts with speech are recognized. Downloaded with every Whisper model.
WHISPER_VAD = ModelInfo(
    id="silero-vad",
    name="Silero VAD v6.2.0",
    repo="ggml-org/whisper-vad",
    revision="9ffd54a1e1ee413ddf265af9913beaf518d1639b",
    filename="ggml-silero-v6.2.0.bin",
    size=885098,
    sha256="2aa269b785eeb53a82983a20501ddf7c1d9c48e33ab63a41391ac6c9f7fb6987",
    languages="",
    engine="vad",
)

# NVIDIA models are pinned to the same revisions and checksums as NeMo-Speech.cpp's model index.
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
        recognizes=(
            "bg", "hr", "cs", "da", "nl", "en", "et", "fi", "fr", "de", "el", "hu", "it",
            "lv", "lt", "mt", "pl", "pt", "ro", "sk", "sl", "es", "sv", "ru", "uk",
        ),
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
    ModelInfo(
        id="whisper-large-v3-turbo",
        name="Whisper large-v3-turbo — 0.8B",
        repo="ggerganov/whisper.cpp",
        revision="0b364b566045a405be7225ee1e415a073e04da77",
        filename="ggml-large-v3-turbo-q8_0.bin",
        size=874188075,
        sha256="317eb69c11673c9de1e1f0d459b253999804ec71ac4c23c17ecf5fbe24e259a1",
        languages="99 languages incl. Ukrainian, Russian, English, Arabic, Persian, Hebrew, Turkish, Chinese",
        language_codes=WHISPER_LANGUAGES,
        engine="whisper",
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
        # Known versions of each model, newest first. The online catalog adds newer ones.
        self._versions: dict[str, list[ModelInfo]] = {m.id: [m] for m in MODELS}

    def available_models(self) -> list[ModelInfo]:
        return [versions[0] for versions in self._versions.values()]

    def get(self, model_id: str) -> ModelInfo:
        """The newest known version of a model."""
        versions = self._versions.get(model_id) or next(iter(self._versions.values()))
        return versions[0]

    def installed(self, model_id: str) -> ModelInfo | None:
        """The newest version that is on disk."""
        return next((m for m in self._versions.get(model_id, []) if self.is_downloaded(m)), None)

    def update_available(self, model_id: str) -> bool:
        installed = self.installed(model_id)
        return installed is not None and installed != self.get(model_id)

    def add_versions(self, models: list[ModelInfo]) -> list[ModelInfo]:
        """Add catalog entries as the newest versions; returns the ones that were new."""
        added = []
        for model in models:
            versions = self._versions.setdefault(model.id, [])
            if any(v.revision == model.revision and v.filename == model.filename for v in versions):
                continue
            if any(v.local_filename == model.local_filename for v in versions):
                path = Path(model.filename)
                model = replace(model, store_as=f"{path.stem}.{model.revision[:8]}{path.suffix}")
            versions.insert(0, model)
            added.append(model)
        return added

    def _older_files(self, model_id: str) -> list[Path]:
        newest = set(self._candidates(self.get(model_id)))
        return [path for model in self._versions.get(model_id, [])[1:] for path in self._candidates(model)
                if path not in newest and path.is_file()]

    def older_size(self, model_id: str) -> int:
        """Bytes taken by versions older than the newest one."""
        total = 0
        for path in self._older_files(model_id):
            try:
                total += path.stat().st_size
            except OSError:
                pass
        return total

    def remove_older(self, model_id: str) -> None:
        for path in self._older_files(model_id):
            try:
                path.unlink()
            except OSError:
                pass

    def _candidates(self, model: ModelInfo) -> list[Path]:
        return [self.models_dir / model.local_filename, self.fallback_dir / model.local_filename]

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

    @staticmethod
    def companions(model: ModelInfo) -> list[ModelInfo]:
        """Files a model needs besides its own."""
        return [WHISPER_VAD] if model.engine == "whisper" else []

    def _file_downloaded(self, model: ModelInfo) -> bool:
        return any(self._complete(path, model) for path in self._candidates(model))

    def is_downloaded(self, model: ModelInfo) -> bool:
        return all(self._file_downloaded(m) for m in [model, *self.companions(model)])

    def download(
        self,
        model: ModelInfo,
        progress: Callable[[int, int], None] | None = None,
        cancel: CancelToken | None = None,
    ) -> Path:
        """Download a model and the files it needs, with resume support and SHA-256 verification."""
        for companion in self.companions(model):
            if not self._file_downloaded(companion):
                self._download_file(companion, None, cancel)
        return self._download_file(model, progress, cancel)

    def _download_file(
        self,
        model: ModelInfo,
        progress: Callable[[int, int], None] | None,
        cancel: CancelToken | None,
    ) -> Path:
        folder = self.models_dir if _writable(self.models_dir) else self.fallback_dir
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / model.local_filename
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
            try:
                response = urlopen(request, timeout=60)
            except urllib.error.HTTPError as exc:
                raise RuntimeError(
                    f"huggingface.co refused the download ({exc.code} {exc.reason}). "
                    "The model may have moved; check for a Subway update."
                ) from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(
                    f"Could not reach huggingface.co: {exc.reason}. "
                    "Check your internet connection, VPN or firewall and try again."
                ) from exc
            with response:
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
