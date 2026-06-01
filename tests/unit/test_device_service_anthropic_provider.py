"""Unit: AnthropicProvider with an injected fake async client (no SDK, no API key)."""
import pytest

from device_service.llm.anthropic_provider import AnthropicProvider
from device_service.llm.provider import LLMProvider
from device_service.llm.types import ProviderError
from device_service.sanitizer import sanitize


class _ToolBlock:
    type = "tool_use"

    def __init__(self, inp):
        self.input = inp


class _Resp:
    def __init__(self, content):
        self.content = content


class _Messages:
    def __init__(self, resp=None, error=None):
        self._resp = resp
        self._error = error
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._resp


class FakeAnthropic:
    def __init__(self, resp=None, error=None):
        self.messages = _Messages(resp, error)


def _sample():
    return sanitize("sim-001", "ems/devices/sim-001/measurements", "ilp", [{"voltage": 220.0}])


def test_is_provider_and_named():
    assert isinstance(AnthropicProvider(client=FakeAnthropic(_Resp([]))), LLMProvider)
    assert AnthropicProvider(client=object()).name == "anthropic"


async def test_parses_tool_use_response():
    fake = FakeAnthropic(_Resp([_ToolBlock({
        "device_type": "electricity", "confidence": 0.95, "reasoning": "ok",
        "suggested_signals": [{"signal_name": "voltage", "unit": "V", "datatype": "float", "direction": "read"}],
    })]))
    r = await AnthropicProvider(client=fake).classify_device("sim-001", "t", _sample())
    assert r.device_type == "electricity" and r.suggested_signals[0].signal_name == "voltage"


async def test_sends_prompt_caching_and_tool_choice():
    fake = FakeAnthropic(_Resp([_ToolBlock({"device_type": "x", "confidence": 0.1})]))
    await AnthropicProvider(client=fake).classify_device("d", "t", _sample())
    kw = fake.messages.calls[0]
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kw["tool_choice"]["name"] == "record_classification"


async def test_no_tool_use_block_yields_unknown():
    r = await AnthropicProvider(client=FakeAnthropic(_Resp([]))).classify_device("d", "t", _sample())
    assert r.device_type == "unknown"


async def test_non_dict_tool_input_yields_empty():
    fake = FakeAnthropic(_Resp([_ToolBlock("not-a-dict")]))
    r = await AnthropicProvider(client=fake).classify_device("d", "t", _sample())
    assert r.device_type == "unknown"


async def test_sdk_error_raises_provider_error():
    fake = FakeAnthropic(error=RuntimeError("rate limited"))
    with pytest.raises(ProviderError):
        await AnthropicProvider(client=fake).classify_device("d", "t", _sample())