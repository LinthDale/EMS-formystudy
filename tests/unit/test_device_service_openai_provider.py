"""Unit: OpenAIProvider with an injected fake async client (no SDK, no API key)."""
import pytest

from device_service.llm.openai_provider import OpenAIProvider
from device_service.llm.provider import LLMProvider
from device_service.llm.types import ProviderError
from device_service.sanitizer import sanitize


class _Message:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Message(content)


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class _Completions:
    def __init__(self, resp=None, errors=()):
        self._resp = resp
        self._errors = list(errors)  # raised in order, one per call
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._errors:
            raise self._errors.pop(0)
        return self._resp


class _Chat:
    def __init__(self, comp):
        self.completions = comp


class FakeOpenAI:
    def __init__(self, resp=None, errors=()):
        self.chat = _Chat(_Completions(resp, errors))


def _sample():
    return sanitize("sensor-001", "ems/factory/sensor-001/measurements", "json", [{"temperature": 25.0}])


def test_is_provider_and_named():
    assert isinstance(OpenAIProvider(client=FakeOpenAI(_Resp("{}"))), LLMProvider)
    assert OpenAIProvider(client=object()).name == "openai"


async def test_parses_json_content():
    fake = FakeOpenAI(_Resp('{"device_type": "temperature", "confidence": 0.8, "reasoning": "r", "suggested_signals": []}'))
    r = await OpenAIProvider(client=fake).classify_device("sensor-001", "t", _sample())
    assert r.device_type == "temperature" and r.confidence == 0.8


async def test_invalid_json_yields_unknown():
    r = await OpenAIProvider(client=FakeOpenAI(_Resp("not json at all"))).classify_device("d", "t", _sample())
    assert r.device_type == "unknown"


async def test_json_array_content_yields_unknown():
    r = await OpenAIProvider(client=FakeOpenAI(_Resp("[1,2,3]"))).classify_device("d", "t", _sample())
    assert r.device_type == "unknown"


async def test_sends_json_response_format_to_sdk():
    fake = FakeOpenAI(_Resp("{}"))
    await OpenAIProvider(client=fake).classify_device("d", "t", _sample())
    assert fake.chat.completions.calls[0]["response_format"] == {"type": "json_object"}


async def test_empty_choices_yields_unknown():
    class _EmptyResp:
        choices = []

    class _Comp:
        async def create(self, **kw):
            return _EmptyResp()

    class _ChatE:
        def __init__(self):
            self.completions = _Comp()

    class _FakeEmpty:
        def __init__(self):
            self.chat = _ChatE()

    r = await OpenAIProvider(client=_FakeEmpty()).classify_device("d", "t", _sample())
    assert r.device_type == "unknown"


async def test_retries_without_json_mode_when_server_rejects_it():
    # first call (with response_format) raises; second (plain) succeeds — Ollama path
    fake = FakeOpenAI(_Resp('{"device_type": "pressure", "confidence": 0.7}'), errors=[RuntimeError("json_object not supported")])
    r = await OpenAIProvider(client=fake).classify_device("d", "t", _sample())
    assert r.device_type == "pressure"
    assert len(fake.chat.completions.calls) == 2
    assert "response_format" not in fake.chat.completions.calls[1]


async def test_both_attempts_fail_raises_provider_error():
    fake = FakeOpenAI(errors=[RuntimeError("boom1"), RuntimeError("boom2")])
    with pytest.raises(ProviderError):
        await OpenAIProvider(client=fake).classify_device("d", "t", _sample())