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
from .llm.types import CorrectionContext, SanitizedSample
from .repositories import audit_repo, correction_repo, device_repo, measurements_repo
from .sanitizer import sanitize

_log = logging.getLogger("device_service.discovery")

# FR-340: the L2 guardrail is metered on its OWN llm_budget_ledger row under this fixed provider
# key, separate from the L1 provider's row, so the two budgets are tracked and capped independently.
GUARDRAIL_PROVIDER_KEY = "guardrail"


@dataclass(frozen=True)
class CorrectionContextLoad:
    sanitized: SanitizedSample
    applied_ids: tuple[int, ...]            # ids of corrections actually injected (cap-kept prefix)
    latest_correction_device_type: str | None   # FR-332 conflict source


async def load_correction_context(
    db, *, device_id: str, topic: str, payload_format: str, samples: list[dict],
    device_type: str | None, gateway_id: str | None,
    prepend_context: CorrectionContext | None = None,
) -> CorrectionContextLoad:
    """FR-331 / §8.6.4: pull relevant ACTIVE corrections (AI role has SELECT-only on
    device_corrections, migration 012) + the latest corrected type for FR-332, sanitize the
    sample(s), and apply the §8.6.5a 32KB prompt cap (LRU-dropping the oldest corrections).
    `samples` is the raw observation list (one dict per message / measurement row).

    `prepend_context` (e.g. an MCP classify_with_context hint) is a NON-persisted context placed
    FIRST so it is counted IN the 32KB cap (must-keep — the cap drops from the tail, so an older
    persisted correction is dropped before the hint). It is never counted in applied_ids."""
    async with db.ai_pool.acquire() as conn:
        corr_rows = await correction_repo.retrieve_relevant(
            conn, device_id=device_id, gateway_id=gateway_id,
            device_type_family=device_type_family(device_type), topic_prefix=topic_prefix(topic))
        latest = await correction_repo.latest_corrected_device_type(
            conn, device_id=device_id, gateway_id=gateway_id)
    base_sample = sanitize(device_id, topic, payload_format, samples)
    contexts = [build_context(r) for r in corr_rows]
    offset = 0
    if prepend_context is not None:
        contexts = [prepend_context, *contexts]
        offset = 1
    kept_ctx, truncated = cap_to_prompt_size(base_sample, contexts)
    if truncated:
        _log.warning("correction_truncated device=%s kept=%d of=%d (32KB prompt cap)",
                     device_id, len(kept_ctx), len(contexts))
    sanitized = replace(base_sample, human_corrections=tuple(kept_ctx))
    # kept is a prefix of `contexts` (oldest dropped from the tail). A prepended context is index 0
    # and has no DB row -> exclude it from applied_ids; the remaining kept map to corr_rows.
    retrieved_kept = max(0, len(kept_ctx) - offset)
    applied_ids = tuple(corr_rows[i]["id"] for i in range(retrieved_kept))
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
    device_id: str, first_seen: str, force: bool = False,
) -> Outcome:
    """FR-329 hard cap: reserve worst-case cost up front (under the budget advisory lock),
    classify, persist the outcome (§8.6.8 device lock), then settle the reservation to actual
    cost. Any exception during classify/persist/settle refunds the full reservation in the finally
    block. (Known narrow gap, pre-existing: a DB error in the guardrail reserve itself — after the
    L1 reserve committed but before the try — can leak the L1 reservation; reserves run before the
    try. Tracked as hardening debt; a single combined reserve tx would close it.)

    FR-340: the L2 guardrail runs up to 2 model calls (pre + post) and is metered on a SEPARATE
    provider='guardrail' ledger row with its own monthly cap. If the guardrail budget is
    exhausted, classification stops entirely (L1 too) and falls back. A cache hit (from_cache)
    spends no tokens for either layer, so both reservations are fully refunded."""
    period_start, period_end = current_period()
    pricing = resolve_pricing(getattr(settings, "llm_pricing_json", ""))
    is_mock = settings.llm_provider == "mock"
    est = reserve_estimate(
        settings.llm_model,
        getattr(settings, "llm_reserve_input_tokens", RESERVE_INPUT_TOKENS),
        getattr(settings, "llm_max_output_tokens", RESERVE_OUTPUT_TOKENS),
        pricing,
    )
    # FR-340 guardrail track: worst case is 2 model calls (pre + post). Defensive getattr keeps a
    # minimal settings object (no guardrail_* fields) safely on the free mock path.
    g_is_mock = getattr(settings, "guardrail_provider", "mock") == "mock"
    g_model = (getattr(settings, "guardrail_model", "")
               or getattr(settings, "guardrail_default_model_openai", "gpt-4o-mini"))
    g_est = 2 * reserve_estimate(
        g_model,
        getattr(settings, "guardrail_reserve_input_tokens", RESERVE_INPUT_TOKENS),
        getattr(settings, "guardrail_max_output_tokens", RESERVE_OUTPUT_TOKENS), pricing,
    )

    if is_mock:
        budget_ok = True                                               # mock is free
    else:
        async with db.ai_tx() as conn:                                 # ADR-014 budget-namespace lock
            budget_ok = await budget_reserve(
                conn, settings.llm_provider, period_start, period_end, est, settings.llm_monthly_budget_usd)
    if g_is_mock:
        guardrail_ok = True                                            # mock guardrail is free
    else:
        async with db.ai_tx() as conn:
            guardrail_ok = await budget_reserve(
                conn, GUARDRAIL_PROVIDER_KEY, period_start, period_end, g_est,
                getattr(settings, "guardrail_monthly_budget_usd", 0.0))

    settled = g_settled = False
    try:
        outcome = await classifier.classify(
            sanitized, budget_ok=budget_ok, guardrail_ok=guardrail_ok,
            default_device_type=default_device_type,
            latest_correction_device_type=latest_correction_device_type,
            first_seen_at=first_seen, generated_at=datetime.now(timezone.utc).isoformat(), force=force,
        )
        async with db.ai_tx(lock=device_id) as conn:                   # §8.6.8 device advisory lock
            await persist_outcome(conn, device_id=device_id, outcome=outcome, applied_ids=applied_ids)
        # settle L1: a cache hit spent no tokens this call -> full refund (tin/tout = 0).
        if not is_mock and budget_ok:
            usage = (outcome.result.raw_response or {}).get("usage") or {}
            if outcome.summary_source == "llm" and not outcome.from_cache:
                tin, tout = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
            else:
                tin = tout = 0
            async with db.ai_tx() as conn:
                await budget_settle(conn, settings.llm_provider, period_start, est, settings.llm_model, tin, tout, pricing)
            settled = True
        # settle L2 guardrail (FR-340): actual pre+post usage, 0 on a cache hit (no L2 call ran).
        if not g_is_mock and guardrail_ok:
            g_usage = (outcome.guardrail_usage or {}) if not outcome.from_cache else {}
            g_tin, g_tout = int(g_usage.get("input_tokens", 0)), int(g_usage.get("output_tokens", 0))
            async with db.ai_tx() as conn:
                await budget_settle(conn, GUARDRAIL_PROVIDER_KEY, period_start, g_est, g_model, g_tin, g_tout, pricing)
            g_settled = True
        return outcome
    finally:
        if not is_mock and budget_ok and not settled:
            with contextlib.suppress(Exception):
                async with db.ai_tx() as conn:
                    await budget_settle(conn, settings.llm_provider, period_start, est, settings.llm_model, 0, 0, pricing)
        if not g_is_mock and guardrail_ok and not g_settled:
            with contextlib.suppress(Exception):
                async with db.ai_tx() as conn:
                    await budget_settle(conn, GUARDRAIL_PROVIDER_KEY, period_start, g_est, g_model, 0, 0, pricing)


