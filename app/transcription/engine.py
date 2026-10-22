"""Speech recognition through NVIDIA's native NeMo-Speech.cpp runtime."""
from __future__ import annotations

import json
import re
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.languages import base_language
from app.process import CancelToken, run
from app.subtitles.srt import read_srt
from app.subtitles.types import Word

from .models import ModelInfo


@dataclass
class TranscriptSegment:
    text: str
    start: float
    end: float
    words: list[Word] = field(default_factory=list)


@dataclass
class Transcript:
    words: list[Word]
    segments: list[TranscriptSegment]  # Used only when word timings are unavailable.
    backend: str = ""


# Runtime builds shipped in the Windows package, best first.
RUNTIME_VARIANTS = (
    ("cuda", "nemo-speech"),          # Windows: NVIDIA
    ("metal", "nemo-speech-metal"),   # macOS: Apple Silicon GPU
    ("vulkan", "nemo-speech-vulkan"),  # Windows: AMD / Intel GPUs
    ("cpu", "nemo-speech-cpu"),
)
DEVICE_KINDS = ("cuda", "metal", "vulkan", "cpu")

_LANG_TAG = re.compile(r"<[a-z]{2,3}(?:-[A-Za-z]{2,4})?>")
_PERCENT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s?%")


@dataclass
class Backend:
    binary: Path
    device: str  # value for --device
    label: str


def _binary_in(folder: Path) -> Path:
    name = "nemo-speech.exe" if sys.platform == "win32" else "nemo-speech"
    return folder / "bin" / name


class RuntimeSelector:
    """Finds a runtime build and device that work on this computer."""

    def __init__(self, runtime_dir: Path):
        self.runtime_dir = runtime_dir
        self._cache: dict[Path, list[str] | None] = {}
        self._lock = threading.Lock()

    def installed(self) -> list[tuple[str, Path]]:
        found = []
        for variant, folder in RUNTIME_VARIANTS:
            binary = _binary_in(self.runtime_dir / folder)
            if binary.exists():
                found.append((variant, binary))
        return found

    def devices(self, binary: Path) -> list[str] | None:
        """Device kinds reported by `nemo-speech doctor`, or None if it cannot run."""
        with self._lock:
            if binary in self._cache:
                return self._cache[binary]
        try:
            code, output = run([binary, "doctor"], timeout=60)
            kinds = parse_doctor(output) if code == 0 else None
        except Exception:
            kinds = None
        with self._lock:
            self._cache[binary] = kinds
        return kinds

    def select(self, preference: str = "auto") -> Backend:
        installed = self.installed()
        if not installed:
            raise RuntimeError(
                f"NeMo-Speech runtime not found in {self.runtime_dir}. "
                "Please reinstall Subway from the release ZIP."
            )
        wanted = [preference] if preference in DEVICE_KINDS else list(DEVICE_KINDS)
        working: list[tuple[str, Path, list[str]]] = []
        for variant, binary in installed:
            kinds = self.devices(binary)
            if kinds is not None:
                working.append((variant, binary, kinds))
        if not working:
            hint = ("Make sure the GPU driver is up to date." if sys.platform == "win32"
                    else "Reinstall Subway; the runtime inside the app may be damaged or blocked by the system.")
            raise RuntimeError("The speech recognition runtime could not start on this computer. " + hint)
        for kind in wanted:
            if preference == "auto" and kind == "cpu":
                break  # No GPU was recognized: let the best working build decide by itself.
            for variant, binary, kinds in working:
                if kind in kinds:
                    return Backend(binary, kind, f"{kind.upper()} ({variant} build)")
        if preference != "auto":
            raise RuntimeError(f"No {preference.upper()} device was found. Choose another device in Settings.")
        variant, binary, _ = working[0]
        return Backend(binary, "auto", f"automatic ({variant} build)")


def parse_doctor(output: str) -> list[str]:
    """Extract device kinds from the `Devices:` section of `nemo-speech doctor`."""
    kinds: list[str] = []
    in_devices = False
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("devices"):
            in_devices = True
            continue
        if in_devices:
            match = re.match(r"\[\d+\]\s+(\S+)", stripped)
            if not match:
                if stripped and not line.startswith((" ", "\t")):
                    in_devices = False
                continue
            name = match.group(1).lower()
            # ggml names devices CUDA0, Vulkan0, MTL0 (Metal), CPU …
            for kind, prefixes in (("cuda", ("cuda",)), ("vulkan", ("vulkan",)), ("metal", ("metal", "mtl")), ("cpu", ("cpu",))):
                if name.startswith(prefixes) and kind not in kinds:
                    kinds.append(kind)
    return kinds


