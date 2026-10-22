"""Check that every pinned model file exists on Hugging Face with the size and SHA-256 Subway expects.

A wrong pin would make every user's download fail the checksum, so CI checks them against
the Hugging Face API without downloading the files.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.transcription import catalog  # noqa: E402
from app.transcription.models import MODELS, WHISPER_VAD  # noqa: E402


def lfs_entry(repo: str, revision: str, filename: str) -> dict:
    request = urllib.request.Request(
        f"https://huggingface.co/api/models/{repo}/paths-info/{revision}",
        data=json.dumps({"paths": [filename]}).encode(),
        headers={"User-Agent": "Subway-Model-Check", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        entries = json.loads(response.read().decode("utf-8"))
    return next((e for e in entries if e.get("path") == filename), {})


def main() -> int:
    published = catalog.parse_catalog(json.loads((Path(__file__).resolve().parents[2] / "models.json").read_text("utf-8")))
    failures = 0
    for model in [*MODELS, WHISPER_VAD, *published]:
        entry = lfs_entry(model.repo, model.revision, model.filename)
        lfs = entry.get("lfs") or {}
        found = (entry.get("size"), lfs.get("oid") or lfs.get("sha256"))
        if found != (model.size, model.sha256):
            failures += 1
            print(f"FAIL {model.repo}/{model.filename}@{model.revision[:8]}: expected {model.size} {model.sha256}, "
                  f"Hugging Face has {found[0]} {found[1]}")
        else:
            print(f"ok   {model.repo}/{model.filename}@{model.revision[:8]}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
