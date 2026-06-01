"""Integration: budget ledger record_usage + gate trip for a real (non-mock) provider."""
import os

import pytest

pytestmark = pytest.mark.integration

_PROV = "itest-prov"


async def _db():
    from device_service.config import Settings
    from device_service.db import Database
    s = Settings(
        _env_file=None, db_host=os.getenv("EMS_DB_HOST", "timescaledb"), db_name="ems",
        db_ai_password=os.getenv("DB_AI_PASSWORD", "devAI_rotate_in_prod_7x2k"),
        db_ops_password=os.getenv("DB_OPS_PASSWORD", "devOPS_rotate_in_prod_9q4m"),
    )
    db = Database(host=s.db_host, port=s.db_port, name=s.db_name,
                  ai_password=s.db_ai_password, ops_password=s.db_ops_password)
    try:
        await db.connect()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB not reachable: {exc}")
    return s, db


async def _cleanup(db):
    async with db.ops_pool.acquire() as conn:
        await conn.execute("DELETE FROM public.llm_budget_ledger WHERE provider=$1", _PROV)
        await conn.execute("DELETE FROM public.devices WHERE device_id LIKE 'itest-bud-%'")


@pytest.fixture
async def budget_db():
    s, db = await _db()
    await _cleanup(db)
    yield s, db
    await _cleanup(db)
    await db.close()


async def test_record_usage_accumulates_and_reads_back(budget_db):
    from device_service.budget_ledger import current_period, get_period_budget, record_usage
    _, db = budget_db
    ps, pe = current_period()
    async with db.ai_tx() as conn:
        await record_usage(conn, _PROV, ps, pe, "claude-haiku-4-5", 1_000_000, 0, 20.0)  # 0.80
        await record_usage(conn, _PROV, ps, pe, "claude-haiku-4-5", 0, 1_000_000, 20.0)  # 4.00
    async with db.ai_pool.acquire() as conn:
        spent, budget = await get_period_budget(conn, _PROV, ps, 20.0)
    assert abs(spent - 4.80) < 1e-6 and budget == 20.0


async def test_budget_gate_trips_for_nonmock_provider(budget_db):
    """Seed the ledger over budget; process_message must fall back (not consume LLM)."""
    from types import SimpleNamespace

    from device_service.budget_ledger import current_period, record_usage
    from device_service.classifier import Classifier
    from device_service.discovery import AdmissionGate, process_message
    from device_service.llm.guardrail import MockGuardrail
    from device_service.llm.types import ClassificationResult, SignalSuggestion

    s, db = budget_db
    settings = SimpleNamespace(llm_provider=_PROV, llm_model="claude-haiku-4-5", llm_monthly_budget_usd=20.0)
    ps, pe = current_period()
    async with db.ai_tx() as conn:
        await record_usage(conn, _PROV, ps, pe, "claude-haiku-4-5", 6_000_000, 0, 20.0)  # 4.8... seed to >=100%
    # push to >= budget
    async with db.ai_tx() as conn:
        await record_usage(conn, _PROV, ps, pe, "claude-haiku-4-5", 25_000_000, 0, 20.0)  # +20 -> >=20

    class _Provider:
        name = _PROV
        calls = 0
        async def classify_device(self, d, t, sanitized):
            type(self).calls += 1
            return ClassificationResult("electricity",
                (SignalSuggestion("voltage", "V", "float", "read"),), 0.95, "ok",
                {"provider": _PROV, "usage": {"input_tokens": 10, "output_tokens": 10}})

    prov = _Provider()
    status = await process_message(
        "ems/devices/itest-bud-1/measurements", b"e,d=x voltage=220 1",
        db=db, classifier=Classifier(prov, MockGuardrail()), gate=AdmissionGate(),
        settings=settings, now=1.0)
    assert status == "created:candidate"          # fell back to candidate (budget blocked)
    assert prov.calls == 0                          # real provider was NOT called
    async with db.ops_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT classified_by, ai_provider FROM public.devices WHERE device_id='itest-bud-1'")
    assert row["ai_provider"] is None               # system_fallback, no provider attributed

# --- FR-329 hard cap + concurrency (§13) ---

_MODEL = "claude-haiku-4-5"


