"""Unit: human-review digest builder (§8.4, FR-317)."""
from device_service.digest import SCHEMA_VERSION, build_fallback_digest, build_llm_digest
from device_service.llm.types import ClassificationResult, SignalSuggestion
from device_service.sanitizer import sanitize


def _sample():
    return sanitize("sim-001", "ems/devices/sim-001/measurements", "ilp",
                    [{"voltage": 220.0, "pump_on": True}])


def test_llm_digest_shape():
    r = ClassificationResult("electricity", (SignalSuggestion("voltage", "V", "float", "read"),), 0.952, "looks electrical")
    d = build_llm_digest(_sample(), r, provider="anthropic", model="claude-haiku-4-5",
                         first_seen_at="t0", generated_at="t1")
    assert d["schema_version"] == SCHEMA_VERSION and d["summary_source"] == "llm"
    assert d["ai_provider"] == "anthropic" and d["ai_confidence"] == 0.95
    assert d["suggested_device_type"] == "electricity"
    assert d["suggested_signals"][0]["signal_name"] == "voltage"
    assert d["sample_digest"]["topic"] == "ems/devices/sim-001/measurements"
    assert "voltage" in d["sample_digest"]["field_value_examples"]


def test_fallback_digest_shape():
    d = build_fallback_digest(_sample(), "electricity", first_seen_at="t0", generated_at="t1")
    assert d["summary_source"] == "system_fallback" and d["ai_provider"] is None
    assert d["ai_confidence"] == 0.0 and d["why_low_confidence"] == "LLM 不可用，請人工判斷"
    assert d["suggested_device_type"] == "electricity"
    names = [s["signal_name"] for s in d["suggested_signals"]]
    assert "voltage" in names and all(s["unit"] is None for s in d["suggested_signals"])
    assert "sim-001" in d["summary_zh"] and "ems/devices/sim-001/measurements" in d["summary_zh"]

def test_field_examples_none_for_string_field():
    s = sanitize("d", "t", "json", [{"label": "abc"}, {"label": "xyz"}])  # string -> distinct only
    d = build_fallback_digest(s, "unknown", first_seen_at="t0", generated_at="t1")
    assert d["sample_digest"]["field_value_examples"]["label"] is None