"""Compare models.json with Hugging Face and print a Markdown report of newer model files.

Run weekly by .github/workflows/model-updates.yml, which opens an issue when the report is not empty.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

API = "https://huggingface.co/api/models"
SEARCHES = ("parakeet", "nemotron-asr", "nemotron-3.5-asr", "canary")


def get(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "Subway-Model-Check"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def file_entry(repo: str, filename: str) -> tuple[str, dict | None]:
    info = get(f"{API}/{repo}/revision/main?blobs=true")
    entry = next((s for s in info.get("siblings", []) if s.get("rfilename") == filename), None)
    return info.get("sha", ""), entry


def main() -> int:
    catalog = json.loads((Path(__file__).resolve().parents[2] / "models.json").read_text(encoding="utf-8"))
    known_repos = {m["repo"] for m in catalog["models"]}
    lines: list[str] = []

    for model in catalog["models"]:
        try:
            revision, entry = file_entry(model["repo"], model["filename"])
        except Exception as exc:  # noqa: BLE001
            lines.append(f"- **{model['name']}**: could not check `{model['repo']}` ({exc}).")
            continue
        if entry is None:
            lines.append(f"- **{model['name']}**: `{model['filename']}` is no longer in `{model['repo']}` at main.")
            continue
        lfs = entry.get("lfs") or {}
        if lfs.get("sha256") and lfs["sha256"] != model["sha256"]:
            lines.append(
                f"- **{model['name']}** has a new file in `{model['repo']}`:\n"
                f"  ```json\n  \"revision\": \"{revision}\",\n  \"size\": {lfs.get('size', entry.get('size'))},\n"
                f"  \"sha256\": \"{lfs['sha256']}\"\n  ```"
            )

    found: dict[str, list[str]] = {}
    for term in SEARCHES:
        try:
            results = get(f"{API}?author=nvidia&search={term}&full=true&limit=100")
        except Exception:  # noqa: BLE001
            continue
        for repo in results:
            name = repo.get("id", "")
            ggufs = [s["rfilename"] for s in repo.get("siblings", []) if s.get("rfilename", "").endswith(".gguf")]
            if name and name not in known_repos and ggufs:
                found[name] = ggufs
    for name, files in sorted(found.items()):
        lines.append(f"- New NVIDIA repository with GGUF files: [{name}](https://huggingface.co/{name}) "
                     f"({', '.join(f'`{f}`' for f in files[:5])}). Check that NeMo-Speech.cpp supports it.")

    if lines:
        print("Hugging Face has model files that Subway's models.json does not list yet.\n")
        print("\n".join(lines))
        print("\nTo offer a new version, update the entry in `models.json` on `main` (revision, size, sha256 and, "
              "if the runtime must change, `min_app_version`). Subway picks it up at the next start.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
