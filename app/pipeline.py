"""The processing queue: recognition, subtitle files, translation and burn-in."""
from __future__ import annotations

import itertools
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app import media
from app.config import AppSettings
from app.languages import language_code, language_name
from app.process import CancelToken, Cancelled
from app.subtitles import formats
from app.subtitles.formatter import rewrap_subtitles, segments_to_subtitles, words_to_subtitles
from app.subtitles.srt import read_srt
from app.subtitles.types import Subtitle
from app.transcription.engine import NemoSpeechEngine
from app.transcription.models import ModelManager

QUEUED, RUNNING, DONE, FAILED, CANCELLED = "queued", "running", "done", "failed", "cancelled"
_ids = itertools.count(1)


@dataclass
class Job:
    path: Path
    id: int = field(default_factory=lambda: next(_ids))
    status: str = QUEUED
    stage: str = ""
    progress: float | None = 0.0
    outputs: dict[str, Path] = field(default_factory=dict)  # label -> file
    error: str = ""
    media_path: Path | None = None  # Video/audio for SRT jobs, when found.
    duration: float = 0.0

    @property
    def is_srt(self) -> bool:
        return self.path.suffix.lower() == ".srt"

    @property
    def main_srt(self) -> Path | None:
        return self.outputs.get("Original") or (self.path if self.is_srt else None)


@dataclass
class Plan:
    """Where every output of one job will be written."""
    folder: Path
    stem: str

    def original(self, fmt: str) -> Path:
        return self.folder / f"{self.stem}.{fmt}"

    def translated(self, code: str, fmt: str) -> Path:
        return self.folder / f"{self.stem}.{code}.{fmt}"

    def burned(self, code: str | None) -> Path:
        return self.folder / (f"{self.stem}.{code}.subtitled.mp4" if code else f"{self.stem}.subtitled.mp4")


def find_sibling_media(srt: Path) -> Path | None:
    stem = srt.stem
    candidates = [stem]
    if "." in stem:
        candidates.append(stem.rsplit(".", 1)[0])  # video.uk.srt -> video
    for name in candidates:
        for ext in sorted(media.VIDEO_EXTENSIONS):
            for variant in (ext, ext.upper()):
                path = srt.with_name(name + variant)
                if path.exists():
                    return path
    return None