def _strip_tags(text: str) -> str:
    return _LANG_TAG.sub("", text).strip()


def _number(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_words(data, duration: float = 0.0) -> list[Word]:
    """Find timed words anywhere in NeMo-Speech JSON output."""
    words: list[Word] = []

    def visit(node) -> None:
        if isinstance(node, dict):
            for key in ("words", "word_timestamps", "tokens"):
                items = node.get(key)
                if isinstance(items, list) and items and all(isinstance(i, dict) for i in items):
                    parsed = []
                    for item in items:
                        text = item.get("word", item.get("text", item.get("token")))
                        start = _number(item.get("start", item.get("start_time", item.get("start_offset"))))
                        end = _number(item.get("end", item.get("end_time", item.get("end_offset"))))
                        if isinstance(text, str) and start is not None and end is not None:
                            parsed.append(Word(_strip_tags(text), start, end))
                    if parsed:
                        words.extend(parsed)
                        return
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(data)
    words = [w for w in words if w.text]
    if words and duration > 0 and max(w.end for w in words) > duration * 1.5 + 5:
        words = [Word(w.text, w.start / 1000, w.end / 1000) for w in words]  # milliseconds
    words.sort(key=lambda w: w.start)
    return words


def language_argument(model: ModelInfo, language: str) -> str | None:
    """Map a UI language choice ("auto", "uk", "uk-UA") to a model locale."""
    if not model.supports_language:
        return None
    if not language or language == "auto":
        return "auto"
    if language in model.language_codes:
        return language
    base = base_language(language)
    return next((code for code in model.language_codes if base_language(code) == base), "auto")


class NemoSpeechEngine:
    def __init__(self, runtime_dir: Path, selector: RuntimeSelector | None = None):
        self.runtime_dir = runtime_dir
        self.selector = selector or RuntimeSelector(runtime_dir)

    def transcribe(
        self,
        wav: Path,
        model: ModelInfo,
        model_path: Path,
        language: str = "auto",
        device: str = "auto",
        phrases: list[str] | None = None,
        duration: float = 0.0,
        cancel: CancelToken | None = None,
        progress: Callable[[float | None], None] | None = None,
        log: Callable[[str], None] | None = None,
    ) -> Transcript:
        backend = self.selector.select(device)
        if log:
            log(f"Recognition device: {backend.label}")
        output = wav.with_suffix(".json")

        def base(fmt: str, target: Path, with_phrases: bool) -> list:
            command = [backend.binary, "transcribe", wav, "--model", model_path,
                       "--format", fmt, "--output", target, "--force"]
            if backend.device != "auto":
                command += ["--device", backend.device]
            lang = language_argument(model, language)
            if lang:
                command += ["--language", lang]
            if with_phrases:
                for phrase in phrases or []:
                    command += ["--speech-context", phrase]
            return command

        def on_line(line: str) -> None:
            match = _PERCENT.search(line)
            if match and progress:
                progress(min(float(match.group(1)) / 100, 1.0))

        def attempt(fmt: str, target: Path) -> None:
            use_phrases = bool(phrases)
            code, text = run(base(fmt, target, use_phrases), cancel, on_line)
            if code != 0 and use_phrases:
                if log:
                    log("Glossary boosting is not supported by this model; retrying without it.")
                code, text = run(base(fmt, target, False), cancel, on_line)
            if code != 0:
                lines = text.splitlines()
                raise RuntimeError(f"Speech recognition failed (exit code {code}):\n" + "\n".join(lines[-20:]))
            if not target.exists():
                raise RuntimeError("Speech recognition finished without producing a result.\n" + text[-1500:])

        srt = wav.with_suffix(".srt")
        try:
            attempt("json", output)
            try:
                data = json.loads(output.read_text(encoding="utf-8", errors="replace"))
            except ValueError:
                data = None
            words = parse_words(data, duration) if data is not None else []
            if words:
                return Transcript(words, [], backend.label)

            if log:
                log("Word timings are unavailable; using the runtime's subtitle segments.")
            attempt("srt", srt)
            segments = [
                TranscriptSegment(_strip_tags(s.text.replace("\n", " ")), s.start, s.end)
                for s in read_srt(srt)
            ]
            segments = [s for s in segments if s.text]
            if not segments:
                raise RuntimeError("No speech was recognized in this file.")
            return Transcript([], segments, backend.label)
        finally:
            for path in (output, srt):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
