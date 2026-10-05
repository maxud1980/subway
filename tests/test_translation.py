from app.translation.translator import TranslationConfig, Translator

class FakeTranslator(Translator):
    def _translate_batch(self, texts):
        return [text.upper() for text in texts]

def test_translation_batches_preserve_order():
    translator = FakeTranslator(TranslationConfig('Gemini', 'key', 'model', 'Ukrainian', batch_size=2))
    assert translator.translate(['one', 'two', 'three']) == ['ONE', 'TWO', 'THREE']

def test_json_response_is_mapped_by_id():
    translator = Translator(TranslationConfig('Gemini', 'key', 'model', 'Ukrainian'))
    translator._gemini = lambda prompt: '{"items":[{"id":1,"text":"два"},{"id":0,"text":"один"}]}'
    assert translator._translate_batch(['one', 'two']) == ['один', 'два']
