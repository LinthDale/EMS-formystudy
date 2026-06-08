"""Integration: on-demand reclassify primitive (PRD-0003 §234/§761, FR-330 rerun /
MCP classify_with_context core). Reads recent measurement samples (OPS pool, SELECT-only)
-> classify. Seeding/cleanup of the measurement hypertables needs a superuser connection
because device_service_ops has SELECT-only on them (no INSERT/DELETE)."""
import os

import asyncpg
import pytest

pytestmark = pytest.mark.integration

_PREFIX = "itest-recl-"


async def _ctx():
    from device_service.classifier import Classifier
    from device_service.config import Settings
    from device_service.db import Database
    from device_service.llm.guardrail import MockGuardrail
    from device_service.llm.mock_provider import MockProvider

    settings = Settings(
        _env_file=None, db_host=os.getenv("EMS_DB_HOST", "timescaledb"), db_name="ems",
        db_ai_password=os.getenv("DB_AI_PASSWORD", "devAI_rotate_in_prod_7x2k"),
        db_ops_password=os.getenv("DB_OPS_PASSWORD", "devOPS_rotate_in_prod_9q4m"),
        llm_provider="mock",
    )
    db = Database(host=settings.db_host, port=settings.db_port, name=settings.db_name,
                  ai_password=settings.db_ai_password, ops_password=settings.db_ops_password)
    try:
        await db.connect()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB not reachable / roles not set: {exc}")
    return settings, db, Classifier(MockProvider(), MockGuardrail())


async def _su():
    """Superuser connection — needed to INSERT/DELETE measurement rows (OPS has SELECT-only)."""
    try:
        return await asyncpg.connect(
            host=os.getenv("EMS_DB_HOST", "timescaledb"), database="ems",
            user="postgres", password=os.getenv("POSTGRES_PASSWORD", "postgres"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"superuser DB connection unavailable: {exc}")


async def _cleanup(su):
    await su.execute(f"DELETE FROM public.electricity_measurements WHERE device_id LIKE '{_PREFIX}%'")
    await su.execute(f"DELETE FROM public.devices WHERE device_id LIKE '{_PREFIX}%'")


@pytest.fixture
async def ctx():
    settings, db, classifier = await _ctx()
    su = await _su()
    await _cleanup(su)
    yield settings, db, classifier, su
    await _cleanup(su)
    await su.close()
    await db.close()


async def _device(su, device_id):
    return await su.fetchrow(
        "SELECT status, device_type, ai_confidence, classified_by FROM public.devices WHERE device_id=$1",
        device_id)


async def test_reclassify_uses_recent_samples_and_classifies(ctx):
    from device_service.discovery_pipeline import reclassify_device
    settings, db, classifier, su = ctx
    dev = f"{_PREFIX}elec"
    await su.execute(
        "INSERT INTO public.devices (device_id, status, gateway_id, metadata) "
        "VALUES ($1,'candidate','ems-gateway', jsonb_build_object('source_topic','ems/devices/'||$1||'/measurements'))",
        dev)
    for i in range(3):
        await su.execute(
            "INSERT INTO public.electricity_measurements (time, device_id, voltage, current, power_kw, energy_kwh) "
            "VALUES (now() - ($2||' seconds')::interval, $1, 220, 1.1, 0.2, 10.0)", dev, str(i))
    outcome = await reclassify_device(db, classifier, settings, device_id=dev)
    assert outcome is not None and outcome.summary_source == "llm"
    row = await _device(su, dev)
    assert row["ai_confidence"] is not None and row["classified_by"] == "ai"  # candidate got classified


async def test_reclassify_no_samples_returns_none(ctx):
    from device_service.discovery_pipeline import reclassify_device
    settings, db, classifier, su = ctx
    dev = f"{_PREFIX}nosamples"
    await su.execute("INSERT INTO public.devices (device_id, status, gateway_id) VALUES ($1,'candidate','ems-gateway')", dev)
    assert await reclassify_device(db, classifier, settings, device_id=dev) is None


async def test_reclassify_unknown_gateway_returns_none(ctx):
    from device_service.discovery_pipeline import reclassify_device
    settings, db, classifier, su = ctx
    dev = f"{_PREFIX}nogw"
    await su.execute("INSERT INTO public.devices (device_id, status, gateway_id) VALUES ($1,'candidate',NULL)", dev)
    assert await reclassify_device(db, classifier, settings, device_id=dev) is None


async def test_reclassify_unknown_device_returns_none(ctx):
    from device_service.discovery_pipeline import reclassify_device
    settings, db, classifier, su = ctx
    assert await reclassify_device(db, classifier, settings, device_id=f"{_PREFIX}ghost") is None


async def test_reclassify_non_candidate_skipped_even_with_samples(ctx):
    """A confirmed/frozen device is skipped (returns None) BEFORE any LLM call — even with
    samples present — so rerun never burns budget on a guaranteed apply_outcome no-op. Operator
    must demote_to_candidate first (FR-330 / §900)."""
    from device_service.discovery_pipeline import reclassify_device
    settings, db, classifier, su = ctx
    dev = f"{_PREFIX}confirmed"
    await su.execute(
        "INSERT INTO public.devices (device_id, status, gateway_id, classified_by) "
        "VALUES ($1,'confirmed','ems-gateway','human')", dev)
    await su.execute(
        "INSERT INTO public.electricity_measurements (time, device_id, voltage, current, power_kw, energy_kwh) "
        "VALUES (now(), $1, 220, 1.1, 0.2, 10.0)", dev)
    assert await reclassify_device(db, classifier, settings, device_id=dev) is None
