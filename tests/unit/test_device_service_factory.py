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

def test_max_tokens_propagates_to_providers():
    # §19 migration: llm_max_output_tokens flows from config -> factory -> provider max_tokens
    assert make_provider("anthropic", max_tokens=2048)._max_tokens == 2048
    assert make_provider("openai", max_tokens=512)._max_tokens == 512
    assert make_provider("local", max_tokens=256)._max_tokens == 256

def test_provider_default_models_come_from_params_not_hardcoded():
    # §19 follow-up: factory default models/base_url are parameters (single source = Settings)
    a = make_provider("anthropic", default_model_anthropic="claude-sonnet-4-6")
    assert a._model == "claude-sonnet-4-6"
    o = make_provider("openai", default_model_openai="gpt-4o")
    assert o._model == "gpt-4o"
    loc = make_provider("local", default_model_local="llama3", local_base_url="http://localhost:9999/v1")
    assert loc._model == "llama3" and loc._base_url == "http://localhost:9999/v1"


def test_explicit_model_overrides_provider_default():
    p = make_provider("anthropic", model="claude-haiku-4-5", default_model_anthropic="other")
    assert p._model == "claude-haiku-4-5"