from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Subtitle:
    start: float
    end: float
    text: str  # Lines are separated with "\n".


@dataclass
class SubtitleParams:
    max_chars_per_line: int = 42
    max_lines: int = 2
    min_duration: float = 1.0
    max_duration: float = 7.0
    max_cps: float = 20.0  # Reading speed limit, characters per second.
    min_gap: float = 0.08  # Minimum pause between two subtitles, seconds.
    pause_split: float = 0.7  # A pause this long always starts a new subtitle.

    def normalized(self) -> "SubtitleParams":
        return SubtitleParams(
            max_chars_per_line=max(10, min(int(self.max_chars_per_line), 120)),
            max_lines=max(1, min(int(self.max_lines), 4)),
            min_duration=max(0.2, min(float(self.min_duration), 10.0)),
            max_duration=max(1.0, min(float(self.max_duration), 30.0)),
            max_cps=max(5.0, min(float(self.max_cps), 60.0)),
            min_gap=max(0.0, min(float(self.min_gap), 1.0)),
            pause_split=max(0.2, min(float(self.pause_split), 5.0)),
        )
