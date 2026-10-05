from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass
class TranscriptWord:
    text: str
    start: float
    end: float


@dataclass
class TranscriptSegment:
    text: str
    start: float
    end: float
    words: list[TranscriptWord]


class TranscriptionEngine:
    name = "Base"

    def transcribe(self, media_path: Path) -> Iterator[TranscriptSegment]:
        raise NotImplementedError


class ParakeetEngine(TranscriptionEngine):
    name = "Parakeet TDT v3"
    model_name = "nvidia/parakeet-tdt-0.6b-v3"

    def __init__(self):
        self._model = None

    def _load(self):
        if self._model is not None:
            return
        try:
            from nemo.collections.asr.models import ASRModel
        except ImportError as exc:
            raise RuntimeError("NeMo ASR is not installed.") from exc
        self._model = ASRModel.from_pretrained(model_name=self.model_name)

    def transcribe(self, media_path: Path) -> Iterator[TranscriptSegment]:
        self._load()
        outputs = self._model.transcribe([str(media_path)], timestamps=True)
        for output in outputs:
            yield self._normalize_output(output)

    @staticmethod
    def _normalize_output(output) -> TranscriptSegment:
        return TranscriptSegment(
            text=str(getattr(output, "text", "")).strip(),
            start=0.0,
            end=0.0,
            words=[],
        )


class QwenASREngine(TranscriptionEngine):
    name = "Qwen3-ASR 1.7B"
    model_name = "Qwen/Qwen3-ASR-1.7B"

    def __init__(self):
        self._model = None

    def _load(self):
        if self._model is not None:
            return
        try:
            from qwen_asr import Qwen3ASRModel
        except ImportError as exc:
            raise RuntimeError("qwen-asr is not installed.") from exc
        self._model = Qwen3ASRModel.from_pretrained(
            self.model_name,
            device_map="cuda:0",
            forced_aligner="Qwen/Qwen3-ForcedAligner-0.6B",
            forced_aligner_kwargs={"device_map": "cuda:0"},
        )

    def transcribe(self, media_path: Path) -> Iterator[TranscriptSegment]:
        self._load()
        results = self._model.transcribe(
            audio=str(media_path),
            language=None,
            return_time_stamps=True,
        )
        for result in results:
            words = [
                TranscriptWord(str(item[0]), float(item[1]), float(item[2]))
                for item in (getattr(result, "time_stamps", []) or [])
                if len(item) >= 3
            ]
            yield TranscriptSegment(
                text=str(getattr(result, "text", "")).strip(),
                start=words[0].start if words else 0.0,
                end=words[-1].end if words else 0.0,
                words=words,
            )
