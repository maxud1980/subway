from app.config import AppSettings
from app.pipeline import DONE, FAILED, Job, Pipeline
from app.subtitles.srt import read_srt, write_srt
from app.subtitles.types import Subtitle


class FakeTranslator:
    def __init__(self, language):
        self.language = language

    def translate(self, texts, cancel=None, progress=None):
        if progress:
            progress(1.0)
        return [f"[{self.language}] {t}" for t in texts]


def factory(provider, api_key, model, language, source_language="auto", notes=""):
    return FakeTranslator(language)


def make_pipeline(tmp_path, **overrides):
    settings = AppSettings(**overrides)
    logs = []
    pipe = Pipeline(settings, "key", tmp_path / "runtime", notify=lambda job: None, log=logs.append,
                    engine=object(), translator_factory=factory)
    return pipe, logs


def test_srt_job_translates_to_several_languages(tmp_path):
    source = tmp_path / "talk.srt"
    write_srt([Subtitle(0, 1, "Hello"), Subtitle(2, 3, "World")], source)
    pipe, _ = make_pipeline(tmp_path, translate=True, target_languages=["Ukrainian", "English"], formats=["srt", "vtt"])
    job = Job(source)
    pipe.run([job])
    assert job.status == DONE, job.error
    assert read_srt(tmp_path / "talk.uk.srt")[1].text == "[Ukrainian] World"
    assert (tmp_path / "talk.en.srt").exists() and (tmp_path / "talk.en.vtt").exists()


def test_existing_outputs_are_not_overwritten(tmp_path):
    source = tmp_path / "talk.srt"
    write_srt([Subtitle(0, 1, "Hello")], source)
    (tmp_path / "talk.uk.srt").write_text("keep me", encoding="utf-8")
    pipe, _ = make_pipeline(tmp_path, translate=True, target_languages=["Ukrainian"])
    job = Job(source)
    pipe.run([job])
    assert (tmp_path / "talk.uk.srt").read_text(encoding="utf-8") == "keep me"
    assert (tmp_path / "talk (2).uk.srt").exists()


def test_media_job_writes_original_and_extra_formats(tmp_path, monkeypatch):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"")
    pipe, _ = make_pipeline(tmp_path, formats=["srt", "txt", "ass"])

    def fake_recognize(job, plan, params, progress):
        subs = [Subtitle(0, 1.5, "Recognized")]
        pipe._write_all(subs, plan.original("srt"), "Original", job)
        return subs

    monkeypatch.setattr(pipe, "recognize", fake_recognize)
    job = Job(video)
    pipe.run([job])
    assert job.status == DONE, job.error
    assert {p.name for p in job.outputs.values()} == {"clip.srt", "clip.txt", "clip.ass"}


def test_translation_without_key_fails_cleanly(tmp_path):
    source = tmp_path / "talk.srt"
    write_srt([Subtitle(0, 1, "Hello")], source)
    pipe, logs = make_pipeline(tmp_path, translate=True)
    pipe.api_key = ""
    job = Job(source)
    pipe.run([job])
    assert job.status == FAILED and "API key" in job.error
