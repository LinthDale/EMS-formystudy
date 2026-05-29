"""Unit: output validator FR-333 — length, blacklist words, unsafe identifiers."""
from device_service.llm.types import ClassificationResult, SignalSuggestion
from device_service.output_validator import MAX_REASONING, validate


def _result(device_type="electricity", reasoning="fine", signals=None):
    signals = signals if signals is not None else (SignalSuggestion("voltage", "V", "float", "read"),)
    return ClassificationResult(device_type, tuple(signals), 0.9, reasoning)


def test_clean_result_passes_and_truncates_reasoning():
    ok, reason, cleaned = validate(_result(reasoning="x" * (MAX_REASONING + 50)))
    assert ok and reason is None and len(cleaned.reasoning) == MAX_REASONING


def test_blacklist_word_in_reasoning_rejected():
    ok, reason, _ = validate(_result(reasoning="the api_key is 123"))
    assert not ok and reason == "blacklist_word_in_reasoning"


def test_unsafe_device_type_rejected():
    ok, reason, _ = validate(_result(device_type="'; DROP TABLE devices;--"))
    assert not ok and reason == "unsafe_device_type"


def test_unsafe_signal_name_rejected():
    ok, reason, _ = validate(_result(signals=(SignalSuggestion("v$(rm -rf)", "V", "float", "read"),)))
    assert not ok and reason == "unsafe_signal_name"


def test_blacklist_word_in_signal_rejected():
    ok, reason, _ = validate(_result(signals=(SignalSuggestion("secret_reading", "V", "float", "read"),)))
    assert not ok and reason == "blacklist_word_in_signal"