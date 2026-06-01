"""OpenAIProvider — OpenAI-compatible L1 classifier (OpenAI / Together / Groq /
local Ollama via base_url), ADR-009. Shared code path for the 'local' provider.

The openai SDK is imported lazily so unit tests can inject a fake client.
Uses JSON-mode chat completion and parses the JSON content.
"""
from __future__ import annotations

import json

from .parsing import result_from_dict
from .prompt import SYSTEM_PROMPT, render_sample
from .types import ClassificationResult, SanitizedSample

_JSON_INSTRUCTION = (
    " Respond ONLY with a JSON object: "
    '{"device_type": str, "confidence": number, "reasoning": str, '
    '"suggested_signals": [{"signal_name": str, "unit": str, "datatype": str, "direction": str}]}'
)


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str = "", model: str = "gpt-4o-mini", base_url: str | None = None, client=None):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._client = client

    def _ensure_client(self):
        if self._client is None:
            import openai  # lazy

            self._client = openai.OpenAI(api_key=self._api_key or "not-needed", base_url=self._base_url)
        return self._client

    @staticmethod
    def _extract_content(response) -> str:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return "{}"
        message = getattr(choices[0], "message", None)
        return (getattr(message, "content", None) or "{}") if message else "{}"

    def classify_device(
        self, device_id: str, topic: str, sanitized: SanitizedSample
    ) -> ClassificationResult:
        client = self._ensure_client()
        response = client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT + _JSON_INSTRUCTION},
                {"role": "user", "content": render_sample(sanitized)},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = self._extract_content(response)
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        return result_from_dict(data, {"provider": self.name, "model": self._model})