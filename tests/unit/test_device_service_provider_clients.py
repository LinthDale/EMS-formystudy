"""Unit: lazy real-SDK client construction (offline, no API call).

Requires the anthropic / openai SDKs to be importable; construction makes no
network request. Skipped automatically if a SDK is absent.
"""
import pytest

from device_service.llm.anthropic_provider import AnthropicProvider
from device_service.llm.openai_provider import OpenAIProvider


def test_anthropic_ensure_client_builds_real_client():
    pytest.importorskip("anthropic")
    p = AnthropicProvider(api_key="sk-test")
    client = p._ensure_client()
    assert client is not None
    assert p._ensure_client() is client  # cached


def test_openai_ensure_client_builds_real_client():
    pytest.importorskip("openai")
    p = OpenAIProvider(api_key="sk-test", base_url="http://localhost:11434/v1")
    client = p._ensure_client()
    assert client is not None
    assert p._ensure_client() is client  # cached