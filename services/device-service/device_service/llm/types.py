"""Immutable data structures for the LLM provider contract (PRD-0003 §8.3, ADR-009).

SanitizedSample is the ONLY structure sent to an external LLM — no raw payload,
no free-text values, no PII. All structures are frozen (immutable by design).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FieldSummary:
    field_name: str
    datatype: str  # 'float' | 'int' | 'bool' | 'string' | 'enum'
    value_min: float | None = None
    value_max: float | None = None
    sample_count: int = 0
    distinct_count: int | None = None       # for bool / enum / string cardinality
    bool_true_ratio: float | None = None     # for bool


@dataclass(frozen=True)
class CorrectionContext:
    """De-sanitised form of a human correction (§8.6 / FR-331)."""
    verdict: str
    corrected_device_type: str | None
    explanation_truncated: str   # truncated, blacklist-stripped
    created_at_iso: str


@dataclass(frozen=True)
class SanitizedSample:
    """The single structure handed to an external LLM."""
    schema_version: str          # 'v1'
    device_id: str
    topic: str
    payload_format: str          # 'ilp' | 'json'
    sample_count: int            # raw observations summarised (<= cap)
    fields: tuple[FieldSummary, ...] = ()
    human_corrections: tuple[CorrectionContext, ...] = ()


@dataclass(frozen=True)
class SignalSuggestion:
    signal_name: str
    unit: str
    datatype: str
    direction: str               # 'read' | 'write' | 'read_write'


@dataclass(frozen=True)
class ClassificationResult:
    device_type: str
    suggested_signals: tuple[SignalSuggestion, ...]
    confidence: float            # 0.0 - 1.0
    reasoning: str
    raw_response: dict = field(default_factory=dict)  # provider raw; stored internally only