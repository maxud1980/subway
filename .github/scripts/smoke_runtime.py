"""CI check of a packaged runtime folder: speech runtime starts, FFmpeg can burn Cyrillic subtitles.

Usage: python smoke_runtime.py <runtime-dir>
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import media  # noqa: E402
from app.process import run  # noqa: E402
from app.subtitles import formats  # noqa: E402
from app.subtitles.types import Subtitle  # noqa: E402
from app.transcription.engine import RuntimeSelector  # noqa: E402


def frame_hash(ffmpeg: Path, video: Path, out: Path) -> str:
    code, text = run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", "1.5", "-i", video,
                      "-frames:v", "1", out])
    assert code == 0, text
    return hashlib.sha256(out.read_bytes()).hexdigest()


def main() -> None:
    runtime = Path(sys.argv[1]).resolve()
    selector = RuntimeSelector(runtime)
    installed = selector.installed()
    print("Installed runtimes:", installed)
    assert installed, "no runtime found"
    for variant, binary in installed:
        devices = selector.devices(binary)
        print(f"  {variant}: devices {devices}")
        assert devices is not None, f"{variant} runtime does not start"
    print("Selected:", selector.select("auto"))

    ffmpeg = media.find_ffmpeg(runtime)
    assert ffmpeg.parent == runtime, f"FFmpeg is not the bundled one: {ffmpeg}"
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        video = work / "test.mp4"
        code, text = run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                          "-f", "lavfi", "-i", "color=c=gray:s=640x360:d=3:r=25",
                          "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                          "-shortest", "-c:v", "libx264", "-c:a", "aac", video])
        assert code == 0, text
        info = media.to_wav(ffmpeg, video, work / "a.wav")
        print("Media info:", info)
        assert info.has_video and info.duration > 2
        ass = work / "subs.ass"
        formats.write([Subtitle(0.5, 2.8, "Привіт, світ!\nПеревірка субтитрів")], ass, "ass")
        burned = media.burn_subtitles(ffmpeg, video, ass, work / "burned.mp4", info.duration)
        before = frame_hash(ffmpeg, video, work / "before.png")
        after = frame_hash(ffmpeg, burned, work / "after.png")
        assert before != after, "subtitles were not drawn into the video"
        if len(sys.argv) > 2:
            (Path(sys.argv[2])).write_bytes((work / "after.png").read_bytes())
    print("Runtime smoke test passed.")


if __name__ == "__main__":
    main()
