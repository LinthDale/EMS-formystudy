"""LLM budget gate (PRD-0003 §10, ADR-014, FR-329/319).

Pure decision: given current period spend vs budget, decide whether an external
LLM call is allowed and which alert (if any) to raise. Fail-closed at 100%.
The DB ledger read/write is wired in the subscriber (slice 3c).
"""
from __future__ import annotations

from dataclasses import dataclass

WARN_RATIO = 0.8


@dataclass(frozen=True)
class BudgetDecision:
    allow: bool
    alert: str | None  # None | 'warn_80' | 'blocked_100'


def evaluate_budget(spent_usd: float, budget_usd: float, *, warn_ratio: float = WARN_RATIO) -> BudgetDecision:
    if budget_usd <= 0:
        return BudgetDecision(allow=True, alert=None)  # no budget configured -> allow
    ratio = spent_usd / budget_usd
    if ratio >= 1.0:
        return BudgetDecision(allow=False, alert="blocked_100")
    if ratio >= warn_ratio:
        return BudgetDecision(allow=True, alert="warn_80")
    return BudgetDecision(allow=True, alert=None)

# TODO(Phase 1.4, FR-329): implement record_usage(conn, provider, cost_usd) and call it after every
# real (non-mock) LLM call so the gate actually trips. Until then spend stays 0 for real providers.
async def get_period_budget(conn, provider: str, monthly_budget_usd: float) -> tuple[float, float]:
    """Return (spent_usd, budget_usd) for the active ledger period of a provider.
    No ledger row yet -> (0, monthly_budget_usd) (full budget available)."""
    row = await conn.fetchrow(
        "SELECT cost_usd, budget_usd FROM public.llm_budget_ledger "
        "WHERE provider=$1 AND active=TRUE ORDER BY period_start DESC LIMIT 1",
        provider,
    )
    if row is None:
        return 0.0, monthly_budget_usd
    return float(row["cost_usd"]), float(row["budget_usd"])