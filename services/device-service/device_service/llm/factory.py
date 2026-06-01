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
    max_tokens: int = 1024,
    default_model_anthropic: str = "claude-haiku-4-5",
    default_model_openai: str = "gpt-4o-mini",
    default_model_local: str = "qwen2.5",
    local_base_url: str = DEFAULT_LOCAL_BASE_URL,
) -> LLMProvider:
    p = (provider or "mock").lower()
    if p == "mock":
        return MockProvider()
    if p == "anthropic":
        return AnthropicProvider(api_key=api_key, model=model or default_model_anthropic, max_tokens=max_tokens)
    if p == "openai":
        return OpenAIProvider(api_key=api_key, model=model or default_model_openai, base_url=base_url, max_tokens=max_tokens)
    if p == "local":
        # local = OpenAI-compatible code path against a local server (e.g. Ollama)
        return OpenAIProvider(
            api_key=api_key or "ollama",
            model=model or default_model_local,
            base_url=base_url or local_base_url, max_tokens=max_tokens,
        )
    raise ValueError(f"unknown LLM_PROVIDER: {provider!r}")