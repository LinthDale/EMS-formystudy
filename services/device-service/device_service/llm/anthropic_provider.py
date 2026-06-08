"""AnthropicProvider — L1 classifier via Claude (default claude-haiku-4-5, ADR-009).

Async (AsyncAnthropic) so it does not block the event loop. SDK imported lazily so
unit tests can inject a fake client. Tool-use structured output + prompt caching.
"""
from __future__ import annotations

from .parsing import result_from_dict
from .prompt import SYSTEM_PROMPT, render_sample
from .types import ClassificationResult, ProviderError, SanitizedSample

_MAX_CLASSIFY_TOKENS = 1024  # one tool-use block; classification output is small

_CLASSIFY_TOOL = {
    "name": "record_classification",
    "description": "Record the device classification.",
    "input_schema": {
        "type": "object",
        "properties": {
            "device_type": {"type": "string"},
            "confidence": {"type": "number"},
            "reasoning": {"type": "string"},
            "suggested_signals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "signal_name": {"type": "string"},
                        "unit": {"type": "string"},
                        "datatype": {"type": "string"},
                        "direction": {"type": "string"},
                    },
                    "required": ["signal_name"],
                },
            },
        },
        "required": ["device_type", "confidence"],
    },
}


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str = "", model: str = "claude-haiku-4-5", max_tokens: int = _MAX_CLASSIFY_TOKENS, client=None):
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._client = client

    def _ensure_client(self):
        if self._client is None:
            import anthropic  # lazy: not needed when a client is injected

            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
        return self._client

    @staticmethod
    def _extract_tool_input(response) -> dict:
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "tool_use":
                inp = getattr(block, "input", None)
                return dict(inp) if isinstance(inp, dict) else {}
        return {}

    async def classify_device(
        self, device_id: str, topic: str, sanitized: SanitizedSample
    ) -> ClassificationResult:
        client = self._ensure_client()
        try:
            response = await client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                tools=[_CLASSIFY_TOOL],
                tool_choice={"type": "tool", "name": "record_classification"},
                messages=[{"role": "user", "content": render_sample(sanitized)}],
            )
        except Exception as exc:  # SDK / network / rate-limit -> single boundary error
            raise ProviderError(f"anthropic classify_device failed: {exc}") from exc
        data = self._extract_tool_input(response)
        raw = {"provider": self.name, "model": self._model}
        usage = getattr(response, "usage", None)
        if usage is not None:
            raw["usage"] = {
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            }
        return result_from_dict(data, raw)