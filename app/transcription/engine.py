"""Speech recognition through NVIDIA's NeMo-Speech.cpp runtime and whisper.cpp."""
from __future__ import annotations

import json
import os
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

from .models import WHISPER_VAD, ModelInfo, ModelManager


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


# whisper.cpp builds shipped with Subway, best first. Vulkan also covers NVIDIA cards.
WHISPER_VARIANTS = (
    ("metal", "whisper-metal"),    # macOS: Apple Silicon GPU
    ("vulkan", "whisper-vulkan"),  # Windows: any GPU with a Vulkan driver
    ("cpu", "whisper-cpu"),
)

_SPECIAL_TOKEN = re.compile(r"^(?:\[_[^\]]*\]|<\|[^|]*\|>)$")
_ANNOTATION = re.compile(r"^\s*(?:\[[^\]]*\]|\([^)]*\)|[♪♫\s]+)\s*$")


def _whisper_binary(folder: Path) -> Path:
    name = "whisper-cli.exe" if sys.platform == "win32" else "whisper-cli"
    return folder / "bin" / name


def _utf8(text: str) -> str:
    """Undo surrogateescape: tokens can hold part of a character, whole words cannot."""
    return text.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def parse_whisper(raw: bytes) -> tuple[list[Word], list[TranscriptSegment]]:
    """Words and segments from whisper-cli's full JSON (-ojf).

    Whisper splits text into byte-level tokens, so one token may end in the middle of a
    UTF-8 character (Cyrillic, Arabic). The JSON is read with surrogateescape and the
    bytes of a word are decoded only once the whole word is assembled.
    """
    data = json.loads(raw.decode("utf-8", "surrogateescape"), strict=False)
    words: list[Word] = []
    segments: list[TranscriptSegment] = []
    for segment in data.get("transcription", []) if isinstance(data, dict) else []:
        offsets = segment.get("offsets") or {}
        start, end = _number(offsets.get("from")), _number(offsets.get("to"))
        text = _utf8(str(segment.get("text", ""))).strip()
        if start is None or end is None or not text or _ANNOTATION.match(text):
            continue
        segments.append(TranscriptSegment(text, start / 1000, end / 1000))
        current: list[list] = []  # [text, start, end] per word
        for token in segment.get("tokens", []):
            if not isinstance(token, dict):
                continue
            piece, times = token.get("text", ""), token.get("offsets") or {}
            t_start, t_end = _number(times.get("from")), _number(times.get("to"))
            if not piece or _SPECIAL_TOKEN.match(piece) or t_start is None or t_end is None:
                continue
            if piece.startswith(" ") or not current:
                current.append([piece, t_start, t_end])
            else:
                current[-1][0] += piece
                current[-1][2] = t_end
        for piece, t_start, t_end in current:
            word = _utf8(piece).strip()
            if word and not _ANNOTATION.match(word):
                words.append(Word(word, t_start / 1000, max(t_end, t_start) / 1000))
    return words, segments


class WhisperEngine:
    """Runs OpenAI's Whisper models through whisper.cpp's command-line tool."""

    def __init__(self, runtime_dir: Path, models: ModelManager):
        self.runtime_dir = runtime_dir
        self.models = models

    def installed(self) -> list[tuple[str, Path]]:
        found = []
        for variant, folder in WHISPER_VARIANTS:
            binary = _whisper_binary(self.runtime_dir / folder)
            if binary.exists():
                found.append((variant, binary))
        return found

    def builds(self, device: str) -> list[tuple[str, Path, list[str]]]:
        """Builds to try in order, with extra arguments. A GPU build falls back to the CPU."""
        installed = self.installed()
        if device == "cpu":
            cpu = [(v, b, []) for v, b in installed if v == "cpu"]
            return cpu or [(v, b, ["-ng"]) for v, b in installed]
        gpu = [(v, b, []) for v, b in installed if v != "cpu"]
        cpu = [(v, b, []) for v, b in installed if v == "cpu"]
        if not cpu:
            cpu = [(v, b, ["-ng"]) for v, b in installed[:1]]
        return gpu + cpu

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
        builds = self.builds(device)
        if not builds:
            raise RuntimeError(f"The Whisper runtime was not found in {self.runtime_dir}. "
                               "Please reinstall Subway from the latest release.")
        base = wav.with_name(wav.stem + ".whisper")
        output = base.with_name(base.name + ".json")
        threads = str(max(1, min(os.cpu_count() or 4, 8)))

        def on_line(line: str) -> None:
            match = _PERCENT.search(line)
            if match and progress:
                progress(min(float(match.group(1)) / 100, 1.0))

        failure = ""
        try:
            for variant, binary, extra in builds:
                command = [binary, "-m", model_path, "-f", wav, "-l", language_argument(model, language) or "auto",
                           "-oj", "-ojf", "-of", base, "-pp", "-t", threads, "-sns",
                           "--vad", "-vm", self.models.path_for(WHISPER_VAD), *extra]
                if phrases:
                    command += ["--prompt", ", ".join(phrases)]
                label = "CPU" if variant == "cpu" or extra else variant.capitalize()
                if log:
                    log(f"Recognition device: {label} (whisper.cpp {variant} build)")
                output.unlink(missing_ok=True)
                try:
                    code, text = run(command, cancel, on_line)
                except RuntimeError as exc:  # The build could not start at all.
                    code, text = -1, str(exc)
                if cancel is not None:
                    cancel.check()
                if code == 0 and output.exists():
                    words, segments = parse_whisper(output.read_bytes())
                    if words and max(len(w.text) for w in words) <= 30:
                        return Transcript(words, segments, label)
                    if segments:
                        if log:
                            log("Word timings are unavailable; using Whisper's segments.")
                        return Transcript([], segments, label)
                    raise RuntimeError("No speech was recognized in this file.")
                failure = "\n".join(text.splitlines()[-20:])
                if log:
                    log(f"The {variant} build of whisper.cpp failed (exit code {code}).")
            raise RuntimeError(f"Speech recognition failed:\n{failure}")
        finally:
            try:
                output.unlink(missing_ok=True)
            except OSError:
                pass


class SpeechEngine:
    """Sends each model to the runtime that can run it."""

    def __init__(self, runtime_dir: Path, models: ModelManager):
        self.nemo = NemoSpeechEngine(runtime_dir)
        self.whisper = WhisperEngine(runtime_dir, models)

    def transcribe(self, wav: Path, model: ModelInfo, model_path: Path, **options) -> Transcript:
        engine = self.whisper if model.engine == "whisper" else self.nemo
        return engine.transcribe(wav, model, model_path, **options)
