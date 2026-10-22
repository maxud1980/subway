import json
from pathlib import Path

import pytest

from app.config import AppSettings
from app.languages import names_for
from app.pipeline import Job, Pipeline
from app.transcription import catalog
from app.transcription.engine import language_argument
from app.transcription.models import MODELS, ModelInfo, ModelManager, get_model

ROOT = Path(__file__).resolve().parents[1]


def test_models_know_their_languages():
    parakeet, nemotron = get_model("parakeet-tdt-v3"), get_model("nemotron-3.5-asr")
    assert parakeet.recognizes_language("uk") and parakeet.recognizes_language("pt-BR")
    assert not parakeet.recognizes_language("ar")
    assert nemotron.recognizes_language("ar") and nemotron.recognizes_language("no")
    assert not nemotron.recognizes_language("sw")
    assert "Portuguese (Brazil)" in names_for(parakeet.recognized_languages)
    assert "Norwegian" in names_for(nemotron.recognized_languages)


def test_language_argument_matches_differently_named_codes():
    nemotron = get_model("nemotron-3.5-asr")
    assert language_argument(nemotron, "no") == "nb-NO"
    assert language_argument(nemotron, "zh-Hans") == "zh-CN"
    assert language_argument(nemotron, "ar") == "ar-AR"


def _entry(**overrides):
    entry = {"id": "parakeet-tdt-v3", "name": "Parakeet TDT v4", "version": "v4", "repo": "nvidia/parakeet-tdt-0.6b-v4",
             "revision": "a" * 40, "filename": "parakeet-tdt-0.6b-v3.q8_0.gguf", "size": 10, "sha256": "b" * 64,
             "recognizes": ["uk", "en"], "notes": "Better punctuation"}
    entry.update(overrides)
    return entry


def test_catalog_rejects_malformed_entries():
    models = catalog.parse_catalog({"models": [
        _entry(), _entry(revision="main"), _entry(filename="../evil.gguf"), _entry(size="10"),
        _entry(repo="https://example.com/x"), "junk",
    ]})
    assert [m.revision for m in models] == ["a" * 40]
    assert models[0].recognizes == ("uk", "en") and models[0].notes == "Better punctuation"
    assert catalog.parse_catalog([]) == [] and catalog.parse_catalog({"models": "x"}) == []


def test_published_catalog_matches_built_in_models():
    data = json.loads((ROOT / "models.json").read_text(encoding="utf-8"))
    published = catalog.parse_catalog(data)
    assert len(published) == len(data["models"])
    built_in = {m.id: m for m in MODELS}
    for model in published:
        if model.id in built_in and model.revision == built_in[model.id].revision:
            assert model.sha256 == built_in[model.id].sha256 and model.size == built_in[model.id].size
            assert model.recognized_languages == built_in[model.id].recognized_languages


@pytest.fixture
def manager(tmp_path):
    manager = ModelManager(tmp_path / "runtime")
    manager.models_dir = tmp_path / "models"
    manager.fallback_dir = tmp_path / "fallback"
    manager.models_dir.mkdir()
    return manager


def _place(manager: ModelManager, model: ModelInfo) -> Path:
    path = manager.models_dir / model.local_filename
    with path.open("wb") as handle:
        handle.truncate(model.size)
    return path


def test_new_version_is_offered_and_old_one_removed(manager):
    old = manager.get("parakeet-tdt-v3")
    old_path = _place(manager, old)
    assert manager.installed(old.id) == old and not manager.update_available(old.id)

    new = catalog.parse_entry(_entry())
    assert manager.add_versions([new, new]) and len(manager.available_models()) == len(MODELS)
    latest = manager.get(old.id)
    assert latest.revision == "a" * 40
    assert latest.local_filename == "parakeet-tdt-0.6b-v3.q8_0.aaaaaaaa.gguf"  # Does not overwrite the old file.
    assert manager.installed(old.id) == old and manager.update_available(old.id)
    assert manager.add_versions([new]) == []

    _place(manager, latest)
    assert manager.installed(old.id) == latest and not manager.update_available(old.id)
    assert manager.older_size(old.id) == old.size
    manager.remove_older(old.id)
    assert not old_path.exists() and manager.installed(old.id) == latest


def test_catalog_can_add_a_new_model(manager):
    manager.add_versions([catalog.parse_entry(_entry(id="parakeet-tdt-v4", filename="parakeet-v4.gguf"))])
    assert [m.id for m in manager.available_models()][-1] == "parakeet-tdt-v4"
    assert manager.installed("parakeet-tdt-v4") is None


def test_recognition_refuses_unsupported_language(tmp_path, manager, monkeypatch):
    settings = AppSettings(model_id="parakeet-tdt-v3", recognition_language="Arabic")
    pipe = Pipeline(settings, "", tmp_path / "runtime", notify=lambda job: None, log=lambda text: None,
                    engine=object(), translator_factory=lambda *a, **k: None, models=manager)
    _place(manager, manager.get("parakeet-tdt-v3"))
    with pytest.raises(RuntimeError, match="does not recognize Arabic"):
        pipe.recognize(Job(tmp_path / "talk.mp4"), None, None, lambda f: None)
