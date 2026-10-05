import json
import subprocess
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

    def __init__(self, runtime_dir: Path | None = None):
        self.runtime_dir = runtime_dir or Path(__file__).resolve().parents[2] / "runtime"

    def _binary(self) -> Path:
        name = "nemo-speech.exe" if __import__("sys").platform == "win32" else "nemo-speech"
        path = self.runtime_dir / "nemo-speech" / "bin" / name
        if not path.exists():
            raise RuntimeError(f"NeMo-Speech runtime not found: {path}")
        return path

    def _model(self) -> Path:
        path = self.runtime_dir / "models" / self.model_name
        if not path.exists():
            raise RuntimeError(f"Parakeet model not found: {path}")
        return path

    def _ffmpeg(self) -> Path:
        name = "ffmpeg.exe" if __import__("sys").platform == "win32" else "ffmpeg"
        path = self.runtime_dir / name
        if not path.exists():
            raise RuntimeError(f"FFmpeg not found: {path}")
        return path

    def _to_wav(self, media_path: Path) -> Path:
        wav_path = media_path.with_suffix(".subway.wav")
        command = [
            str(self._ffmpeg()), "-y", "-i", str(media_path),
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg conversion failed:\n{result.stderr[-2000:]}")
        return wav_path

    def transcribe(self, media_path: Path) -> Iterator[TranscriptSegment]:
        wav_path = self._to_wav(media_path)
        command = [
            str(self._binary()), "transcribe", str(wav_path),
            "--model", str(self._model()), "--format", "json",
        ]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        try:
            wav_path.unlink(missing_ok=True)
        except OSError:
            pass
        if result.returncode != 0:
            raise RuntimeError(f"Parakeet transcription failed:\n{result.stderr[-3000:]}")

        payload = json.loads(result.stdout)
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
