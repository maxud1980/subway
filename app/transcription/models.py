from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str
    filename: str
    url: str
    size_mb: int
    languages: str


MODELS = [
    ModelInfo(
        id="parakeet-tdt-v3",
        name="Parakeet TDT v3 — 0.6B Q8",
        filename="parakeet-tdt-0.6b-v3.q8_0.gguf",
        url="https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3/resolve/main/parakeet-tdt-0.6b-v3.q8_0.gguf",
        size_mb=714,
        languages="25 European languages, including Ukrainian and Russian",
    ),
]


class ModelManager:
    def __init__(self, runtime_dir: Path | None = None):
        self.runtime_dir = runtime_dir or Path(__file__).resolve().parents[2] / "runtime"
        self.models_dir = self.runtime_dir / "models"

    def available_models(self) -> list[ModelInfo]:
        return MODELS

    def path_for(self, model: ModelInfo) -> Path:
        return self.models_dir / model.filename

    def is_downloaded(self, model: ModelInfo) -> bool:
        path = self.path_for(model)
        return path.exists() and path.stat().st_size > 1024 * 1024

    def download(
        self,
        model: ModelInfo,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        self.models_dir.mkdir(parents=True, exist_ok=True)
        target = self.path_for(model)
        partial = target.with_suffix(target.suffix + ".download")

        try:
            request = urllib.request.Request(
                model.url,
                headers={"User-Agent": "Subway/0.1"},
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                total = int(response.headers.get("Content-Length", "0"))
                received = 0
                with partial.open("wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        received += len(chunk)
                        if progress:
                            progress(received, total)

            partial.replace(target)
            return target
        except Exception:
            partial.unlink(missing_ok=True)
            raise
