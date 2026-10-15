"""Persistent user preferences (stored in %APPDATA%\\Subway\\settings.json)."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from app.subtitles.types import SubtitleParams


def settings_path() -> Path:
    root = os.environ.get("APPDATA")
    folder = Path(root) / "Subway" if root else Path.home() / ".subway"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "settings.json"


@dataclass
class AppSettings:
    ui_language: str = "English"
    model_id: str = "parakeet-tdt-v3"
    device: str = "auto"
    recognition_language: str = "auto"
    translate: bool = False
    target_languages: list[str] = field(default_factory=lambda: ["Ukrainian"])
    gemini_model: str = "gemini-3.5-flash-lite"
    glossary: str = ""
    boost_glossary_in_recognition: bool = True
    formats: list[str] = field(default_factory=lambda: ["srt"])
    burn_in: bool = False
    burn_in_language: str = ""  # "" = original subtitles, otherwise a target language name.
    overwrite: bool = False
    output_dir: str = ""  # "" = next to the source file.
    max_chars_per_line: int = 42
    max_lines: int = 2
    min_duration: float = 1.0
    max_duration: float = 7.0
    max_cps: float = 20.0

    def subtitle_params(self) -> SubtitleParams:
        return SubtitleParams(
            max_chars_per_line=self.max_chars_per_line,
            max_lines=self.max_lines,
            min_duration=self.min_duration,
            max_duration=self.max_duration,
            max_cps=self.max_cps,
        ).normalized()

    def glossary_phrases(self) -> list[str]:
        """Terms for recognition boosting: the part before '=' or '—' on each glossary line."""
        phrases = []
        for line in self.glossary.splitlines():
            line = line.strip().lstrip("-•*").strip()
            if not line or line.startswith("#"):
                continue
            for separator in ("=", "—", " - ", ":"):
                if separator in line:
                    line = line.split(separator, 1)[0].strip()
                    break
            if line and len(line) <= 60 and line not in phrases:
                phrases.append(line)
        return phrases[:100]


def load_settings() -> AppSettings:
    settings = AppSettings()
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return settings
    if not isinstance(data, dict):
        return settings
    for item in fields(AppSettings):
        if item.name not in data:
            continue
        value = data[item.name]
        default = getattr(settings, item.name)
        try:
            if isinstance(default, bool):
                value = bool(value)
            elif isinstance(default, int):
                value = int(value)
            elif isinstance(default, float):
                value = float(value)
            elif isinstance(default, list):
                value = [str(v) for v in value] if isinstance(value, list) else default
            elif isinstance(default, str):
                value = str(value)
        except (TypeError, ValueError):
            continue
        setattr(settings, item.name, value)
    return settings


def save_settings(settings: AppSettings) -> None:
    path = settings_path()
    try:
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(existing, dict):
            existing = {}
    except (OSError, ValueError):
        existing = {}
    existing.update(asdict(settings))
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
