"""Unit: OpenAIProvider with an injected fake client (no SDK, no API key)."""
from device_service.llm.openai_provider import OpenAIProvider
from device_service.llm.provider import LLMProvider
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
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._resp


class _Chat:
    def __init__(self, resp):
        self.completions = _Completions(resp)


class FakeOpenAI:
    def __init__(self, resp):
        self.chat = _Chat(resp)


def _sample():
    return sanitize("sensor-001", "ems/factory/sensor-001/measurements", "json", [{"temperature": 25.0}])


def test_is_provider_and_named():
    assert isinstance(OpenAIProvider(client=FakeOpenAI(_Resp("{}"))), LLMProvider)
    assert OpenAIProvider(client=object()).name == "openai"


def test_parses_json_content():
    fake = FakeOpenAI(_Resp('{"device_type": "temperature", "confidence": 0.8, "reasoning": "r", "suggested_signals": []}'))
    r = OpenAIProvider(client=fake).classify_device("sensor-001", "t", _sample())
    assert r.device_type == "temperature" and r.confidence == 0.8


def test_invalid_json_yields_unknown():
    r = OpenAIProvider(client=FakeOpenAI(_Resp("not json at all"))).classify_device("d", "t", _sample())
    assert r.device_type == "unknown"


def test_json_array_content_yields_unknown():
    r = OpenAIProvider(client=FakeOpenAI(_Resp("[1,2,3]"))).classify_device("d", "t", _sample())
    assert r.device_type == "unknown"


def test_sends_json_response_format():
    fake = FakeOpenAI(_Resp("{}"))
    OpenAIProvider(client=fake).classify_device("d", "t", _sample())
    assert fake.chat.completions.calls[0]["response_format"] == {"type": "json_object"}

def test_empty_choices_yields_unknown():
    class _EmptyResp:
        choices = []
    class _Comp:
        def create(self, **kw): return _EmptyResp()
    class _ChatE:
        def __init__(self): self.completions = _Comp()
    class _FakeEmpty:
        def __init__(self): self.chat = _ChatE()
    r = OpenAIProvider(client=_FakeEmpty()).classify_device("d", "t", _sample())
    assert r.device_type == "unknown"