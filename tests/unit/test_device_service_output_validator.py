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

# --- regression tests from code review (RED first) ---

def test_blacklist_in_device_type_rejected():
    """CRITICAL-2: blacklist word in device_type must be rejected."""
    ok, reason, _ = validate(_result(device_type="token_device"))
    assert not ok and reason == "blacklist_word_in_device_type"


def test_fullwidth_blacklist_rejected():
    """HIGH-2: full-width homoglyph of 'token' caught after NFKC normalize."""
    ok, _, _ = validate(_result(reasoning="leaked ｔｏｋｅｎ here"))
    assert not ok


def test_zero_width_blacklist_rejected():
    """HIGH-2: zero-width char inside 'secret' must still be caught."""
    ok, _, _ = validate(_result(reasoning="the se" + chr(0x200b) + "cret was leaked"))
    assert not ok


def test_whitespace_only_device_type_rejected():
    """MEDIUM-2: whitespace-only device_type must be rejected."""
    ok, reason, _ = validate(_result(device_type="   "))
    assert not ok and reason == "unsafe_device_type"


def test_confidence_out_of_range_rejected():
    """MEDIUM-3: confidence outside 0..1 must be rejected."""
    from device_service.llm.types import ClassificationResult, SignalSuggestion
    r = ClassificationResult("electricity", (SignalSuggestion("voltage", "V", "float", "read"),), 1.5, "ok")
    ok, reason, _ = validate(r)
    assert not ok and reason == "confidence_out_of_range"

def test_unsafe_signal_unit_rejected():
    """output_validator: a unit containing unsafe chars must be rejected."""
    ok, reason, _ = validate(_result(signals=(SignalSuggestion("flow", "m3; DROP", "float", "read"),)))
    assert not ok and reason == "unsafe_signal_unit"