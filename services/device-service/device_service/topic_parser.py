"""MQTT topic parser — Parser Matrix v3 (PRD-0003 §8.5, ADR-013).

Pure function: given (topic, payload, payload_size) decide whether a message is
admissible and resolve its device_id / default device_type. Deny-by-default —
only Matrix rules #1-#4 are accepted; everything else is rejected with a metric.

Stateful admission rules (#5 dedupe, #6 rate-limit, #7 status) live in the MQTT
subscriber, not here.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
MAX_PAYLOAD_BYTES = 16 * 1024
MAX_FIELDS = 64

# PRD-0002 legacy hard-coded mapping (already backfilled as confirmed); keyed on sensor_id.
LEGACY_SENSOR_MAP = {"temp_01": "sensor-001"}


@dataclass(frozen=True)
class ParseResult:
    ok: bool
    device_id: str | None = None
    device_type: str | None = None      # default device_type for a new candidate
    payload_format: str | None = None   # 'ilp' | 'json'
    matched_rule: int | None = None      # 1-4
    reject_reason: str | None = None
    metric: str | None = None            # metric to increment on reject


def _reject(reason: str, metric: str) -> ParseResult:
    return ParseResult(ok=False, reject_reason=reason, metric=metric)


def _normalize_sensor(sensor_id: str) -> str:
    return sensor_id.lower().replace("_", "-")


def _resolve_factory_sensor(sensor_id: str, payload: Mapping | None) -> tuple[str | None, str | None]:
    """Return (device_id, reject_metric). Order: legacy -> payload device_id (4a) -> normalize (4b)."""
    if sensor_id in LEGACY_SENSOR_MAP:
        return LEGACY_SENSOR_MAP[sensor_id], None
    if payload is not None:
        candidate = payload.get("device_id")
        if isinstance(candidate, str) and ID_RE.match(candidate):
            return candidate, None  # rule #4a (valid payload device_id wins, ignore 4b)
    # rule #4b: sensor_id (raw) must pass the id regex before normalisation
    if not ID_RE.match(sensor_id):
        return None, "mqtt_invalid_id_total"
    return f"sensor-{_normalize_sensor(sensor_id)}", None


def parse(topic: str, payload: Mapping | None = None, payload_size: int | None = None) -> ParseResult:
    segments = topic.split("/")

    # ---- topic shape (rules #1-#4) ----
    if len(segments) == 4 and segments[0] == "ems" and segments[3] == "measurements":
        domain, device_id = segments[1], segments[2]
        device_type = "electricity" if domain == "devices" else "unknown"
        rule = 1 if domain == "devices" else (2 if domain == "factory" else 3)
        payload_format = "ilp"
    elif len(segments) == 3 and segments[0] == "factory" and segments[1] == "sensor":
        device_id, bad = _resolve_factory_sensor(segments[2], payload)
        if bad:
            return _reject("invalid_id", bad)
        device_type, rule, payload_format = "unknown", 4, "json"
    else:
        return _reject("unmatched_topic", "unmatched_topic_total")

    # ---- deny rule #2: id regex ----
    if not device_id or not ID_RE.match(device_id):
        return _reject("invalid_id", "mqtt_invalid_id_total")

    # ---- deny rule #3: payload size ----
    if payload_size is not None and payload_size > MAX_PAYLOAD_BYTES:
        return _reject("oversized_payload", "mqtt_oversized_payload_total")

    # ---- deny rule #4: field count ----
    if payload is not None and len(payload) > MAX_FIELDS:
        return _reject("oversized_fields", "mqtt_oversized_fields_total")

    return ParseResult(
        ok=True, device_id=device_id, device_type=device_type,
        payload_format=payload_format, matched_rule=rule,
    )