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