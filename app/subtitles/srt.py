from pathlib import Path
from .types import Subtitle

def _timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def write_srt(subtitles: list[Subtitle], path: Path) -> None:
    blocks = []
    for index, subtitle in enumerate(subtitles, start=1):
        blocks.append(
            f"{index}\n{_timestamp(subtitle.start)} --> {_timestamp(subtitle.end)}\n"
            f"{subtitle.text.strip()}\n"
        )
    path.write_text("\n".join(blocks), encoding="utf-8")
