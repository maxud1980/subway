from app.config import AppSettings
from app.transcription.engine import language_argument, parse_doctor, parse_words
from app.transcription.models import MODELS, get_model


def test_parse_doctor_devices():
    output = """NeMo-Speech.cpp 0.1.0
Features: asr diarization
Devices:
  [0] cuda0          NVIDIA GeForce RTX 4070 (12 GiB)
  [1] Vulkan0        NVIDIA GeForce RTX 4070
  [2] cpu            AMD Ryzen 7
Model downloads: curl
"""
    assert parse_doctor(output) == ["cuda", "vulkan", "cpu"]


def test_parse_words_nested_and_language_tags():
    data = {"text": "Привіт світ", "words": [
        {"word": "Привіт", "start": 0.5, "end": 0.9, "confidence": 0.9},
        {"word": "світ.<uk-UA>", "start": 1.0, "end": 1.4},
    ]}
    words = parse_words(data, duration=2.0)
    assert [(w.text, w.start) for w in words] == [("Привіт", 0.5), ("світ.", 1.0)]


def test_parse_words_converts_milliseconds():
    data = {"results": [{"words": [{"text": "a", "start": 1000, "end": 1500}]}]}
    words = parse_words(data, duration=10.0)
    assert words[0].start == 1.0 and words[0].end == 1.5


def test_language_argument():
    parakeet, nemotron = get_model("parakeet-tdt-v3"), get_model("nemotron-3.5-asr")
    assert language_argument(parakeet, "uk") is None
    assert language_argument(nemotron, "uk") == "uk-UA"
    assert language_argument(nemotron, "auto") == "auto"
    assert language_argument(nemotron, "sw") == "auto"


def test_models_are_pinned():
    for model in MODELS:
        assert len(model.sha256) == 64 and model.revision in model.url


def test_glossary_phrases():
    settings = AppSettings(glossary="Купʼянськ = Kupiansk\n# comment\n- Петро Іваненко — командир\nЗСУ")
    assert settings.glossary_phrases() == ["Купʼянськ", "Петро Іваненко", "ЗСУ"]
