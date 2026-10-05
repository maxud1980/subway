from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

class TranslationError(RuntimeError):
    pass

@dataclass(frozen=True)
class TranslationConfig:
    provider: str
    api_key: str
    model: str
    target_language: str
    batch_size: int = 24

class Translator:
    def __init__(self, config: TranslationConfig):
        self.config = config

    def translate(self, texts: list[str]) -> list[str]:
        result: list[str] = []
        for start in range(0, len(texts), self.config.batch_size):
            result.extend(self._translate_batch(texts[start:start + self.config.batch_size]))
        return result

    def _translate_batch(self, texts: list[str]) -> list[str]:
        payload = {'items': [{'id': i, 'text': text} for i, text in enumerate(texts)]}
        prompt = (
            'Translate subtitle lines into {target}. Preserve meaning, tone, names, numbers and profanity. '
            'Do not explain or summarize. Keep each subtitle item separate. '
            'Return ONLY valid JSON in exactly this form: {{"items":[{{"id":0,"text":"translated text"}}]}}. '
            'Keep every input id exactly once and do not add or remove items. Input JSON:\n{payload}'
        ).format(target=self.config.target_language, payload=json.dumps(payload, ensure_ascii=False))
        if self.config.provider == 'Gemini':
            raw = self._gemini(prompt)
        elif self.config.provider == 'OpenAI':
            raw = self._openai(prompt)
        else:
            raise TranslationError(f'Unsupported provider: {self.config.provider}')
        try:
            data = json.loads(raw.strip())
            items = data['items']
            by_id = {int(item['id']): str(item['text']).strip() for item in items}
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise TranslationError('Translation model returned invalid JSON.\n\n' + raw[:4000]) from exc
        expected = set(range(len(texts)))
        if set(by_id) != expected or any(not by_id[i] for i in expected):
            raise TranslationError('Translation returned the wrong number of subtitle items.')
        return [by_id[i] for i in range(len(texts))]

    def _request_json(self, url: str, body: dict, headers: dict[str, str]) -> dict:
        request = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'), headers={'Content-Type': 'application/json', **headers}, method='POST')
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode('utf-8', errors='replace')
            raise TranslationError(f'API request failed ({exc.code}): {details[:3000]}') from exc
        except urllib.error.URLError as exc:
            raise TranslationError(f'Unable to reach translation API: {exc.reason}') from exc

    def _gemini(self, prompt: str) -> str:
        url = 'https://generativelanguage.googleapis.com/v1beta/models/' + self.config.model + ':generateContent'
        body = {'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0.2}}
        data = self._request_json(url, body, {'x-goog-api-key': self.config.api_key})
        try:
            return ''.join(part['text'] for part in data['candidates'][0]['content']['parts'] if 'text' in part)
        except (KeyError, IndexError, TypeError) as exc:
            raise TranslationError(f'Unexpected Gemini response: {data}') from exc

    def _openai(self, prompt: str) -> str:
        body = {'model': self.config.model, 'input': prompt, 'store': False}
        data = self._request_json('https://api.openai.com/v1/responses', body, {'Authorization': 'Bearer ' + self.config.api_key})
        try:
            return ''.join(item['text'] for output in data['output'] if output.get('type') == 'message' for item in output.get('content', []) if item.get('type') == 'output_text')
        except (KeyError, TypeError) as exc:
            raise TranslationError(f'Unexpected OpenAI response: {data}') from exc

def create_translator(provider: str, api_key: str, model: str, target_language: str) -> Translator:
    if not api_key.strip():
        raise TranslationError('API key is required.')
    if not model.strip():
        raise TranslationError('Model name is required.')
    return Translator(TranslationConfig(provider, api_key.strip(), model.strip(), target_language))
