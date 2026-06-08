"""Unit: correction→prompt-context assembly + 32KB cap (PRD §8.6.4 / §8.6.5a, FR-331).
Pure functions, no DB."""
from datetime import datetime, timezone

from device_service.correction_context import (
    build_context,
    cap_to_prompt_size,
    device_type_family,
    topic_prefix,
)
from device_service.llm.types import CorrectionContext, FieldSummary, SanitizedSample


def _sample(corrections=()):
    return SanitizedSample(
        schema_version="v1", device_id="d1", topic="ems/factory/d1/measurements",
        payload_format="ilp", sample_count=3,
        fields=(FieldSummary("voltage", "float", value_min=1.0, value_max=2.0, sample_count=3),),
        human_corrections=tuple(corrections),
    )


def _ctx(i: int, explanation: str = "x" * 100) -> CorrectionContext:
    return CorrectionContext(
        verdict="wrong_classification", corrected_device_type="electricity",
        explanation_truncated=f"{i}:{explanation}", created_at_iso="2026-06-01T00:00:00+00:00",
    )


# ── device_type_family ────────────────────────────────────────────────────────
def test_device_type_family_defaults_to_self_and_empty_for_none():
    assert device_type_family("electricity") == ("electricity",)
    assert device_type_family(None) == ()
    assert device_type_family("") == ()


def test_device_type_family_uses_configured_mapping(monkeypatch):
    import device_service.correction_context as cc
    monkeypatch.setattr(cc, "DEVICE_TYPE_FAMILIES", {"electricity": ("electricity", "power_meter")})
    assert cc.device_type_family("electricity") == ("electricity", "power_meter")
    assert cc.device_type_family("pressure") == ("pressure",)  # unmapped -> singleton


# ── topic_prefix ──────────────────────────────────────────────────────────────
def test_topic_prefix_first_two_segments():
    assert topic_prefix("ems/factory/d1/measurements") == "ems/factory"
    assert topic_prefix("factory/sensor/s1") == "factory/sensor"
    assert topic_prefix("singletoken") == ""
    assert topic_prefix("") == ""
    assert topic_prefix(None) == ""
    assert topic_prefix("ems/") == ""        # empty 2nd segment -> not matchable
    assert topic_prefix("/x") == ""          # empty 1st segment -> not matchable


# ── build_context ─────────────────────────────────────────────────────────────
def test_build_context_maps_row_and_truncates_explanation():
    row = {
        "verdict": "wrong_unit", "corrected_device_type": "pressure",
        "human_explanation": "y" * 800,
        "created_at": datetime(2026, 6, 1, tzinfo=timezone.utc),
    }
    ctx = build_context(row)
    assert ctx.verdict == "wrong_unit" and ctx.corrected_device_type == "pressure"
    assert len(ctx.explanation_truncated) == 500           # capped
    assert ctx.created_at_iso == "2026-06-01T00:00:00+00:00"


def test_build_context_handles_missing_created_at_and_fields():
    ctx = build_context({"verdict": "good_with_note", "human_explanation": None, "created_at": None})
    assert ctx.created_at_iso == "" and ctx.explanation_truncated == ""
    assert ctx.corrected_device_type is None


# ── cap_to_prompt_size ────────────────────────────────────────────────────────
def test_cap_keeps_all_when_under_limit():
    ctxs = [_ctx(i) for i in range(3)]
    kept, truncated = cap_to_prompt_size(_sample(), ctxs, cap_bytes=1_000_000)
    assert truncated is False and len(kept) == 3


def test_cap_drops_oldest_until_under_limit_keeping_prefix():
    ctxs = [_ctx(i, explanation="z" * 400) for i in range(8)]  # most-recent-first
    kept, truncated = cap_to_prompt_size(_sample(), ctxs, cap_bytes=1500)
    assert truncated is True
    assert 0 < len(kept) < 8
    # kept is a PREFIX of the input (oldest dropped from the tail)
    assert list(kept) == ctxs[: len(kept)]


def test_cap_empty_contexts_is_noop():
    kept, truncated = cap_to_prompt_size(_sample(), [], cap_bytes=10)
    assert kept == () and truncated is False


def test_cap_can_drop_all_when_fields_alone_exceed_cap():
    ctxs = [_ctx(i) for i in range(3)]
    kept, truncated = cap_to_prompt_size(_sample(), ctxs, cap_bytes=1)  # nothing fits
    assert kept == () and truncated is True
