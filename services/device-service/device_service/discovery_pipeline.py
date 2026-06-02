"""Classification pipeline stages, extracted from discovery.process_message so each
concern is small and independently testable (PRD-0003 §4 / §8.6 / §8.7 / §10):

  - load_correction_context : FR-331 retrieval + sanitize + §8.6.5a 32KB prompt cap
  - persist_outcome         : the in-transaction writes (status/digest + applied_count + FR-339 audit)
  - classify_under_budget   : FR-329 budget reserve -> classify -> persist -> settle (leak-safe)

discovery.process_message stays as the admission gate + orchestrator. This module imports
only repos / sanitizer / budget / correction_context — never discovery — so there is no cycle.
"""
from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from .budget_ledger import (
    RESERVE_INPUT_TOKENS, RESERVE_OUTPUT_TOKENS,
    budget_reserve, budget_settle, current_period, reserve_estimate, resolve_pricing,
)
from .classifier import Outcome
from .correction_context import build_context, cap_to_prompt_size, device_type_family, topic_prefix
from .llm.types import SanitizedSample
from .repositories import audit_repo, correction_repo, device_repo
from .sanitizer import sanitize

_log = logging.getLogger("device_service.discovery")


@dataclass(frozen=True)
class CorrectionContextLoad:
    sanitized: SanitizedSample
    applied_ids: tuple[int, ...]            # ids of corrections actually injected (cap-kept prefix)
    latest_correction_device_type: str | None   # FR-332 conflict source


async def load_correction_context(
    db, *, device_id: str, topic: str, payload_format: str, fields: dict,
    device_type: str | None, gateway_id: str | None,
) -> CorrectionContextLoad:
    """FR-331 / §8.6.4: pull relevant ACTIVE corrections (AI role has SELECT-only on
    device_corrections, migration 012) + the latest corrected type for FR-332, sanitize the
    sample, and apply the §8.6.5a 32KB prompt cap (LRU-dropping the oldest corrections)."""
    async with db.ai_pool.acquire() as conn:
        corr_rows = await correction_repo.retrieve_relevant(
            conn, device_id=device_id, gateway_id=gateway_id,
            device_type_family=device_type_family(device_type), topic_prefix=topic_prefix(topic))
        latest = await correction_repo.latest_corrected_device_type(
            conn, device_id=device_id, gateway_id=gateway_id)
    base_sample = sanitize(device_id, topic, payload_format, [fields])
    kept_ctx, truncated = cap_to_prompt_size(base_sample, [build_context(r) for r in corr_rows])
    if truncated:
        _log.warning("correction_truncated device=%s kept=%d of=%d (32KB prompt cap)",
                     device_id, len(kept_ctx), len(corr_rows))
    sanitized = replace(base_sample, human_corrections=tuple(kept_ctx))
    # kept is a prefix of corr_rows (oldest dropped from the tail) -> map back by position
    applied_ids = tuple(corr_rows[i]["id"] for i in range(len(kept_ctx)))
    return CorrectionContextLoad(sanitized, applied_ids, latest)


async def persist_outcome(conn, *, device_id: str, outcome: Outcome, applied_ids: tuple[int, ...]) -> None:
    """In-transaction writes for one classification outcome (caller holds the §8.6.8 device
    advisory lock). All atomic: status/digest, applied_count bump, and the FR-339 guardrail
    audit row cannot diverge from each other."""
    await device_repo.apply_outcome(conn, device_id, outcome)
    # §7.3a applied_count bump only when the LLM actually ran — a budget/guardrail fallback
    # never reached the prompt, so nothing was injected.
    if outcome.summary_source == "llm" and applied_ids:
        await correction_repo.mark_applied(conn, applied_ids)
    # FR-339 / §8.7.5: persist every L2 guardrail BLOCK (AI role has INSERT-only on
    # device_audit_log; raw prompt is never stored, only its hash). Consecutive-BLOCK alert
    # is a Grafana window query over these rows.
    gb = outcome.guardrail_block
    if gb is not None:
        await audit_repo.record(
            conn, event_type="guardrail_block", actor="ai", device_id=device_id,
            outcome="blocked", detail={
                "phase": gb.phase, "threat_category": gb.threat_category,
                "reasoning": gb.reasoning, "l1_input_hash": gb.l1_input_hash,
                "l1_output_hash": gb.l1_output_hash})


async def classify_under_budget(
    db, classifier, settings, *, sanitized: SanitizedSample, default_device_type: str | None,
    latest_correction_device_type: str | None, applied_ids: tuple[int, ...],
    device_id: str, first_seen: str,
) -> Outcome:
    """FR-329 hard cap: reserve worst-case cost up front (under the budget advisory lock),
    classify, persist the outcome (§8.6.8 device lock), then settle the reservation to actual
    cost. The reservation NEVER leaks: any exception after a successful reserve refunds the
    full reservation in the finally block."""
    period_start, period_end = current_period()
    is_mock = settings.llm_provider == "mock"
    pricing = resolve_pricing(getattr(settings, "llm_pricing_json", ""))
    est = reserve_estimate(
        settings.llm_model,
        getattr(settings, "llm_reserve_input_tokens", RESERVE_INPUT_TOKENS),
        getattr(settings, "llm_max_output_tokens", RESERVE_OUTPUT_TOKENS),
        pricing,
    )
    if is_mock:
        budget_ok = True                                               # mock is free
    else:
        async with db.ai_tx() as conn:                                 # ADR-014 budget-namespace lock
            budget_ok = await budget_reserve(
                conn, settings.llm_provider, period_start, period_end, est, settings.llm_monthly_budget_usd)
    settled = False
    try:
        outcome = await classifier.classify(
            sanitized, budget_ok=budget_ok, default_device_type=default_device_type,
            latest_correction_device_type=latest_correction_device_type,
            first_seen_at=first_seen, generated_at=datetime.now(timezone.utc).isoformat(),
        )
        async with db.ai_tx(lock=device_id) as conn:                   # §8.6.8 device advisory lock
            await persist_outcome(conn, device_id=device_id, outcome=outcome, applied_ids=applied_ids)
        if not is_mock and budget_ok:
            usage = (outcome.result.raw_response or {}).get("usage") or {}
            if outcome.summary_source == "llm":
                tin, tout = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
            else:
                tin = tout = 0
            async with db.ai_tx() as conn:
                await budget_settle(conn, settings.llm_provider, period_start, est, settings.llm_model, tin, tout, pricing)
            settled = True
        return outcome
    finally:
        if not is_mock and budget_ok and not settled:
            with contextlib.suppress(Exception):
                async with db.ai_tx() as conn:
                    await budget_settle(conn, settings.llm_provider, period_start, est, settings.llm_model, 0, 0, pricing)
