import json

from app.translation.translator import TranslationConfig, Translator, _strip_fence


class FakeTranslator(Translator):
    def __init__(self, config):
        super().__init__(config)
        self.contexts = []

    def _translate_batch(self, texts, context=None):
        self.contexts.append(list(context or []))
        return [text.upper() for text in texts]


def test_translation_batches_preserve_order():
    translator = FakeTranslator(TranslationConfig("Gemini", "key", "model", "Ukrainian", batch_size=2))
    assert translator.translate(["one", "two", "three"]) == ["ONE", "TWO", "THREE"]


def test_previous_lines_are_passed_as_context():
    translator = FakeTranslator(TranslationConfig("Gemini", "key", "model", "Ukrainian", batch_size=2, context_lines=1))
    translator.translate(["one", "two", "three"])
    assert translator.contexts == [[], [("two", "TWO")]]


def test_multiline_input_is_flattened():
    translator = FakeTranslator(TranslationConfig("Gemini", "key", "model", "Ukrainian"))
    assert translator.translate(["hello\nworld"]) == ["HELLO WORLD"]


def test_json_response_is_mapped_by_id():
    translator = Translator(TranslationConfig("Gemini", "key", "model", "Ukrainian"))
    translator._gemini = lambda prompt: '{"items":[{"id":1,"text":"два"},{"id":0,"text":"один"}]}'
    assert translator._translate_batch(["one", "two"]) == ["один", "два"]


def test_code_fence_is_removed():
    assert _strip_fence('```json\n{"items": []}\n```') == '{"items": []}'


def test_prompt_contains_glossary_and_context():
    translator = Translator(TranslationConfig("Gemini", "key", "model", "Ukrainian", notes="Petro = Петро"))
    prompt = translator.build_prompt(["hi"], [("before", "раніше")])
    assert "Petro = Петро" in prompt
    assert "before => раніше" in prompt
    assert json.loads(prompt.rsplit("Input JSON:\n", 1)[1]) == {"items": [{"id": 0, "text": "hi"}]}


def test_stalled_answer_is_retried(monkeypatch):
    import io

    import app.translation.translator as translator

    calls = []

    def fake_urlopen(request, timeout):
        calls.append(timeout)
        if len(calls) < 3:
            raise TimeoutError("The read operation timed out")
        return io.BytesIO(b'{"ok": true}')

    monkeypatch.setattr(translator, "urlopen", fake_urlopen)
    monkeypatch.setattr(translator.time, "sleep", lambda seconds: None)
    client = Translator(TranslationConfig(provider="gemini", api_key="k", model="m", target_language="uk"))
    assert client._request_json("https://example.com", {}, {}) == {"ok": True}
    assert len(calls) == 3
