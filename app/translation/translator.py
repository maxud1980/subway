from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from app.net import urlopen
from app.process import CancelToken, Cancelled


class TranslationError(RuntimeError):
    pass


@dataclass(frozen=True)
class TranslationConfig:
    provider: str
    api_key: str
    model: str
    target_language: str
    batch_size: int = 30
    source_language: str = "auto"
    notes: str = ""  # Glossary and context supplied by the user.
    context_lines: int = 8


def _strip_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1] if "\n" in raw else raw[3:]
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()


class Translator:
    def __init__(self, config: TranslationConfig):
        self.config = config

    def translate(
        self,
        texts: list[str],
        cancel: CancelToken | None = None,
        progress: Callable[[float], None] | None = None,
    ) -> list[str]:
        """Translate subtitle texts, giving the model the previous lines as context."""
        flat = [" ".join(text.split()) for text in texts]
        result: list[str] = []
        size = max(1, self.config.batch_size)
        for start in range(0, len(flat), size):
            if cancel is not None and cancel.cancelled:
                raise Cancelled()
            batch = flat[start:start + size]
            keep = max(0, self.config.context_lines)
            context = list(zip(flat[max(0, start - keep):start], result[max(0, start - keep):start])) if keep else []
            result.extend(self._translate_batch(batch, context))
            if progress:
                progress(min(len(result) / len(flat), 1.0))
        return result

    def _translate_batch(self, texts: list[str], context: list[tuple[str, str]] | None = None) -> list[str]:
        """Retry malformed model output; split difficult batches without losing items."""
        try:
            return self._translate_batch_once(texts, context)
        except TranslationError:
            try:
                return self._translate_batch_once(texts, context)
            except TranslationError as second_error:
                if len(texts) == 1:
                    raise TranslationError(
                        "Translation failed for one subtitle after retry: " + str(second_error)
                    ) from second_error
                midpoint = len(texts) // 2
                first = self._translate_batch(texts[:midpoint], context)
                tail_context = (list(context or []) + list(zip(texts[:midpoint], first)))[-max(1, self.config.context_lines):]
                return first + self._translate_batch(texts[midpoint:], tail_context)

    def build_prompt(self, texts: list[str], context: list[tuple[str, str]] | None = None) -> str:
        payload = {"items": [{"id": i, "text": text} for i, text in enumerate(texts)]}
        source = "" if self.config.source_language in ("", "auto") else f" from {self.config.source_language}"
        parts = [
            f"You translate video subtitles{source} into {self.config.target_language}.",
            "Preserve meaning, tone, register, names, numbers and profanity. "
            "Keep sentences that continue across items natural in the target language, "
            "but keep every item as a separate subtitle. Do not explain, summarize or censor.",
            "Keep translations about as short as the original so they remain readable on screen.",
        ]
        if self.config.notes.strip():
            parts.append("Glossary and notes from the author (follow them strictly):\n" + self.config.notes.strip())
        if context:
            lines = "\n".join(f"- {src} => {dst}" for src, dst in context)
            parts.append("Previous subtitles and their translations, for context only (do NOT include them in the output):\n" + lines)
        parts.append(
            'Return ONLY valid JSON in exactly this form: {"items":[{"id":0,"text":"translated text"}]}. '
            "Keep every input id exactly once and do not add or remove items."
        )
        parts.append("Input JSON:\n" + json.dumps(payload, ensure_ascii=False))
        return "\n\n".join(parts)

    def _translate_batch_once(self, texts: list[str], context: list[tuple[str, str]] | None = None) -> list[str]:
        if self.config.provider != "Gemini":
            raise TranslationError(f"Unsupported provider: {self.config.provider}")
        raw = _strip_fence(self._gemini(self.build_prompt(texts, context)))
        try:
            data = json.loads(raw)
            items = data["items"]
            if not isinstance(items, list):
                raise ValueError("items must be a list")
            by_id = {}
            for item in items:
                item_id = item["id"]
                if not isinstance(item_id, int) or isinstance(item_id, bool) or item_id in by_id:
                    raise ValueError("Invalid or duplicate subtitle id")
                value = item["text"]
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("Missing subtitle text")
                by_id[item_id] = " ".join(value.split())
            if set(by_id) != set(range(len(texts))):
                raise ValueError("Missing or unexpected subtitle ids")
            return [by_id[i] for i in range(len(texts))]
        except (ValueError, TypeError, KeyError) as exc:
            raise TranslationError("Translation model returned malformed subtitle JSON: " + str(exc)) from exc

    def _request_json(self, url: str, body: dict, headers: dict[str, str]) -> dict:
        request_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        retryable = {429, 500, 502, 503, 504}
        last_error = None

        for attempt in range(5):
            request = urllib.request.Request(
                url, data=request_body,
                headers={"Content-Type": "application/json", **headers}, method="POST",
            )
            try:
                with urlopen(request, timeout=180) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                details = exc.read().decode("utf-8", errors="replace")
                last_error = exc
                if exc.code not in retryable or attempt == 4:
                    raise TranslationError(f"API request failed ({exc.code}): {details[:3000]}") from exc
                time.sleep(2 ** attempt)
            except urllib.error.URLError as exc:
                last_error = exc
                if attempt == 4:
                    raise TranslationError(f"Unable to reach translation API: {exc.reason}") from exc
                time.sleep(2 ** attempt)
            except (TimeoutError, ConnectionError, http.client.HTTPException) as exc:
                # The connection opened but the answer stalled or broke off mid-way.
                last_error = exc
                if attempt == 4:
                    raise TranslationError(f"The translation API did not answer in time ({exc}).") from exc
                time.sleep(2 ** attempt)

        raise TranslationError("API request failed after retries.") from last_error

    def _gemini(self, prompt: str) -> str:
        url = "https://generativelanguage.googleapis.com/v1beta/models/" + self.config.model + ":generateContent"
        body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}}
        data = self._request_json(url, body, {"x-goog-api-key": self.config.api_key})
        try:
            return "".join(part["text"] for part in data["candidates"][0]["content"]["parts"] if "text" in part)
        except (KeyError, IndexError, TypeError) as exc:
            reason = ""
            if isinstance(data, dict):
                feedback = data.get("promptFeedback") or {}
                reason = feedback.get("blockReason", "") if isinstance(feedback, dict) else ""
            if reason:
                raise TranslationError(f"Gemini refused to translate this part (reason: {reason}).") from exc
            raise TranslationError(f"Unexpected Gemini response: {str(data)[:1000]}") from exc


def create_translator(provider: str, api_key: str, model: str, target_language: str,
                      source_language: str = "auto", notes: str = "") -> Translator:
    if not api_key.strip():
        raise TranslationError("API key is required.")
    if not model.strip():
        raise TranslationError("Model name is required.")
    return Translator(TranslationConfig(provider, api_key.strip(), model.strip(), target_language,
                                        source_language=source_language, notes=notes))
