import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass
class TranscriptWord:
    text: str
    start: float
    end: float


@dataclass
class TranscriptSegment:
    text: str
    start: float
    end: float
    words: list[TranscriptWord]


class TranscriptionEngine:
    name = "Base"

    def transcribe(self, media_path: Path) -> Iterator[TranscriptSegment]:
        raise NotImplementedError


class ParakeetEngine(TranscriptionEngine):
    """Parakeet through NVIDIA's native NeMo-Speech.cpp runtime."""

    name = "Parakeet TDT v3"
    model_name = "parakeet-tdt-0.6b-v3.q8_0.gguf"

    def __init__(self, runtime_dir: Path | None = None, model_name: str | None = None):
        if runtime_dir is None:
            if getattr(sys, "frozen", False):
                runtime_dir = Path(sys.executable).resolve().parent / "runtime"
            else:
                runtime_dir = Path(__file__).resolve().parents[2] / "runtime"
        self.runtime_dir = runtime_dir
        if model_name:
            self.model_name = model_name

    def _binary(self) -> Path:
        name = "nemo-speech.exe" if sys.platform == "win32" else "nemo-speech"
        path = self.runtime_dir / "nemo-speech" / "bin" / name
        if not path.exists():
            raise RuntimeError(f"NeMo-Speech runtime not found: {path}")
        return path

    def _model(self) -> Path:
        path = self.runtime_dir / "models" / self.model_name
        if not path.exists():
            raise RuntimeError(f"Model not found: {path}")
        return path

    def _ffmpeg(self) -> Path:
        name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        path = self.runtime_dir / name
        if not path.exists():
            raise RuntimeError(f"FFmpeg not found: {path}")
        return path

    def _to_wav(self, media_path: Path) -> Path:
        # Keep temporary audio outside the source directory. This avoids
        # failures when the source video is in a read-only/protected folder.
        temp_dir = Path(tempfile.gettempdir()) / "Subway"
        temp_dir.mkdir(parents=True, exist_ok=True)
        wav_path = temp_dir / f"{media_path.stem}-{id(media_path)}.wav"

        command = [
            str(self._ffmpeg()),
            "-hide_banner",
            "-loglevel", "error",
            "-nostdin",
            "-y",
            "-i", str(media_path),
            "-map", "0:a:0?",
            "-vn",
            "-sn",
            "-dn",
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "pcm_s16le",
            str(wav_path),
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise RuntimeError(f"Unable to start FFmpeg: {exc}") from exc

        if result.returncode != 0:
            details = (result.stderr or result.stdout).strip()
            if not details:
                details = f"FFmpeg exited with code {result.returncode}."
            raise RuntimeError(f"FFmpeg conversion failed:\n{details[-4000:]}")

        if not wav_path.exists() or wav_path.stat().st_size < 44:
            raise RuntimeError("FFmpeg did not produce an audio file. The selected media may contain no audio track.")

        return wav_path

    def transcribe(self, media_path: Path) -> Iterator[TranscriptSegment]:
        wav_path = self._to_wav(media_path)
        try:
            command = [
                str(self._binary()), "transcribe", str(wav_path),
                "--model", str(self._model()), "--format", "json",
            ]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0:
                raise RuntimeError(f"Parakeet transcription failed:\n{result.stderr[-3000:]}")

            try:
                payload = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "Parakeet returned invalid JSON.\n\n"
                    f"Output:\n{result.stdout[-3000:]}"
                ) from exc

            for item in payload.get("segments", []) if isinstance(payload, dict) else []:
                words = [
                    TranscriptWord(
                        str(word.get("text", word.get("word", ""))).strip(),
                        float(word.get("start", 0)),
                        float(word.get("end", 0)),
                    )
                    for word in item.get("words", [])
                    if word.get("text", word.get("word", "")).strip()
                ]
                start = float(item.get("start", words[0].start if words else 0))
                end = float(item.get("end", words[-1].end if words else 0))
                text = str(item.get("text", "")).strip()
                if text and end > start:
                    yield TranscriptSegment(text, start, end, words)
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except OSError:
                pass
