from __future__ import annotations

import json
import time
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
        """Retry malformed model output; split difficult batches without losing items."""
        try:
            return self._translate_batch_once(texts)
        except TranslationError as first_error:
            try:
                return self._translate_batch_once(texts)
            except TranslationError as second_error:
                if len(texts) == 1:
                    raise TranslationError(
                        'Translation failed for one subtitle after retry: ' + str(second_error)
                    ) from second_error
                midpoint = len(texts) // 2
                return (self._translate_batch(texts[:midpoint])
                        + self._translate_batch(texts[midpoint:]))

    def _translate_batch_once(self, texts: list[str]) -> list[str]:
        payload = {'items': [{'id': i, 'text': text} for i, text in enumerate(texts)]}
        prompt = (
            'Translate subtitle lines into {target}. Preserve meaning, tone, names, numbers and profanity. '
            'Do not explain or summarize. Keep each subtitle item separate. '
            'Return ONLY valid JSON in exactly this form: {{"items":[{{"id":0,"text":"translated text"}}]}}. '
            'Keep every input id exactly once and do not add or remove items. Input JSON:\\n{payload}'
        ).format(target=self.config.target_language, payload=json.dumps(payload, ensure_ascii=False))
        if self.config.provider != 'Gemini':
            raise TranslationError(f'Unsupported provider: {self.config.provider}')
        raw = self._gemini(prompt).strip()
        if raw.startswith('```'):
            raw = raw.split('\\n', 1)[-1].rsplit('```', 1)[0].strip()
        try:
            data = json.loads(raw)
            items = data['items']
            if not isinstance(items, list):
                raise ValueError('items must be a list')
            by_id = {}
            for item in items:
                item_id = item['id']
                if not isinstance(item_id, int) or isinstance(item_id, bool) or item_id in by_id:
                    raise ValueError('Invalid or duplicate subtitle id')
                value = item['text']
                if not isinstance(value, str) or not value.strip():
                    raise ValueError('Missing subtitle text')
                by_id[item_id] = value.strip()
            if set(by_id) != set(range(len(texts))):
                raise ValueError('Missing or unexpected subtitle ids')
            return [by_id[i] for i in range(len(texts))]
        except (ValueError, TypeError, KeyError) as exc:
            raise TranslationError('Translation model returned malformed subtitle JSON: ' + str(exc)) from exc

    def _request_json(self, url: str, body: dict, headers: dict[str, str]) -> dict:
        request_body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        retryable = {429, 500, 502, 503, 504}
        last_error = None

        for attempt in range(5):
            request = urllib.request.Request(
                url, data=request_body,
                headers={'Content-Type': 'application/json', **headers}, method='POST'
            )
            try:
                with urllib.request.urlopen(request, timeout=180) as response:
                    return json.loads(response.read().decode('utf-8'))
            except urllib.error.HTTPError as exc:
                details = exc.read().decode('utf-8', errors='replace')
                last_error = exc
                if exc.code not in retryable or attempt == 4:
                    raise TranslationError(f'API request failed ({exc.code}): {details[:3000]}') from exc
                time.sleep(2 ** attempt)
            except urllib.error.URLError as exc:
                last_error = exc
                if attempt == 4:
                    raise TranslationError(f'Unable to reach translation API: {exc.reason}') from exc
                time.sleep(2 ** attempt)

        raise TranslationError('API request failed after retries.') from last_error

    def _gemini(self, prompt: str) -> str:
        url = 'https://generativelanguage.googleapis.com/v1beta/models/' + self.config.model + ':generateContent'
        body = {'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': {'responseMimeType': 'application/json'}}
        data = self._request_json(url, body, {'x-goog-api-key': self.config.api_key})
        try:
            return ''.join(part['text'] for part in data['candidates'][0]['content']['parts'] if 'text' in part)
        except (KeyError, IndexError, TypeError) as exc:
            raise TranslationError(f'Unexpected Gemini response: {data}') from exc

def create_translator(provider: str, api_key: str, model: str, target_language: str) -> Translator:
    if not api_key.strip():
        raise TranslationError('API key is required.')
    if not model.strip():
        raise TranslationError('Model name is required.')
    return Translator(TranslationConfig(provider, api_key.strip(), model.strip(), target_language))
