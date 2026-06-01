"""Unit: LLM budget gate (ADR-014, FR-329/319)."""
from device_service.budget_ledger import evaluate_budget


def test_under_warn_allows_no_alert():
    d = evaluate_budget(5.0, 20.0)
    assert d.allow and d.alert is None


def test_at_80_percent_warns_but_allows():
    d = evaluate_budget(16.0, 20.0)
    assert d.allow and d.alert == "warn_80"


def test_at_100_percent_blocks():
    d = evaluate_budget(20.0, 20.0)
    assert not d.allow and d.alert == "blocked_100"


def test_over_budget_blocks():
    assert not evaluate_budget(25.0, 20.0).allow


def test_zero_budget_allows():
    d = evaluate_budget(5.0, 0.0)
    assert d.allow and d.alert is None

async def test_get_period_budget_no_row_uses_monthly():
    from device_service.budget_ledger import get_period_budget
    class _Conn:
        async def fetchrow(self, *a):
            return None
    assert await get_period_budget(_Conn(), "anthropic", 20.0) == (0.0, 20.0)


async def test_get_period_budget_with_row():
    from device_service.budget_ledger import get_period_budget
    class _Conn:
        async def fetchrow(self, *a):
            return {"cost_usd": 7.5, "budget_usd": 18.0}
    assert await get_period_budget(_Conn(), "anthropic", 20.0) == (7.5, 18.0)