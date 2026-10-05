from dataclasses import dataclass

@dataclass
class AppConfig:
    recognition_engine: str = "parakeet"
    language: str = "auto"
    max_chars_per_line: int = 42
    max_lines: int = 2
