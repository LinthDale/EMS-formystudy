"""Unit: AnthropicProvider with an injected fake client (no SDK, no API key)."""
from device_service.llm.anthropic_provider import AnthropicProvider
from device_service.llm.provider import LLMProvider
from device_service.sanitizer import sanitize


class _ToolBlock:
    type = "tool_use"

    def __init__(self, inp):
        self.input = inp


class _Resp:
    def __init__(self, content):
        self.content = content


class _Messages:
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._resp


class FakeAnthropic:
    def __init__(self, resp):
        self.messages = _Messages(resp)


def _sample():
    return sanitize("sim-001", "ems/devices/sim-001/measurements", "ilp", [{"voltage": 220.0}])


def test_is_provider_and_named():
    assert isinstance(AnthropicProvider(client=FakeAnthropic(_Resp([]))), LLMProvider)
    assert AnthropicProvider(client=object()).name == "anthropic"


def test_parses_tool_use_response():
    fake = FakeAnthropic(_Resp([_ToolBlock({
        "device_type": "electricity", "confidence": 0.95, "reasoning": "ok",
        "suggested_signals": [{"signal_name": "voltage", "unit": "V", "datatype": "float", "direction": "read"}],
    })]))
    p = AnthropicProvider(client=fake, model="claude-haiku-4-5")
    r = p.classify_device("sim-001", "ems/devices/sim-001/measurements", _sample())
    assert r.device_type == "electricity" and r.suggested_signals[0].signal_name == "voltage"


def test_sends_prompt_caching_and_tool_choice():
    fake = FakeAnthropic(_Resp([_ToolBlock({"device_type": "x", "confidence": 0.1})]))
    AnthropicProvider(client=fake).classify_device("d", "t", _sample())
    kw = fake.messages.calls[0]
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kw["tool_choice"]["name"] == "record_classification"


def test_no_tool_use_block_yields_unknown():
    p = AnthropicProvider(client=FakeAnthropic(_Resp([])))
    r = p.classify_device("d", "t", _sample())
    assert r.device_type == "unknown"