"""Auto-discovery orchestration (PRD-0003 §8.5 rules #5-#7 + §4 pipeline).

process_message ties together: topic parse (rules #1-#4) -> admission (dedupe /
rate-limit / status) -> create candidate (AI pool) -> classify (slice 3b) ->
persist under advisory lock. The MQTT transport lives in mqtt_subscriber.py.
"""
from __future__ import annotations

import contextlib
import json
import logging
from collections import deque
from collections.abc import Mapping
from datetime import datetime, timezone

from .budget_ledger import budget_reserve, budget_settle, current_period, reserve_estimate
from .repositories import device_repo
from .sanitizer import sanitize
from .topic_parser import MAX_PAYLOAD_BYTES, parse

_log = logging.getLogger("device_service.discovery")

DEDUPE_WINDOW = 60.0
RATE_LIMIT = 60
RATE_WINDOW = 60.0


class AdmissionGate:
    """Stateful deny rules #5 (dedupe) and #6 (rate-limit). Clock injected via `now`."""

    def __init__(self, *, dedupe_window: float = DEDUPE_WINDOW,
                 rate_limit: int = RATE_LIMIT, rate_window: float = RATE_WINDOW):
        self._dedupe_window = dedupe_window
        self._rate_limit = rate_limit
        self._rate_window = rate_window
        # one entry per topic that has created a candidate; bounded by the DB device
        # count (record_candidate only fires on a committed INSERT), so this grows at
        # the same rate as the devices table, not per-message. Explicit eviction is a
        # future concern if the fleet reaches hundreds of thousands.
        self._last_candidate_for: dict[str, float] = {}
        self._candidate_times: deque[float] = deque()

    def is_duplicate(self, source_topic: str, now: float) -> bool:
        t = self._last_candidate_for.get(source_topic)
        return t is not None and (now - t) < self._dedupe_window

    def allow_rate(self, now: float) -> bool:
        while self._candidate_times and now - self._candidate_times[0] >= self._rate_window:
            self._candidate_times.popleft()
        return len(self._candidate_times) < self._rate_limit

    def record_candidate(self, source_topic: str, now: float) -> None:
        self._last_candidate_for[source_topic] = now
        self._candidate_times.append(now)


def _coerce_ilp(v: str):
    if v.endswith("i") and v[:-1].lstrip("-").isdigit():
        return int(v[:-1])
    if v in ("t", "T", "true", "True"):
        return True
    if v in ("f", "F", "false", "False"):
        return False
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        return v[1:-1]
    try:
        return float(v)
    except ValueError:
        return v


def parse_fields(payload, payload_format: str) -> dict:
    text = payload.decode("utf-8", "replace") if isinstance(payload, (bytes, bytearray)) else str(payload)
    if payload_format == "json":
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {}
        return data if isinstance(data, Mapping) else {}
    parts = text.strip().split(" ")
    if len(parts) < 2:
        return {}
    out: dict = {}
    for kv in parts[1].split(","):
        if "=" in kv:
            k, v = kv.split("=", 1)
            out[k] = _coerce_ilp(v)
    return out


def _gateway_for(topic: str) -> str | None:
    if topic.startswith("ems/devices/"):
        return "ems-gateway"
    if topic.startswith("ems/factory/"):
        return "kc-gateway"
    if topic.startswith("factory/sensor/"):
        return "kc-ingest"
    return None


async def process_message(topic, payload, *, db, classifier, gate, settings, now) -> str:
    """Process one MQTT message. Returns a short status string (for metrics / tests)."""
    size = len(payload) if isinstance(payload, (bytes, bytearray)) else len(str(payload).encode())
    if size > MAX_PAYLOAD_BYTES:                                       # fast-fail before any decode
        return "reject:mqtt_oversized_payload_total"

    fmt_guess = "json" if topic.startswith("factory/sensor/") else "ilp"
    fields = parse_fields(payload, fmt_guess)

    pr = parse(topic, payload=fields, payload_size=size)
    if not pr.ok:
        return f"reject:{pr.metric}"
    if not fields:
        _log.warning("accepted topic %s parsed to zero fields (publisher format mismatch?)", topic)

    if gate.is_duplicate(topic, now):                                  # rule #5
        async with db.ai_pool.acquire() as conn:
            await device_repo.touch_last_seen(conn, pr.device_id)
        return "dedupe"

    async with db.ai_pool.acquire() as conn:
        existing = await device_repo.get(conn, pr.device_id)
    if existing is not None:
        async with db.ai_pool.acquire() as conn:
            await device_repo.touch_last_seen(conn, pr.device_id)
        return "existing"

    if not gate.allow_rate(now):                                       # rule #6
        return "rate_limited"

    async with db.ai_tx(lock=pr.device_id) as conn:                    # rule #7: candidate
        if await device_repo.get(conn, pr.device_id) is not None:
            return "existing"
        created_at = await device_repo.create_candidate(
            conn, pr.device_id, pr.device_type, topic, _gateway_for(topic))
    gate.record_candidate(topic, now)

    first_seen = created_at.isoformat() if created_at is not None else datetime.now(timezone.utc).isoformat()
    sanitized = sanitize(pr.device_id, topic, pr.payload_format, [fields])
    period_start, period_end = current_period()
    is_mock = settings.llm_provider == "mock"
    est = reserve_estimate(settings.llm_model)
    if is_mock:
        budget_ok = True                                               # mock is free
    else:
        # FR-329 hard cap: reserve the worst-case cost up front under the budget advisory
        # lock; a near-budget or concurrent call that would cross is denied here (ADR-014).
        async with db.ai_tx() as conn:
            budget_ok = await budget_reserve(
                conn, settings.llm_provider, period_start, period_end, est, settings.llm_monthly_budget_usd)
    settled = False
    try:
        outcome = await classifier.classify(
            sanitized, budget_ok=budget_ok, default_device_type=pr.device_type,
            first_seen_at=first_seen, generated_at=datetime.now(timezone.utc).isoformat(),
        )
        async with db.ai_tx(lock=pr.device_id) as conn:               # §8.6.8 device advisory lock
            await device_repo.apply_outcome(conn, pr.device_id, outcome)
        if not is_mock and budget_ok:
            # settle the reservation to actual cost (refund the over-reservation; a fallback
            # with no real call refunds the full reservation)
            usage = (outcome.result.raw_response or {}).get("usage") or {}
            if outcome.summary_source == "llm":
                tin, tout = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
            else:
                tin = tout = 0
            async with db.ai_tx() as conn:
                await budget_settle(conn, settings.llm_provider, period_start, est, settings.llm_model, tin, tout)
            settled = True
        return f"created:{outcome.new_status}"
    finally:
        # never leak a reservation: if classify/apply/settle raised after a successful
        # reservation, refund the full reservation (no usage accounted) so a transient
        # crash does not permanently consume the budget.
        if not is_mock and budget_ok and not settled:
            with contextlib.suppress(Exception):
                async with db.ai_tx() as conn:
                    await budget_settle(conn, settings.llm_provider, period_start, est, settings.llm_model, 0, 0)