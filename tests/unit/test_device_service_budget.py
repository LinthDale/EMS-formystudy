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
    from datetime import datetime, timezone
    from device_service.budget_ledger import get_period_budget
    class _Conn:
        async def fetchrow(self, *a):
            return None
    ps = datetime(2026, 5, 1, tzinfo=timezone.utc)
    assert await get_period_budget(_Conn(), "anthropic", ps, 20.0) == (0.0, 20.0)


async def test_get_period_budget_with_row():
    from datetime import datetime, timezone
    from device_service.budget_ledger import get_period_budget
    class _Conn:
        async def fetchrow(self, *a):
            return {"cost_usd": 7.5, "budget_usd": 18.0}
    ps = datetime(2026, 5, 1, tzinfo=timezone.utc)
    assert await get_period_budget(_Conn(), "anthropic", ps, 18.0) == (7.5, 18.0)

# --- FR-329 completion: cost estimate + period ---

def test_estimate_cost_known_model():
    from device_service.budget_ledger import estimate_cost
    c = estimate_cost("claude-haiku-4-5", 1_000_000, 1_000_000)
    assert abs(c - (0.80 + 4.00)) < 1e-9


def test_estimate_cost_unknown_model_is_zero():
    from device_service.budget_ledger import estimate_cost
    assert estimate_cost("nope", 5_000_000, 5_000_000) == 0.0


def test_current_period_month_bounds_and_rollover():
    from datetime import datetime, timezone
    from device_service.budget_ledger import current_period
    s, e = current_period(datetime(2026, 5, 17, 9, 0, tzinfo=timezone.utc))
    assert s == datetime(2026, 5, 1, tzinfo=timezone.utc) and e == datetime(2026, 6, 1, tzinfo=timezone.utc)
    s2, e2 = current_period(datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc))
    assert s2 == datetime(2026, 12, 1, tzinfo=timezone.utc) and e2 == datetime(2027, 1, 1, tzinfo=timezone.utc)

async def test_record_usage_warns_on_unpriced_model(caplog):
    import logging
    from device_service.budget_ledger import record_usage
    from datetime import datetime, timezone

    class _Conn:
        async def execute(self, *a):
            return None

    ps = datetime(2026, 5, 1, tzinfo=timezone.utc)
    with caplog.at_level(logging.WARNING, logger="device_service.budget"):
        cost = await record_usage(_Conn(), "p", ps, ps, "unknown-model", 1000, 1000, 20.0)
    assert cost == 0.0
    assert any("not in pricing table" in r.message for r in caplog.records)

# --- §19 migration: pricing override + parameterised reserve estimate ---

def test_resolve_pricing_merges_env_override():
    from device_service.budget_ledger import estimate_cost, resolve_pricing
    p = resolve_pricing('{"my-model": [1.0, 2.0]}')
    assert p["my-model"] == (1.0, 2.0) and "claude-haiku-4-5" in p   # base retained
    assert abs(estimate_cost("my-model", 1_000_000, 1_000_000, p) - 3.0) < 1e-9


def test_resolve_pricing_invalid_json_falls_back_to_base():
    from device_service.budget_ledger import _PRICING, resolve_pricing
    assert resolve_pricing("not json") == _PRICING
    assert resolve_pricing("") == _PRICING


def test_reserve_estimate_honours_tokens_and_pricing():
    from device_service.budget_ledger import reserve_estimate
    assert abs(reserve_estimate("m", 1_000_000, 0, {"m": (1.0, 9.0)}) - 1.0) < 1e-9