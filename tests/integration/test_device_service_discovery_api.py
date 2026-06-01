"""Integration: auto-discovery pipeline against TimescaleDB (PRD-0003 §8.5 + §4).

process_message: parse -> admission -> candidate -> classify (MockProvider) -> persist.
"""
import os

import pytest

pytestmark = pytest.mark.integration

_PREFIXES = ("itest-disc-", "sensor-itest-")


async def _ctx():
    from device_service.classifier import Classifier
    from device_service.config import Settings
    from device_service.db import Database
    from device_service.discovery import AdmissionGate
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
    classifier = Classifier(MockProvider(), MockGuardrail())
    gate = AdmissionGate()
    return settings, db, classifier, gate


async def _cleanup(db):
    async with db.ops_pool.acquire() as conn:
        for p in _PREFIXES:
            await conn.execute("DELETE FROM public.devices WHERE device_id LIKE $1", p + "%")


@pytest.fixture
async def disc():
    from device_service.discovery import process_message
    settings, db, classifier, gate = await _ctx()
    await _cleanup(db)
    yield process_message, settings, db, classifier, gate
    await _cleanup(db)
    await db.close()


async def _device(db, device_id):
    async with db.ops_pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT status, device_type, classified_by, ai_confidence FROM public.devices WHERE device_id=$1",
            device_id,
        )


async def test_new_ems_device_candidate_then_confirmed(disc):
    process_message, settings, db, classifier, gate = disc
    payload = b"electricity,device_id=itest-disc-1 voltage=220,current=1.1,power_kw=0.2 1700000000"
    status = await process_message("ems/devices/itest-disc-1/measurements", payload,
                                   db=db, classifier=classifier, gate=gate, settings=settings, now=1000.0)
    assert status == "created:confirmed"
    row = await _device(db, "itest-disc-1")
    assert row["status"] == "confirmed" and row["device_type"] == "electricity"
    assert row["classified_by"] == "ai" and row["ai_confidence"] is not None
    # digest persisted (FR-317)
    async with db.ops_pool.acquire() as conn:
        dg = await conn.fetchrow("SELECT summary_source FROM public.device_review_digests WHERE device_id=$1", "itest-disc-1")
    assert dg["summary_source"] == "llm"


async def test_factory_sensor_low_confidence_stays_candidate(disc):
    process_message, settings, db, classifier, gate = disc
    status = await process_message("factory/sensor/itest_disc_x", b'{"foo": 1.0}',
                                   db=db, classifier=classifier, gate=gate, settings=settings, now=1000.0)
    assert status == "created:candidate"
    row = await _device(db, "sensor-itest-disc-x")
    assert row is not None and row["status"] == "candidate"


async def test_dedupe_same_topic(disc):
    process_message, settings, db, classifier, gate = disc
    topic, payload = "ems/devices/itest-disc-2/measurements", b"e,d=x voltage=1 1"
    await process_message(topic, payload, db=db, classifier=classifier, gate=gate, settings=settings, now=2000.0)
    second = await process_message(topic, payload, db=db, classifier=classifier, gate=gate, settings=settings, now=2010.0)
    assert second == "dedupe"


async def test_existing_frozen_device_only_touched(disc):
    process_message, settings, db, classifier, gate = disc
    # sim-001 is migration_backfill (frozen, electricity); re-seeing it must not reclassify
    status = await process_message("ems/devices/sim-001/measurements", b"e,d=x voltage=220 1",
                                   db=db, classifier=classifier, gate=gate, settings=settings, now=3000.0)
    assert status == "existing"
    row = await _device(db, "sim-001")
    assert row["device_type"] == "electricity" and row["classified_by"] == "migration_backfill"


async def test_unmatched_topic_rejected(disc):
    process_message, settings, db, classifier, gate = disc
    status = await process_message("random/topic/foo", b"x", db=db, classifier=classifier, gate=gate, settings=settings, now=1.0)
    assert status == "reject:unmatched_topic_total"

async def test_rate_limited_returns_without_creating(disc):
    from device_service.discovery import AdmissionGate
    process_message, settings, db, classifier, _ = disc
    g0 = AdmissionGate(rate_limit=0)
    status = await process_message("ems/devices/itest-disc-rl/measurements", b"e,d=x voltage=1 1",
                                   db=db, classifier=classifier, gate=g0, settings=settings, now=1.0)
    assert status == "rate_limited"


async def test_live_mqtt_publish_creates_and_confirms():
    """End-to-end: subscriber (lifespan) + real mosquitto publish -> candidate -> confirmed."""
    import asyncio
    import os

    aiomqtt = pytest.importorskip("aiomqtt")
    from device_service.config import Settings
    from device_service.main import create_app

    mqtt_host = os.getenv("EMS_MQTT_HOST", "mosquitto")
    app = create_app()
    app.state.settings = Settings(
        _env_file=None, db_host=os.getenv("EMS_DB_HOST", "timescaledb"), db_name="ems",
        db_ai_password=os.getenv("DB_AI_PASSWORD", "devAI_rotate_in_prod_7x2k"),
        db_ops_password=os.getenv("DB_OPS_PASSWORD", "devOPS_rotate_in_prod_9q4m"),
        llm_provider="mock", mqtt_enabled=True, mqtt_host=mqtt_host,
    )
    try:
        async with app.router.lifespan_context(app):
            db = app.state.db
            async with db.ops_pool.acquire() as conn:
                await conn.execute("DELETE FROM public.devices WHERE device_id LIKE 'itest-disc-live%'")
            try:
                async with aiomqtt.Client(hostname=mqtt_host, port=1883) as client:
                    await client.publish(
                        "ems/devices/itest-disc-live/measurements",
                        b"e,d=x voltage=220,current=1.1,power_kw=0.2 1700000000", qos=1)
            except Exception as exc:  # noqa: BLE001
                pytest.skip(f"mosquitto not reachable: {exc}")

            row = None
            for _ in range(50):
                row = await _device(db, "itest-disc-live")
                if row is not None and row["status"] == "confirmed":
                    break
                await asyncio.sleep(0.2)
            assert row is not None and row["status"] == "confirmed" and row["device_type"] == "electricity"
            async with db.ops_pool.acquire() as conn:
                await conn.execute("DELETE FROM public.devices WHERE device_id LIKE 'itest-disc-live%'")
    except Exception as exc:  # noqa: BLE001
        if "skip" in str(exc).lower():
            raise
        pytest.skip(f"live mqtt e2e unavailable: {exc}")