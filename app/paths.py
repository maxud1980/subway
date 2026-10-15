"""Per-platform folders for settings, models and the bundled runtime."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Subway"
IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


def config_dir() -> Path:
    """Settings and the encrypted key file (Windows)."""
    if IS_WINDOWS and os.environ.get("APPDATA"):
        folder = Path(os.environ["APPDATA"]) / APP_NAME
    elif IS_MAC:
        folder = Path.home() / "Library" / "Application Support" / APP_NAME
    elif os.environ.get("APPDATA"):  # Lets tests and development redirect the folder.
        folder = Path(os.environ["APPDATA"]) / APP_NAME
    else:
        folder = Path.home() / ".subway"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def user_models_dir() -> Path:
    if IS_WINDOWS and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / APP_NAME / "models"
    if IS_MAC:
        return Path.home() / "Library" / "Application Support" / APP_NAME / "models"
    root = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(root) / APP_NAME / "models"


def runtime_dir() -> Path:
    """Folder with the speech runtime(s) and FFmpeg.

    Windows: `runtime` beside Subway.exe.
    macOS app: Subway.app/Contents/Resources/runtime.
    Development: `runtime` in the repository root.
    """
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        if IS_MAC and executable.parent.name == "MacOS":
            return executable.parents[1] / "Resources" / "runtime"
        return executable.parent / "runtime"
    return Path(__file__).resolve().parents[1] / "runtime"


def models_live_in_app_folder() -> bool:
    """Models may sit beside a portable Windows install, never inside a signed macOS app."""
    return not IS_MAC