class Pipeline:
    def __init__(
        self,
        settings: AppSettings,
        api_key: str,
        runtime_dir: Path,
        notify: Callable[[Job], None],
        log: Callable[[str], None],
        engine: NemoSpeechEngine | None = None,
        translator_factory=None,
        models: ModelManager | None = None,
    ):
        self.settings = settings
        self.api_key = api_key
        self.runtime_dir = runtime_dir
        self.notify = notify
        self.log = log
        self.models = models or ModelManager(runtime_dir)
        self.engine = engine or NemoSpeechEngine(runtime_dir)
        if translator_factory is None:
            from app.translation.translator import create_translator
            translator_factory = create_translator
        self.translator_factory = translator_factory
        self.cancel = CancelToken()

    # -- helpers ---------------------------------------------------------
    def _set(self, job: Job, stage: str | None = None, progress: float | None | str = "keep") -> None:
        if stage is not None:
            job.stage = stage
        if progress != "keep":
            job.progress = progress  # type: ignore[assignment]
        self.notify(job)

    def plan(self, job: Job) -> Plan:
        s = self.settings
        folder = Path(s.output_dir) if s.output_dir else job.path.parent
        folder.mkdir(parents=True, exist_ok=True)
        stem = job.path.stem
        if s.overwrite:
            return Plan(folder, stem)
        for n in range(1, 1000):
            candidate = Plan(folder, stem if n == 1 else f"{stem} ({n})")
            planned = self._planned_files(job, candidate)
            if not any(p.exists() for p in planned if p != job.path):
                return candidate
        return Plan(folder, f"{stem} ({int(time.time())})")

    def _planned_files(self, job: Job, plan: Plan) -> list[Path]:
        s = self.settings
        files: list[Path] = []
        extra = [f for f in s.formats if f != "srt"]
        if not job.is_srt:
            files += [plan.original(f) for f in ["srt"] + extra]
        if s.translate:
            for name in s.target_languages:
                code = language_code(name)
                files += [plan.translated(code, f) for f in ["srt"] + extra]
        if s.burn_in:
            language = self._burn_language()
            files.append(plan.burned(language_code(language) if language else None))
        return files

    def _burn_language(self) -> str:
        s = self.settings
        return s.burn_in_language if s.translate and s.burn_in_language in s.target_languages else ""

    def _write_all(self, subtitles: list[Subtitle], target_srt: Path, label: str, job: Job) -> None:
        formats.write(subtitles, target_srt, "srt")
        job.outputs[label] = target_srt
        for fmt in self.settings.formats:
            if fmt == "srt":
                continue
            path = target_srt.with_suffix("." + fmt)
            formats.write(subtitles, path, fmt)
            job.outputs[f"{label} ({fmt.upper()})"] = path

    # -- main entry --------------------------------------------------------
    def run(self, jobs: list[Job]) -> None:
        """Process queued jobs until none are left.

        `jobs` may be the UI's live list: files added while the queue runs
        are picked up, and removing finished rows does not skip anything.
        """
        while not self.cancel.cancelled:
            job = next((j for j in list(jobs) if j.status == QUEUED), None)
            if job is None:
                break
            job.status = RUNNING
            job.error = ""
            self._set(job, "Starting", 0.0)
            started = time.monotonic()
            try:
                self.process(job)
                job.status = DONE
                self._set(job, "Done", 1.0)
                self.log(f"✓ {job.path.name} — {time.monotonic() - started:.0f} s")
            except Cancelled:
                job.status = CANCELLED
                self._set(job, "Stopped", None)
                self.log(f"■ {job.path.name}: stopped")
                break
            except Exception as exc:  # noqa: BLE001 - report every failure to the user
                job.status = FAILED
                job.error = str(exc)
                self._set(job, "Failed", None)
                self.log(f"✗ {job.path.name}: {exc}")

    def process(self, job: Job) -> None:
        s = self.settings
        params = s.subtitle_params()
        plan = self.plan(job)
        targets = [t for t in s.target_languages if t] if s.translate else []
        burn = s.burn_in
        weights = {"recognize": 0.0 if job.is_srt else 0.6, "translate": 0.3 if targets else 0.0,
                   "burn": 0.25 if burn else 0.0}
        total = sum(weights.values()) or 1.0
        offset = 0.0

        def scaled(name: str, done_before: float) -> Callable[[float | None], None]:
            share = weights[name] / total

            def update(fraction: float | None) -> None:
                self._set(job, None, None if fraction is None else done_before + share * fraction)
            return update

        # 1. Original subtitles.
        if job.is_srt:
            original = read_srt(job.path)
            if not original:
                raise RuntimeError("The SRT file contains no subtitles.")
            job.media_path = find_sibling_media(job.path)
        else:
            original = self.recognize(job, plan, params, scaled("recognize", 0.0))
            job.media_path = job.path
            offset += weights["recognize"] / total

        # 2. Translations.
        translated: dict[str, list[Subtitle]] = {}
        if targets:
            if not self.api_key:
                raise RuntimeError("Enter a Gemini API key in Settings to translate subtitles.")
            share = weights["translate"] / total / len(targets)
            for index, name in enumerate(targets):
                self.cancel.check()
                self._set(job, f"Translating → {name}", offset + share * index)
                result = self.translate(original, name, params,
                                        lambda f, base=offset + share * index: self._set(job, None, base + share * f))
                code = language_code(name)
                self._write_all(result, plan.translated(code, "srt"), name, job)
                translated[name] = result
            offset += weights["translate"] / total

        # 3. Burned-in video.
        if burn:
            self.cancel.check()
            video = job.media_path
            if video is None or video.suffix.lower() not in media.VIDEO_EXTENSIONS:
                self.log(f"{job.path.name}: no video to burn subtitles into — skipped.")
            else:
                language = self._burn_language()
                language = language if language in translated else ""
                subs = translated[language] if language else original
                self._set(job, "Burning subtitles into video", offset)
                ffmpeg = media.find_ffmpeg(self.runtime_dir)
                duration = job.duration or media.probe(ffmpeg, video).duration
                with tempfile.TemporaryDirectory(dir=media.temp_dir()) as tmp:
                    ass = Path(tmp) / "subs.ass"
                    formats.write(subs, ass, "ass")
                    out = plan.burned(language_code(language) if language else None)
                    media.burn_subtitles(ffmpeg, video, ass, out, duration, self.cancel, scaled("burn", offset))
                job.outputs["Video with subtitles"] = out

    def recognize(self, job: Job, plan: Plan, params, progress) -> list[Subtitle]:
        s = self.settings
        model = self.models.installed(s.model_id)
        if model is None:
            raise RuntimeError(f"Download the recognition model first: {self.models.get(s.model_id).name}")
        language = language_code(s.recognition_language) if s.recognition_language != "auto" else "auto"
        if language != "auto" and not model.recognizes_language(language):
            raise RuntimeError(f"{model.name} does not recognize {language_name(language)}. "
                               "Choose another recognition model.")
        ffmpeg = media.find_ffmpeg(self.runtime_dir)
        with tempfile.TemporaryDirectory(dir=media.temp_dir()) as tmp:
            wav = Path(tmp) / "audio.wav"
            self._set(job, "Extracting audio", 0.0)
            info = media.to_wav(ffmpeg, job.path, wav, self.cancel, lambda f: progress(0.1 * f))
            job.duration = info.duration
            self.cancel.check()
            self._set(job, "Recognizing speech", None)
            started = time.monotonic()
            phrases = s.glossary_phrases() if s.boost_glossary_in_recognition else []
            transcript = self.engine.transcribe(
                wav, model, self.models.path_for(model),
                language=language,
                device=s.device, phrases=phrases, duration=info.duration,
                cancel=self.cancel, progress=lambda f: progress(None if f is None else 0.1 + 0.9 * f), log=self.log,
            )
            elapsed = time.monotonic() - started
            if info.duration:
                self.log(f"{job.path.name}: recognized {info.duration / 60:.1f} min of audio in {elapsed:.0f} s ({transcript.backend})")
        if transcript.words:
            subtitles = words_to_subtitles(transcript.words, params)
        else:
            subtitles = segments_to_subtitles(transcript.segments, params=params)
        if not subtitles:
            raise RuntimeError("No speech was recognized in this file.")
        self._write_all(subtitles, plan.original("srt"), "Original", job)
        return subtitles

    def translate(self, subtitles: list[Subtitle], language: str, params, progress) -> list[Subtitle]:
        s = self.settings
        source = s.recognition_language if s.recognition_language not in ("", "auto") else "auto"
        translator = self.translator_factory("Gemini", self.api_key, s.gemini_model, language,
                                             source_language=source, notes=s.glossary)
        texts = translator.translate([sub.text for sub in subtitles], cancel=self.cancel, progress=progress)
        return rewrap_subtitles([Subtitle(sub.start, sub.end, text) for sub, text in zip(subtitles, texts)], params)
