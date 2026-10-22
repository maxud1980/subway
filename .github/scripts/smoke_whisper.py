"""CI check of the packaged whisper.cpp runtime: recognize a short spoken sentence.

Usage: python smoke_whisper.py <runtime-dir> <whisper-model.bin> <speech-audio> <expected word>

The Silero VAD file is downloaded through Subway's own ModelManager, which also
verifies the size and SHA-256 pinned in app/transcription/models.py.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import media  # noqa: E402
from app.transcription.engine import WhisperEngine  # noqa: E402
from app.transcription.models import WHISPER_VAD, ModelManager, get_model  # noqa: E402


def notice(message: str) -> None:
    print(message)
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice title=Whisper check::{message}")


def main() -> None:
    runtime, model_path, audio, expected = Path(sys.argv[1]).resolve(), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        manager = ModelManager(work)
        manager.models_dir = manager.fallback_dir = work / "models"
        manager.download(WHISPER_VAD)
        engine = WhisperEngine(runtime, manager)
        builds = engine.installed()
        notice(f"whisper.cpp builds: {[variant for variant, _ in builds]}")
        assert builds, "no whisper.cpp build found"

        wav = work / "speech.wav"
        media.to_wav(media.find_ffmpeg(runtime), audio, wav)
        model = get_model("whisper-large-v3-turbo")
        for device in ("auto", "cpu"):
            transcript = engine.transcribe(wav, model, model_path, language="en", device=device, log=print)
            text = " ".join(w.text for w in transcript.words) or " ".join(s.text for s in transcript.segments)
            print([(w.text, w.start, w.end) for w in transcript.words])
            assert expected.lower() in text.lower(), f"'{expected}' not in: {text}"
            assert transcript.words, "no word timings"
            notice(f"{transcript.backend}: {text}")


if __name__ == "__main__":
    main()
