import re
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
            raise RuntimeError(
                "FFmpeg did not produce an audio file. "
                "The selected media may contain no audio track."
            )

        return wav_path

    @staticmethod
    def _parse_timestamp(value: str) -> float:
        match = re.fullmatch(r"(\d+):(\d{2}):(\d{2})[,.](\d{3})", value.strip())
        if not match:
            raise ValueError(f"Invalid SRT timestamp: {value}")
        hours, minutes, seconds, millis = map(int, match.groups())
        return hours * 3600 + minutes * 60 + seconds + millis / 1000

    @classmethod
    def _read_srt(cls, path: Path) -> list[TranscriptSegment]:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        blocks = re.split(r"\r?\n\s*\r?\n", text.strip())
        segments: list[TranscriptSegment] = []

        for block in blocks:
            lines = [line.strip() for line in block.splitlines()]
            if len(lines) < 3:
                continue

            timing_index = next(
                (i for i, line in enumerate(lines) if " --> " in line),
                None,
            )
            if timing_index is None:
                continue

            start_text, end_text = [part.strip() for part in lines[timing_index].split(" --> ", 1)]
            start = cls._parse_timestamp(start_text)
            end = cls._parse_timestamp(end_text)
            subtitle_text = " ".join(lines[timing_index + 1:]).strip()

            if subtitle_text and end > start:
                segments.append(TranscriptSegment(subtitle_text, start, end, []))

        return segments

    def transcribe(self, media_path: Path) -> Iterator[TranscriptSegment]:
        wav_path = self._to_wav(media_path)
        output_srt = wav_path.with_suffix(".srt")

        try:
            command = [
                str(self._binary()),
                "transcribe",
                str(wav_path),
                "--model", str(self._model()),
                "--format", "srt",
                "--output", str(output_srt),
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
                details = (result.stderr or result.stdout).strip()
                raise RuntimeError(
                    f"Parakeet transcription failed (exit code {result.returncode}):\n"
                    f"{details[-4000:]}"
                )

            if not output_srt.exists():
                raise RuntimeError(
                    "Parakeet completed without producing an SRT file.\n\n"
                    f"Output:\n{result.stdout[-2000:]}"
                )

            segments = self._read_srt(output_srt)
            if not segments:
                raise RuntimeError(
                    "Parakeet returned an empty transcript. "
                    "The model may not have detected speech in the selected file."
                )

            yield from segments

        finally:
            for path in (wav_path, output_srt):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
