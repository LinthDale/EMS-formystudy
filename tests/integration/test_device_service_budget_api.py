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