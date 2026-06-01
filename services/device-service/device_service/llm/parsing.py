"""Parse a provider's JSON/tool payload into a ClassificationResult (ADR-009).

Provider-agnostic. Security checks (FR-333) live in output_validator, not here;
this only does defensive structural coercion.
"""
from __future__ import annotations

from collections.abc import Mapping

from .types import ClassificationResult, SignalSuggestion


def _to_signal(d: Mapping) -> SignalSuggestion:
    return SignalSuggestion(
        signal_name=str(d.get("signal_name") or ""),
        unit=str(d.get("unit") or ""),
        datatype=str(d.get("datatype") or ""),
        direction=str(d.get("direction") or "read"),
    )


def _to_float(v: object, default: float = 0.0) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def result_from_dict(data: Mapping, raw_response: Mapping) -> ClassificationResult:
    signals_raw = data.get("suggested_signals") or []
    if not isinstance(signals_raw, (list, tuple)):
        signals_raw = []
    signals = tuple(_to_signal(s) for s in signals_raw if isinstance(s, Mapping))
    return ClassificationResult(
        device_type=str(data.get("device_type") or "unknown"),
        suggested_signals=signals,
        confidence=_to_float(data.get("confidence", 0.0)),
        reasoning=str(data.get("reasoning", "")),
        raw_response=dict(raw_response),
    )