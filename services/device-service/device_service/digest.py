"""Human-review digest builder (PRD-0003 §8.4, FR-317).

Fixed field order; built only from a SanitizedSample (no raw payload values).
Persisted to device_review_digests on every classification (incl. fallback).
"""
from __future__ import annotations

from .llm.types import ClassificationResult, SanitizedSample

SCHEMA_VERSION = "1.0"
_FALLBACK_WHY = "LLM 不可用，請人工判斷"


def _field_examples(sanitized: SanitizedSample) -> dict:
    out: dict = {}
    for f in sanitized.fields:
        if f.bool_true_ratio is not None:
            out[f.field_name] = f.bool_true_ratio
        elif f.value_min is not None:
            out[f.field_name] = f.value_min
        else:
            out[f.field_name] = None
    return out


def _sample_digest(sanitized: SanitizedSample) -> dict:
    return {
        "topic": sanitized.topic,
        "field_value_examples": _field_examples(sanitized),
        "sample_count": sanitized.sample_count,
    }


def build_llm_digest(
    sanitized: SanitizedSample, result: ClassificationResult, *,
    provider: str, model: str, first_seen_at: str, generated_at: str,
    summary_zh: str = "", why_low_confidence: str = "", prompt_version: str = "v1",
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "device_id": sanitized.device_id,
        "first_seen_at": first_seen_at,
        "generated_at": generated_at,
        "summary_source": "llm",
        "ai_provider": provider,
        "ai_model": model or None,
        "prompt_version": prompt_version,
        "ai_confidence": round(result.confidence, 2),
        "suggested_device_type": result.device_type,
        "suggested_signals": [
            {"signal_name": s.signal_name, "unit": s.unit, "datatype": s.datatype, "direction": s.direction}
            for s in result.suggested_signals
        ],
        "summary_zh": summary_zh or result.reasoning,
        "sample_digest": _sample_digest(sanitized),
        "why_low_confidence": why_low_confidence or result.reasoning,
    }


def build_fallback_digest(
    sanitized: SanitizedSample, default_device_type: str, *,
    first_seen_at: str, generated_at: str, prompt_version: str = "v1",
) -> dict:
    field_names = [f.field_name for f in sanitized.fields]
    summary_zh = (
        f"{sanitized.device_id} 於 {first_seen_at} 出現於 topic {sanitized.topic}，"
        f"含 {len(field_names)} 個欄位：{', '.join(field_names)}。{_FALLBACK_WHY}。"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "device_id": sanitized.device_id,
        "first_seen_at": first_seen_at,
        "generated_at": generated_at,
        "summary_source": "system_fallback",
        "ai_provider": None,
        "ai_model": None,
        "prompt_version": prompt_version,
        "ai_confidence": 0.0,
        "suggested_device_type": default_device_type,
        "suggested_signals": [
            {"signal_name": n, "unit": None, "datatype": None, "direction": None} for n in field_names
        ],
        "summary_zh": summary_zh,
        "sample_digest": _sample_digest(sanitized),
        "why_low_confidence": _FALLBACK_WHY,
    }