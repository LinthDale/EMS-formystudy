"""Unit: provider factory (FR-305)."""
import pytest

from device_service.llm.anthropic_provider import AnthropicProvider
from device_service.llm.factory import DEFAULT_LOCAL_BASE_URL, make_provider
from device_service.llm.mock_provider import MockProvider
from device_service.llm.openai_provider import OpenAIProvider


def test_mock_default_and_explicit():
    assert isinstance(make_provider(""), MockProvider)
    assert isinstance(make_provider("mock"), MockProvider)


def test_anthropic():
    p = make_provider("anthropic", api_key="k")
    assert isinstance(p, AnthropicProvider) and p.name == "anthropic"


def test_openai():
    assert isinstance(make_provider("openai", api_key="k"), OpenAIProvider)


def test_local_uses_openai_path_with_default_base_url():
    p = make_provider("local")
    assert isinstance(p, OpenAIProvider) and p._base_url == DEFAULT_LOCAL_BASE_URL


def test_local_respects_explicit_base_url():
    p = make_provider("local", base_url="http://localhost:1234/v1")
    assert p._base_url == "http://localhost:1234/v1"


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        make_provider("gemini")