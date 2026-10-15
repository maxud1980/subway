"""Colours and fonts shared by every Subway window.

The queue is drawn as a metro line: each file is a station whose dot shows
its state, which is where the app's name comes from.
"""
import sys

BG = "#141B26"
SURFACE = "#1C2533"
RAISED = "#243042"
LINE = "#2F3D52"
TEXT = "#E6EDF7"
MUTED = "#8A9BB3"
ACCENT = "#2D7FF9"
ACCENT_HOVER = "#1F6AD8"
SUCCESS = "#3FB27F"
DANGER = "#E5534B"
WARNING = "#E0A33A"

STATUS_COLORS = {
    "queued": MUTED,
    "running": ACCENT,
    "done": SUCCESS,
    "failed": DANGER,
    "cancelled": WARNING,
}

if sys.platform == "darwin":
    UI_FONT, MONO_FONT, TABLE_SIZE = "Helvetica Neue", "Menlo", 13
elif sys.platform == "win32":
    UI_FONT, MONO_FONT, TABLE_SIZE = "Segoe UI", "Consolas", 10
else:
    UI_FONT, MONO_FONT, TABLE_SIZE = "DejaVu Sans", "DejaVu Sans Mono", 10

PAD = 16
RADIUS = 10
