from __future__ import annotations

import re
from pathlib import Path

from .types import Subtitle

_TIMESTAMP = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})")


def _timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in text.strip().splitlines() if line.strip()]


def format_srt(subtitles: list[Subtitle]) -> str:
    blocks = []
    for index, subtitle in enumerate(subtitles, start=1):
        text = "\n".join(_clean_lines(subtitle.text))
        blocks.append(f"{index}\n{_timestamp(subtitle.start)} --> {_timestamp(subtitle.end)}\n{text}\n")
    return "\n".join(blocks)


def write_srt(subtitles: list[Subtitle], path: Path) -> None:
    path.write_text(format_srt(subtitles), encoding="utf-8")


def _parse_timestamp(value: str) -> float:
    match = _TIMESTAMP.fullmatch(value.strip())
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {value}")
    hours, minutes, seconds, fraction = match.groups()
    millis = int(fraction.ljust(3, "0"))
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + millis / 1000


def parse_srt(text: str) -> list[Subtitle]:
    blocks = re.split(r"\r?\n\s*\r?\n", text.strip())
    subtitles: list[Subtitle] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines()]
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        start_text, end_text = [part.strip() for part in lines[timing_index].split("-->", 1)]
        end_text = end_text.split()[0] if end_text else end_text  # Drop position hints.
        try:
            start = _parse_timestamp(start_text)
            end = _parse_timestamp(end_text)
        except ValueError:
            continue
        subtitle_text = "\n".join(line for line in lines[timing_index + 1:] if line)
        if subtitle_text and end > start:
            subtitles.append(Subtitle(start=start, end=end, text=subtitle_text))
    return subtitles


def read_srt(path: Path) -> list[Subtitle]:
    return parse_srt(path.read_text(encoding="utf-8-sig", errors="replace"))


def translated_path(path: Path, language_code: str) -> Path:
    return path.with_name(f"{path.stem}.{language_code}.srt")
