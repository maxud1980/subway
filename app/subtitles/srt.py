from pathlib import Path
import re
from .types import Subtitle

def _timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}'

def write_srt(subtitles: list[Subtitle], path: Path) -> None:
    blocks = []
    for index, subtitle in enumerate(subtitles, start=1):
        blocks.append(f'{index}\n{_timestamp(subtitle.start)} --> {_timestamp(subtitle.end)}\n{subtitle.text.strip()}\n')
    path.write_text('\n'.join(blocks), encoding='utf-8')

def read_srt(path: Path) -> list[Subtitle]:
    text = path.read_text(encoding='utf-8-sig', errors='replace')
    blocks = re.split(r'\r?\n\s*\r?\n', text.strip())
    subtitles: list[Subtitle] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines()]
        timing = next((line for line in lines if ' --> ' in line), None)
        if not timing:
            continue
        start_text, end_text = [part.strip() for part in timing.split(' --> ', 1)]
        try:
            start = _parse_timestamp(start_text)
            end = _parse_timestamp(end_text)
        except ValueError:
            continue
        timing_index = lines.index(timing)
        subtitle_text = ' '.join(lines[timing_index + 1:]).strip()
        if subtitle_text and end > start:
            subtitles.append(Subtitle(start=start, end=end, text=subtitle_text))
    return subtitles

def _parse_timestamp(value: str) -> float:
    match = re.fullmatch(r'(\d+):(\d{2}):(\d{2})[,.](\d{3})', value)
    if not match:
        raise ValueError(f'Invalid SRT timestamp: {value}')
    hours, minutes, seconds, millis = map(int, match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / 1000

def translated_path(path: Path, language_code: str) -> Path:
    return path.with_name(f'{path.stem}.{language_code}.srt')
