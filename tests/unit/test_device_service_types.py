"""Unit: LLM contract dataclasses are immutable (ADR-009)."""
import dataclasses

import pytest

from device_service.llm.types import (
    ClassificationResult, FieldSummary, SanitizedSample, SignalSuggestion,
)


def test_sanitized_sample_is_frozen():
    s = SanitizedSample("v1", "sim-001", "ems/devices/sim-001/measurements", "ilp", 3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.device_id = "evil"  # type: ignore[misc]


def test_field_summary_defaults():
    f = FieldSummary("voltage", "float", value_min=219.0, value_max=221.0, sample_count=3)
    assert f.distinct_count is None and f.bool_true_ratio is None


def test_classification_result_holds_tuple_signals():
    r = ClassificationResult(
        "electricity",
        (SignalSuggestion("voltage", "V", "float", "read"),),
        0.95, "ok",
    )
    assert r.suggested_signals[0].unit == "V"
    assert isinstance(r.raw_response, dict)