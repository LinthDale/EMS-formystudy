"""Unit: MockProvider deterministic classification (ADR-009)."""
from device_service.llm.mock_provider import MockProvider
from device_service.llm.provider import LLMProvider
from device_service.sanitizer import sanitize


def _sample(rows, topic="ems/devices/sim-001/measurements", payload="ilp"):
    return sanitize("sim-001", topic, payload, rows)


def test_satisfies_llm_provider_protocol():
    assert isinstance(MockProvider(), LLMProvider)
    assert MockProvider().name == "mock"


def test_classifies_electricity_from_fields():
    s = _sample([{"voltage": 220.0, "current": 1.1, "power_kw": 0.2}])
    r = MockProvider().classify_device("sim-001", s.topic, s)
    assert r.device_type == "electricity" and r.confidence > 0.9
    assert {sig.signal_name for sig in r.suggested_signals} == {"voltage", "current", "power_kw"}


def test_classifies_temperature():
    s = _sample([{"temperature": 25.0, "humidity": 60.0}], topic="ems/factory/sensor-001/measurements")
    r = MockProvider().classify_device("sensor-001", s.topic, s)
    assert r.device_type == "temperature"


def test_unknown_fallback_low_confidence():
    s = _sample([{"weird_metric": 1.0}], topic="x/y/z")
    r = MockProvider().classify_device("d", s.topic, s)
    assert r.device_type == "unknown" and r.confidence < 0.5


def test_deterministic_same_input_same_output():
    s = _sample([{"pressure": 101.0}], topic="ems/factory/plc/measurements")
    a = MockProvider().classify_device("d", s.topic, s)
    b = MockProvider().classify_device("d", s.topic, s)
    assert a == b


def test_bool_field_maps_to_bool_datatype():
    s = _sample([{"valve_open": True}], topic="ems/factory/plc/measurements")
    r = MockProvider().classify_device("d", s.topic, s)
    assert any(sig.datatype == "bool" for sig in r.suggested_signals)