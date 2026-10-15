"""Run external tools with live output, progress parsing and cancellation."""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Sequence


class Cancelled(Exception):
    """Raised when the user stops the current work."""


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise Cancelled()


NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run(
    command: Sequence[str | Path],
    cancel: CancelToken | None = None,
    on_output: Callable[[str], None] | None = None,
    cwd: Path | None = None,
    timeout: float | None = None,
) -> tuple[int, str]:
    """Run a command, streaming stderr+stdout line by line.

    Both carriage returns and newlines end a line, so tools that redraw a
    progress line (FFmpeg, model runtimes) are reported while they work.
    Returns the exit code and the last ~16 KB of output.
    """
    try:
        process = subprocess.Popen(
            [str(part) for part in command],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(cwd) if cwd else None,
            creationflags=NO_WINDOW,
        )
    except OSError as exc:
        raise RuntimeError(f"Unable to start {Path(str(command[0])).name}: {exc}") from exc

    tail: list[str] = []
    tail_size = 0

    def reader() -> None:
        nonlocal tail_size
        buffer = b""
        assert process.stdout is not None
        while True:
            chunk = process.stdout.read1(4096) if hasattr(process.stdout, "read1") else process.stdout.read(4096)
            if not chunk:
                break
            buffer += chunk
            while True:
                positions = [p for p in (buffer.find(b"\r"), buffer.find(b"\n")) if p >= 0]
                if not positions:
                    break
                cut = min(positions)
                raw, buffer = buffer[:cut], buffer[cut + 1:]
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                tail.append(line)
                tail_size += len(line)
                while tail_size > 16000 and len(tail) > 1:
                    tail_size -= len(tail.pop(0))
                if on_output:
                    try:
                        on_output(line)
                    except Exception:
                        pass
        if buffer.strip():
            line = buffer.decode("utf-8", errors="replace").strip()
            tail.append(line)
            if on_output:
                on_output(line)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    started = time.monotonic()
    while process.poll() is None:
        if cancel is not None and cancel.cancelled:
            _stop(process)
            thread.join(2)
            raise Cancelled()
        if timeout is not None and time.monotonic() - started > timeout:
            _stop(process)
            thread.join(2)
            raise RuntimeError(f"{Path(str(command[0])).name} did not finish in {timeout:.0f} s.")
        time.sleep(0.1)
    thread.join(5)
    return process.returncode, "\n".join(tail)


def _stop(process: subprocess.Popen) -> None:
    try:
        process.terminate()
        process.wait(3)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def frozen_base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]
