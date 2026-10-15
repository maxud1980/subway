"""Colours and fonts shared by every Subway window.

The queue is drawn as a metro line: each file is a station whose dot shows
its state, which is where the app's name comes from.
"""

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

PAD = 16
RADIUS = 10