async def _seed(db, ps, pe, cost, budget):
    async with db.ops_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO public.llm_budget_ledger
                   (period_start, period_end, provider, cost_usd, budget_usd, active, updated_at)
               VALUES ($1,$2,$3,$4,$5,TRUE, now())
               ON CONFLICT (period_start, provider) DO UPDATE SET cost_usd=EXCLUDED.cost_usd""",
            ps, pe, _PROV, cost, budget)


async def _cost(db, ps):
    async with db.ops_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT cost_usd FROM public.llm_budget_ledger WHERE provider=$1 AND period_start=$2", _PROV, ps)
    return float(row["cost_usd"])


async def test_reserve_denies_when_call_would_cross_budget(budget_db):
    from device_service.budget_ledger import budget_reserve, current_period, reserve_estimate
    _, db = budget_db
    ps, pe = current_period()
    est = reserve_estimate(_MODEL)
    budget = 20.0
    await _seed(db, ps, pe, budget - est / 2, budget)   # headroom < one call
    async with db.ai_tx() as conn:
        ok = await budget_reserve(conn, _PROV, ps, pe, est, budget)
    assert ok is False
    assert abs(await _cost(db, ps) - (budget - est / 2)) < 1e-3   # unchanged, no overspend (NUMERIC(10,4))


async def test_concurrent_reserves_only_one_succeeds(budget_db):
    import asyncio
    from device_service.budget_ledger import budget_reserve, current_period, reserve_estimate
    _, db = budget_db
    ps, pe = current_period()
    est = reserve_estimate(_MODEL)
    budget = 20.0
    await _seed(db, ps, pe, budget - 1.5 * est, budget)   # only ONE more call fits

    async def _r():
        async with db.ai_tx() as conn:
            return await budget_reserve(conn, _PROV, ps, pe, est, budget)

    r1, r2 = await asyncio.gather(_r(), _r())
    assert sorted([r1, r2]) == [False, True]              # advisory lock prevents double-pass
    assert abs(await _cost(db, ps) - (budget - 1.5 * est + est)) < 1e-3  # exactly one reservation


async def test_settle_refunds_overreservation(budget_db):
    from device_service.budget_ledger import (
        budget_reserve, budget_settle, current_period, estimate_cost, reserve_estimate)
    _, db = budget_db
    ps, pe = current_period()
    est = reserve_estimate(_MODEL)
    async with db.ai_tx() as conn:
        assert await budget_reserve(conn, _PROV, ps, pe, est, 20.0)
    async with db.ai_tx() as conn:
        actual = await budget_settle(conn, _PROV, ps, est, _MODEL, 100, 50)
    expected = estimate_cost(_MODEL, 100, 50)
    assert abs(actual - expected) < 1e-9
    assert abs(await _cost(db, ps) - expected) < 1e-3     # ledger holds actual, not the reservation (NUMERIC(10,4))


async def test_fallback_settle_refunds_full_reservation(budget_db):
    from device_service.budget_ledger import budget_reserve, budget_settle, current_period, reserve_estimate
    _, db = budget_db
    ps, pe = current_period()
    est = reserve_estimate(_MODEL)
    async with db.ai_tx() as conn:
        assert await budget_reserve(conn, _PROV, ps, pe, est, 20.0)
    async with db.ai_tx() as conn:
        await budget_settle(conn, _PROV, ps, est, _MODEL, 0, 0)   # no real call -> full refund
    assert await _cost(db, ps) < 1e-9

async def test_real_provider_classify_settles_actual_cost(budget_db):
    """Reserve succeeds, real provider classifies, settle records actual cost (>0)."""
    from types import SimpleNamespace
    from device_service.classifier import Classifier
    from device_service.discovery import AdmissionGate, process_message
    from device_service.llm.guardrail import MockGuardrail
    from device_service.llm.types import ClassificationResult, SignalSuggestion

    _, db = budget_db
    settings = SimpleNamespace(llm_provider=_PROV, llm_model=_MODEL, llm_monthly_budget_usd=20.0)

    class _Provider:
        name = _PROV
        async def classify_device(self, d, t, sanitized):
            return ClassificationResult(
                "electricity", (SignalSuggestion("voltage", "V", "float", "read"),), 0.95, "ok",
                {"provider": _PROV, "usage": {"input_tokens": 1000, "output_tokens": 500}})

    status = await process_message(
        "ems/devices/itest-bud-2/measurements", b"e,d=x voltage=220 1",
        db=db, classifier=Classifier(_Provider(), MockGuardrail()), gate=AdmissionGate(),
        settings=settings, now=1.0)
    assert status == "created:confirmed"
    from device_service.budget_ledger import current_period, estimate_cost
    ps, _ = current_period()
    expected = estimate_cost(_MODEL, 1000, 500)
    assert abs(await _cost(db, ps) - expected) < 1e-3   # settled to actual, reservation refunded