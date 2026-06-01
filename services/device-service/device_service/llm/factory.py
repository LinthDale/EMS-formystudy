"""Provider factory — select L1 provider by config (FR-305, ADR-009)."""
from __future__ import annotations

from .anthropic_provider import AnthropicProvider
from .mock_provider import MockProvider
from .openai_provider import OpenAIProvider
from .provider import LLMProvider

# Default base URL for the 'local' provider (Ollama OpenAI-compatible endpoint).
DEFAULT_LOCAL_BASE_URL = "http://host.docker.internal:11434/v1"


def make_provider(
    provider: str,
    *,
    api_key: str = "",
    model: str = "",
    base_url: str | None = None,
) -> LLMProvider:
    p = (provider or "mock").lower()
    if p == "mock":
        return MockProvider()
    if p == "anthropic":
        return AnthropicProvider(api_key=api_key, model=model or "claude-haiku-4-5")
    if p == "openai":
        return OpenAIProvider(api_key=api_key, model=model or "gpt-4o-mini", base_url=base_url)
    if p == "local":
        # local = OpenAI-compatible code path against a local server (e.g. Ollama)
        return OpenAIProvider(
            api_key=api_key or "ollama",
            model=model or "qwen2.5",
            base_url=base_url or DEFAULT_LOCAL_BASE_URL,
        )
    raise ValueError(f"unknown LLM_PROVIDER: {provider!r}")