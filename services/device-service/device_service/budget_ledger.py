"""LLM budget gate + ledger I/O (PRD-0003 §10, ADR-014, FR-329/319).

evaluate_budget: pure pre-call decision (80% warn, 100% fail-closed).
record_usage: writes token/cost back to llm_budget_ledger after a real LLM call so
the gate actually trips for real providers (Phase 1.4 completion of FR-329).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

_log = logging.getLogger("device_service.budget")

WARN_RATIO = 0.8

# Rough USD per 1M tokens (input, output) — dev estimate; update to live pricing.
# Unknown model -> (0, 0): tokens are still recorded, cost contribution is 0.
_PRICING = {
    "claude-haiku-4-5": (0.80, 4.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "gpt-4o-mini": (0.15, 0.60),
}


@dataclass(frozen=True)
class BudgetDecision:
    allow: bool
    alert: str | None  # None | 'warn_80' | 'blocked_100'


def evaluate_budget(spent_usd: float, budget_usd: float, *, warn_ratio: float = WARN_RATIO) -> BudgetDecision:
    if budget_usd <= 0:
        return BudgetDecision(allow=True, alert=None)
    ratio = spent_usd / budget_usd
    if ratio >= 1.0:
        return BudgetDecision(allow=False, alert="blocked_100")
    if ratio >= warn_ratio:
        return BudgetDecision(allow=True, alert="warn_80")
    return BudgetDecision(allow=True, alert=None)


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    p_in, p_out = _PRICING.get(model, (0.0, 0.0))
    return (tokens_in / 1_000_000) * p_in + (tokens_out / 1_000_000) * p_out


def current_period(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Calendar-month [start, end) in UTC for ledger keying."""
    now = now or datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    return start, end


async def get_period_budget(conn, provider: str, period_start: datetime, monthly_budget_usd: float) -> tuple[float, float]:
    """Return (spent_usd, budget_usd) for the (period_start, provider) ledger row.
    No row yet -> (0, monthly_budget_usd)."""
    row = await conn.fetchrow(
        "SELECT cost_usd, budget_usd FROM public.llm_budget_ledger "
        "WHERE provider=$1 AND period_start=$2",
        provider, period_start,
    )
    if row is None:
        return 0.0, monthly_budget_usd
    return float(row["cost_usd"]), float(row["budget_usd"])


async def record_usage(
    conn, provider: str, period_start: datetime, period_end: datetime, model: str,
    tokens_in: int, tokens_out: int, budget_usd: float,
) -> float:
    """Accumulate token/cost usage into the (period_start, provider) ledger row. Returns the cost added."""
    cost = estimate_cost(model, tokens_in, tokens_out)
    if cost == 0.0 and (tokens_in or tokens_out):
        # point 4: do not silently fail the USD budget gate for an unpriced model
        _log.warning(
            "model %r not in pricing table: %d/%d tokens recorded but cost_usd unchanged; "
            "the USD budget gate will NOT trip for provider %r until pricing is configured",
            model, tokens_in, tokens_out, provider,
        )
    await conn.execute(
        """INSERT INTO public.llm_budget_ledger
               (period_start, period_end, provider, tokens_in, tokens_out, cost_usd, budget_usd, active, updated_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, TRUE, now())
           ON CONFLICT (period_start, provider) DO UPDATE SET
               tokens_in = public.llm_budget_ledger.tokens_in + EXCLUDED.tokens_in,
               tokens_out = public.llm_budget_ledger.tokens_out + EXCLUDED.tokens_out,
               cost_usd = public.llm_budget_ledger.cost_usd + EXCLUDED.cost_usd,
               updated_at = now()""",
        period_start, period_end, provider, tokens_in, tokens_out, cost, budget_usd,
    )
    return cost

# --- FR-329 hard cap: pre-call reservation + budget-namespace advisory lock (ADR-014) ---
# Reserve a generous per-call upper bound BEFORE the LLM call (so a near-budget single
# call cannot cross), then settle to the actual cost AFTER. The advisory lock serialises
# reserve/settle per (provider, period) so concurrent workers cannot both over-reserve.
RESERVE_INPUT_TOKENS = 4000
RESERVE_OUTPUT_TOKENS = 1024
_BUDGET_LOCK = "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))"


def _budget_lock_key(provider: str, period_start: datetime) -> str:
    return f"budget:{provider}:{period_start.isoformat()}"


def reserve_estimate(model: str) -> float:
    """Worst-case cost of one classification call (used as the pre-call reservation)."""
    return estimate_cost(model, RESERVE_INPUT_TOKENS, RESERVE_OUTPUT_TOKENS)


async def budget_reserve(
    conn, provider: str, period_start: datetime, period_end: datetime,
    est_cost: float, budget_usd: float,
) -> bool:
    """Under the budget advisory lock: reserve est_cost unless it would exceed budget.
    Returns True if reserved (LLM call may proceed), False if denied (-> fallback).
    Must run inside a transaction (e.g. Database.ai_tx)."""
    await conn.execute(_BUDGET_LOCK, _budget_lock_key(provider, period_start))
    row = await conn.fetchrow(
        "SELECT cost_usd FROM public.llm_budget_ledger WHERE provider=$1 AND period_start=$2",
        provider, period_start,
    )
    current = float(row["cost_usd"]) if row is not None else 0.0
    if budget_usd > 0 and current + est_cost > budget_usd:
        return False
    await conn.execute(
        """INSERT INTO public.llm_budget_ledger
               (period_start, period_end, provider, cost_usd, budget_usd, active, updated_at)
           VALUES ($1, $2, $3, $4, $5, TRUE, now())
           ON CONFLICT (period_start, provider) DO UPDATE SET
               cost_usd = public.llm_budget_ledger.cost_usd + EXCLUDED.cost_usd, updated_at = now()""",
        period_start, period_end, provider, est_cost, budget_usd,
    )
    return True


async def budget_settle(
    conn, provider: str, period_start: datetime, reserved_est: float, model: str,
    tokens_in: int, tokens_out: int,
) -> float:
    """Under the budget advisory lock: replace the reservation with the actual cost
    (delta = actual - reserved_est, usually a refund) and add token counts.
    For a fallback (no real call) pass tokens 0 -> the full reservation is refunded.
    Returns the actual cost. Must run inside a transaction."""
    actual = estimate_cost(model, tokens_in, tokens_out)
    if actual == 0.0 and (tokens_in or tokens_out):
        _log.warning(
            "model %r not in pricing table: %d/%d tokens settled at cost 0 for provider %r; "
            "USD budget gate cannot enforce until pricing is configured",
            model, tokens_in, tokens_out, provider,
        )
    await conn.execute(_BUDGET_LOCK, _budget_lock_key(provider, period_start))
    await conn.execute(
        """UPDATE public.llm_budget_ledger SET
               cost_usd = GREATEST(0, cost_usd + $3),
               tokens_in = tokens_in + $4, tokens_out = tokens_out + $5, updated_at = now()
           WHERE provider=$1 AND period_start=$2""",
        provider, period_start, actual - reserved_est, tokens_in, tokens_out,
    )
    return actual