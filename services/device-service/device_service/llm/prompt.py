"""Prompt rendering for L1 classifiers (ADR-009 / §8.6.5 — JSON, never raw payload)."""
from __future__ import annotations

import json

from .types import SanitizedSample

PROMPT_VERSION = "v1"  # bump when SYSTEM_PROMPT / render_sample change; stamped into provenance
DEVICE_TYPES = ("electricity", "temperature", "pressure", "motor", "valve", "hvac", "unknown")

SYSTEM_PROMPT = (
    "You classify Energy Management System (EMS) devices from de-identified signal "
    "summaries. You receive ONLY numeric/bool field statistics — never raw payloads. "
    "Choose device_type from this closed set: " + ", ".join(DEVICE_TYPES) + ". "
    "Suggest signals (name/unit/datatype/direction) and a confidence in [0,1]. "
    "If human_corrections are present, treat them as authoritative prior feedback. "
    "Respond with the classification only; do not echo raw input."
)


def render_sample(sanitized: SanitizedSample) -> str:
    """Render a SanitizedSample as a compact JSON object (no raw values)."""
    payload = {
        "device_id": sanitized.device_id,
        "topic": sanitized.topic,
        "payload_format": sanitized.payload_format,
        "sample_count": sanitized.sample_count,
        "fields": [
            {
                "field_name": f.field_name,
                "datatype": f.datatype,
                "value_min": f.value_min,
                "value_max": f.value_max,
                "sample_count": f.sample_count,
                "distinct_count": f.distinct_count,
                "bool_true_ratio": f.bool_true_ratio,
            }
            for f in sanitized.fields
        ],
        "human_corrections": [
            {
                "verdict": c.verdict,
                "corrected_device_type": c.corrected_device_type,
                "explanation": c.explanation_truncated,
                "created_at": c.created_at_iso,
            }
            for c in sanitized.human_corrections
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)