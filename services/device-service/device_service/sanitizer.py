"""Sample sanitiser (FR-328, ADR-009).

Builds a SanitizedSample from raw observations. Rules:
  1. field whitelist — keep numeric / bool only; strings are stripped (only a
     distinct_count is recorded, never the value).
  2. PII blacklist field names are dropped entirely.
  3. field count cap (<= 64), sample count cap (<= 20).
  4. numeric -> min/max/count only (never individual readings).
  5. bool -> true ratio.
Invariant (property-tested): no raw string VALUE appears in the output.
"""
from __future__ import annotations

import re
from numbers import Real
from typing import Iterable, Mapping, Sequence

from .llm.types import CorrectionContext, FieldSummary, SanitizedSample

MAX_FIELDS = 64
MAX_SAMPLES = 20
PII_FIELD_RE = re.compile(
    r"(name|user|email|phone|address|location|gps|lat|lng|owner)", re.IGNORECASE
)


def _is_bool(v: object) -> bool:
    return isinstance(v, bool)


def _is_number(v: object) -> bool:
    return isinstance(v, Real) and not isinstance(v, bool)


def _ordered_field_names(samples: Sequence[Mapping]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for s in samples:
        for k in s.keys():
            if k not in seen:
                seen.add(k)
                names.append(k)
    return names


def sanitize(
    device_id: str,
    topic: str,
    payload_format: str,
    raw_samples: Iterable[Mapping],
    corrections: Iterable[CorrectionContext] = (),
) -> SanitizedSample:
    samples = list(raw_samples)[-MAX_SAMPLES:]
    summaries: list[FieldSummary] = []

    for name in _ordered_field_names(samples):
        if len(summaries) >= MAX_FIELDS:
            break
        if PII_FIELD_RE.search(name):
            continue  # drop PII field entirely (not even a count)
        values = [s[name] for s in samples if name in s and s[name] is not None]
        if not values:
            continue
        if all(_is_bool(v) for v in values):
            ratio = sum(1 for v in values if v) / len(values)
            summaries.append(
                FieldSummary(name, "bool", sample_count=len(values), bool_true_ratio=round(ratio, 4))
            )
        elif all(_is_number(v) for v in values):
            dt = "int" if all(isinstance(v, int) for v in values) else "float"
            summaries.append(
                FieldSummary(
                    name, dt, value_min=float(min(values)),
                    value_max=float(max(values)), sample_count=len(values),
                )
            )
        else:
            # string / mixed -> strip values, record cardinality only
            distinct = len({str(v) for v in values})
            summaries.append(
                FieldSummary(name, "string", sample_count=len(values), distinct_count=distinct)
            )

    return SanitizedSample(
        schema_version="v1",
        device_id=device_id,
        topic=topic,
        payload_format=payload_format,
        sample_count=len(samples),
        fields=tuple(summaries),
        human_corrections=tuple(corrections),
    )