"""FFmpeg helpers: audio extraction, previews and burned-in subtitles."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .process import CancelToken, run

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv", ".flv", ".ts", ".mts", ".m2ts", ".mpg", ".mpeg"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".wma"}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

_DURATION = re.compile(r"Duration:\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
_TIME = re.compile(r"time=\s*(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")


@dataclass
class MediaInfo:
    duration: float = 0.0
    has_video: bool = False
    has_audio: bool = False


def temp_dir() -> Path:
    folder = Path(tempfile.gettempdir()) / "Subway"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def find_ffmpeg(runtime_dir: Path) -> Path:
    name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    bundled = runtime_dir / name
    if bundled.exists():
        return bundled
    found = shutil.which("ffmpeg")
    if found:
        return Path(found)
    raise RuntimeError(f"FFmpeg not found: {bundled}")


def _seconds(match: re.Match) -> float:
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


class _ProgressParser:
    def __init__(self, info: MediaInfo, progress: Callable[[float], None] | None, total: float | None = None):
        self.info = info
        self.progress = progress
        self.total = total
        self.in_input = True

    def __call__(self, line: str) -> None:
        if line.startswith("Output #"):
            self.in_input = False
        if self.in_input:
            duration = _DURATION.search(line)
            if duration and not self.info.duration:
                self.info.duration = _seconds(duration)
            if "Stream #" in line:
                if " Video: " in line and "attached pic" not in line:
                    self.info.has_video = True
                if " Audio: " in line:
                    self.info.has_audio = True
        current = _TIME.search(line)
        total = self.total or self.info.duration
        if current and total and self.progress:
            self.progress(min(_seconds(current) / total, 1.0))


def _fail(code: int, output: str, what: str) -> RuntimeError:
    lines = [line for line in output.splitlines() if not line.startswith(("frame=", "size="))]
    details = "\n".join(lines[-25:]) or f"exit code {code}"
    return RuntimeError(f"{what} failed:\n{details}")


def probe(ffmpeg: Path, media: Path) -> MediaInfo:
    info = MediaInfo()
    run([ffmpeg, "-hide_banner", "-nostdin", "-i", media], on_output=_ProgressParser(info, None), timeout=60)
    return info


def to_wav(ffmpeg: Path, media: Path, wav: Path, cancel: CancelToken | None = None,
           progress: Callable[[float], None] | None = None) -> MediaInfo:
    """Convert the first audio track to 16 kHz mono PCM, the format ASR models expect."""
    info = MediaInfo()
    command = [
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-stats",
        "-i", media,
        "-map", "0:a:0?", "-vn", "-sn", "-dn",
        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        wav,
    ]
    code, output = run(command, cancel, _ProgressParser(info, progress))
    if code != 0:
        raise _fail(code, output, "FFmpeg audio conversion")
    if not wav.exists() or wav.stat().st_size <= 44:
        raise RuntimeError("The selected file has no audio track.")
    if not info.duration:
        info.duration = max(0.0, (wav.stat().st_size - 44) / 32000)
    return info


def extract_clip(ffmpeg: Path, media: Path, start: float, end: float, wav: Path) -> Path:
    start = max(0.0, start)
    duration = max(0.2, end - start)
    command = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
               "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", media,
               "-vn", "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", wav]
    code, output = run(command, timeout=60)
    if code != 0 or not wav.exists():
        raise _fail(code, output, "Audio preview")
    return wav


def burn_subtitles(ffmpeg: Path, video: Path, ass_file: Path, output: Path, duration: float,
                   cancel: CancelToken | None = None, progress: Callable[[float], None] | None = None) -> Path:
    """Render a copy of the video with subtitles drawn into the picture.

    The subtitle file is copied into a temporary folder and referenced by a
    plain relative name: FFmpeg filter arguments are very hard to escape for
    Windows paths with drive letters, spaces and quotes.
    """
    work = Path(tempfile.mkdtemp(prefix="burn-", dir=temp_dir()))
    try:
        shutil.copyfile(ass_file, work / "subs.ass")
        partial = output.with_name(output.stem + ".part" + output.suffix)
        command = [
            ffmpeg, "-hide_banner", "-nostdin", "-y", "-stats",
            "-i", video,
            "-vf", _ass_filter(),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            partial,
        ]
        info = MediaInfo(duration=duration)
        try:
            code, out = run(command, cancel, _ProgressParser(info, progress, total=duration or None), cwd=work)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        if code != 0:
            partial.unlink(missing_ok=True)
            raise _fail(code, out, "Burning subtitles into the video")
        partial.replace(output)
        return output
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _ass_filter() -> str:
    # The static macOS FFmpeg has no usable fontconfig setup, so point libass
    # at the system font folders where Arial and Cyrillic fonts live.
    if sys.platform == "darwin":
        for folder in ("/System/Library/Fonts/Supplemental", "/Library/Fonts", "/System/Library/Fonts"):
            if Path(folder).is_dir():
                return f"ass=subs.ass:fontsdir={folder}"
    return "ass=subs.ass"


_player: subprocess.Popen | None = None


def play_wav(path: Path) -> bool:
    """Play a WAV file asynchronously. Returns False where unsupported."""
    global _player
    if sys.platform == "win32":
        import winsound  # type: ignore

        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        return True
    if sys.platform == "darwin":
        stop_playback()
        _player = subprocess.Popen(["/usr/bin/afplay", str(path)], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    return False


def stop_playback() -> None:
    global _player
    if sys.platform == "win32":
        import winsound  # type: ignore

        winsound.PlaySound(None, 0)
    elif _player is not None:
        try:
            _player.terminate()
        except Exception:
            pass
        _player = None
