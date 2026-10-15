"""Subtitle writers for every output format Subway supports."""
from __future__ import annotations

from pathlib import Path

from .srt import format_srt
from .types import Subtitle

FORMATS = {
    "srt": "SRT",
    "vtt": "WebVTT",
    "ass": "ASS",
    "txt": "TXT",
}


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.strip().splitlines() if line.strip()]


def _vtt_time(seconds: float) -> str:
    ms = max(0, round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _ass_time(seconds: float) -> str:
    cs = max(0, round(seconds * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _clock(seconds: float) -> str:
    total = int(max(0, seconds))
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def format_vtt(subtitles: list[Subtitle]) -> str:
    blocks = ["WEBVTT\n"]
    for sub in subtitles:
        text = "\n".join(_lines(sub.text)).replace("-->", "->")
        blocks.append(f"{_vtt_time(sub.start)} --> {_vtt_time(sub.end)}\n{text}\n")
    return "\n".join(blocks)


ASS_HEADER = """[Script Info]
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{size},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,{outline},1,2,80,80,{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def format_ass(subtitles: list[Subtitle], font_size: int = 58) -> str:
    out = [ASS_HEADER.format(size=font_size, outline=3, margin=70)]
    for sub in subtitles:
        text = r"\N".join(line.replace("{", "(").replace("}", ")") for line in _lines(sub.text))
        out.append(f"Dialogue: 0,{_ass_time(sub.start)},{_ass_time(sub.end)},Default,,0,0,0,,{text}\n")
    return "".join(out)


def format_txt(subtitles: list[Subtitle], paragraph_gap: float = 2.0) -> str:
    """Plain transcript split into paragraphs with a time mark for each one."""
    paragraphs: list[tuple[float, list[str]]] = []
    previous_end = None
    for sub in subtitles:
        text = " ".join(_lines(sub.text))
        if not text:
            continue
        if previous_end is None or sub.start - previous_end >= paragraph_gap:
            paragraphs.append((sub.start, []))
        paragraphs[-1][1].append(text)
        previous_end = sub.end
    return "\n\n".join(f"[{_clock(start)}] {' '.join(parts)}" for start, parts in paragraphs) + "\n"


def render(subtitles: list[Subtitle], fmt: str) -> str:
    if fmt == "srt":
        return format_srt(subtitles)
    if fmt == "vtt":
        return format_vtt(subtitles)
    if fmt == "ass":
        return format_ass(subtitles)
    if fmt == "txt":
        return format_txt(subtitles)
    raise ValueError(f"Unknown subtitle format: {fmt}")


def write(subtitles: list[Subtitle], path: Path, fmt: str | None = None) -> Path:
    fmt = fmt or path.suffix.lstrip(".").lower()
    path.write_text(render(subtitles, fmt), encoding="utf-8-sig" if fmt == "txt" else "utf-8")
    return path
