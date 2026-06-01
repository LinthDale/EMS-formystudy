"""OpenAIProvider — OpenAI-compatible L1 classifier (OpenAI / Together / Groq /
local Ollama via base_url), ADR-009. Shared code path for the 'local' provider.

Async (AsyncOpenAI), SDK imported lazily. Tries JSON-mode; if the server rejects
response_format (common for Ollama base models) it retries without it, then parses
the JSON content. SDK errors are re-raised as ProviderError. Token usage (when the
server reports it) is surfaced in raw_response['usage'] for the budget ledger.
"""
from __future__ import annotations

import json

from .parsing import result_from_dict
from .prompt import SYSTEM_PROMPT, render_sample
from .types import ClassificationResult, ProviderError, SanitizedSample

_MAX_OUTPUT_TOKENS = 1024  # must match budget_ledger.RESERVE_OUTPUT_TOKENS so the reservation is a true upper bound

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

            self._client = openai.AsyncOpenAI(api_key=self._api_key or "not-needed", base_url=self._base_url)
        return self._client

    @staticmethod
    def _extract_content(response) -> str:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return "{}"
        message = getattr(choices[0], "message", None)
        return (getattr(message, "content", None) or "{}") if message else "{}"

    @staticmethod
    def _extract_usage(response) -> dict | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        return {
            "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        }

    async def _complete(self, client, sanitized: SanitizedSample):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + _JSON_INSTRUCTION},
            {"role": "user", "content": render_sample(sanitized)},
        ]
        try:
            return await client.chat.completions.create(
                model=self._model, messages=messages, max_tokens=_MAX_OUTPUT_TOKENS,
                response_format={"type": "json_object"}, temperature=0,
            )
        except Exception:
            try:
                return await client.chat.completions.create(
                    model=self._model, messages=messages, max_tokens=_MAX_OUTPUT_TOKENS, temperature=0,
                )
            except Exception as exc:
                raise ProviderError(f"openai classify_device failed: {exc}") from exc

    async def classify_device(
        self, device_id: str, topic: str, sanitized: SanitizedSample
    ) -> ClassificationResult:
        client = self._ensure_client()
        response = await self._complete(client, sanitized)
        try:
            data = json.loads(self._extract_content(response))
        except (json.JSONDecodeError, TypeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        raw = {"provider": self.name, "model": self._model}
        usage = self._extract_usage(response)
        if usage is not None:
            raw["usage"] = usage
        return result_from_dict(data, raw)