async def reclassify_device(
    db, classifier, settings, *, device_id: str, force: bool = True, hint: str | None = None,
) -> Outcome | None:
    """On-demand reclassification of an EXISTING device (PRD §234/§761, FR-330 rerun /
    MCP classify_with_context primitive). Reads the device's recent <=20 raw measurement
    samples via the OPS pool (the AI role has no measurements SELECT), then runs the same
    correction-context + budget-gated classify path as live discovery. force=True forces a
    fresh LLM call (FR-316 cache miss). `hint` (MCP classify_with_context) is injected as a
    synthetic most-recent correction context to steer the LLM — caller MUST pre-validate it
    (§7.3a) since it enters the prompt. Returns the Outcome, or None if the device is unknown,
    not a candidate, has no known sample source, or has no recent samples."""
    async with db.ops_pool.acquire() as conn:   # OPS: measurements SELECT + devices SELECT
        row = await conn.fetchrow(
            "SELECT status, gateway_id, device_type, created_at, metadata->>'source_topic' AS source_topic "
            "FROM public.devices WHERE device_id = $1", device_id)
        if row is None:
            return None
        # apply_outcome only mutates a non-frozen candidate, so classifying a confirmed/retired
        # device would burn an LLM call for a guaranteed persistence no-op. Skip it here (no
        # budget spend) and tell the operator to demote first (FR-330 demote_to_candidate / §900).
        if row["status"] != "candidate":
            _log.info("reclassify skipped device=%s: status=%r is not 'candidate' "
                      "(demote_to_candidate=true to re-open before rerun)", device_id, row["status"])
            return None
        table = measurements_repo.table_for_gateway(row["gateway_id"])
        if table is None:
            _log.info("reclassify skipped device=%s: unknown gateway %r (no sample source)",
                      device_id, row["gateway_id"])
            return None
        samples = await measurements_repo.recent_samples(conn, table=table, device_id=device_id)
    if not samples:
        _log.info("reclassify skipped device=%s: no recent samples in %s", device_id, table)
        return None
    # payload_format is informational for the prompt; best-effort by table.
    payload_format = "ilp" if table == "electricity_measurements" else "json"
    first_seen = row["created_at"].isoformat() if row["created_at"] is not None else ""
    # the (pre-validated) hint is a non-persisted, must-keep MOST-RECENT context -> pass it into
    # load_correction_context so it is INSIDE the 32KB cap (older persisted corrections drop first,
    # never the hint), and it stays out of applied_ids.
    hint_ctx = (CorrectionContext("hint", None, hint, datetime.now(timezone.utc).isoformat())
                if hint else None)
    ctx = await load_correction_context(
        db, device_id=device_id, topic=row["source_topic"] or "", payload_format=payload_format,
        samples=samples, device_type=row["device_type"], gateway_id=row["gateway_id"],
        prepend_context=hint_ctx)
    return await classify_under_budget(
        db, classifier, settings, sanitized=ctx.sanitized, default_device_type=row["device_type"],
        latest_correction_device_type=ctx.latest_correction_device_type,
        applied_ids=ctx.applied_ids, device_id=device_id, first_seen=first_seen, force=force)
