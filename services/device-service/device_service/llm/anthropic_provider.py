"""AnthropicProvider — L1 classifier via Claude (default claude-haiku-4-5, ADR-009).

The anthropic SDK is imported lazily (only when a real client is built), so unit
tests can inject a fake client without the dependency installed. Uses tool-use
for structured output and prompt caching on the (static) system prompt.
"""
from __future__ import annotations

from .parsing import result_from_dict
from .prompt import SYSTEM_PROMPT, render_sample
from .types import ClassificationResult, SanitizedSample

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

    def __init__(self, api_key: str = "", model: str = "claude-haiku-4-5", client=None):
        self._api_key = api_key
        self._model = model
        self._client = client

    def _ensure_client(self):
        if self._client is None:
            import anthropic  # lazy: not needed when a client is injected

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    @staticmethod
    def _extract_tool_input(response) -> dict:
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "tool_use":
                return dict(getattr(block, "input", {}) or {})
        return {}

    def classify_device(
        self, device_id: str, topic: str, sanitized: SanitizedSample
    ) -> ClassificationResult:
        client = self._ensure_client()
        response = client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            tools=[_CLASSIFY_TOOL],
            tool_choice={"type": "tool", "name": "record_classification"},
            messages=[{"role": "user", "content": render_sample(sanitized)}],
        )
        data = self._extract_tool_input(response)
        return result_from_dict(data, {"provider": self.name, "model": self._model})