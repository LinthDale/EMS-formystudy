"""Integration: relevance retrieval + applied_count + latest-for-conflict
(PRD §8.6.4 / FR-331 / FR-332). Exercises correction_repo against TimescaleDB."""
import os

import pytest

pytestmark = pytest.mark.integration

_SALT = "itest-retr-salt"


async def _db():
    from device_service.config import Settings
    from device_service.db import Database

    settings = Settings(
        _env_file=None,
        db_host=os.getenv("EMS_DB_HOST", "timescaledb"),
        db_port=int(os.getenv("EMS_DB_PORT", "5432")),
        db_name="ems",
        db_ai_password=os.getenv("DB_AI_PASSWORD", "devAI_rotate_in_prod_7x2k"),
        db_ops_password=os.getenv("DB_OPS_PASSWORD", "devOPS_rotate_in_prod_9q4m"),
    )
    db = Database(host=settings.db_host, port=settings.db_port, name=settings.db_name,
                  ai_password=settings.db_ai_password, ops_password=settings.db_ops_password)
    try:
        await db.connect()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB not reachable / roles not set: {exc}")
    return db


async def _cleanup(db):
    async with db.ops_pool.acquire() as conn:
        await conn.execute("DELETE FROM public.devices WHERE device_id LIKE 'itest-retr-%'")


async def _mk_device(conn, device_id, *, gateway_id=None, source_topic=None):
    await conn.execute(
        """INSERT INTO public.devices (device_id, status, gateway_id, metadata)
           VALUES ($1, 'candidate', $2, jsonb_build_object('source_topic', $3::text))
           ON CONFLICT (device_id) DO UPDATE SET gateway_id=EXCLUDED.gateway_id, metadata=EXCLUDED.metadata""",
        device_id, gateway_id, source_topic,
    )


async def _mk_correction(conn, device_id, *, corrected_type=None, active=True):
    return await conn.fetchval(
        """INSERT INTO public.device_corrections
              (device_id, verdict, corrected_device_type, human_explanation,
               created_by_key_id, salt_version, is_active)
           VALUES ($1, 'wrong_classification', $2,
                   'a sufficiently long operator explanation for this correction row', 'kid', 'v1', $3)
           RETURNING id""",
        device_id, corrected_type, active,
    )


@pytest.fixture
async def db():
    d = await _db()
    await _cleanup(d)
    yield d
    await _cleanup(d)
    await d.close()


async def test_retrieve_relevant_union_of_device_gateway_type_topic(db):
    from device_service.repositories import correction_repo

    async with db.ops_pool.acquire() as conn:
        # target device X: gateway gw-A, topic ems/factory/X
        await _mk_device(conn, "itest-retr-X", gateway_id="gw-A", source_topic="ems/factory/itest-retr-X")
        # matches by SAME DEVICE
        c_dev = await _mk_correction(conn, "itest-retr-X", corrected_type="motor")
        # matches by SAME GATEWAY (gw-A), different topic prefix, non-family type
        await _mk_device(conn, "itest-retr-gw", gateway_id="gw-A", source_topic="other/path/g")
        c_gw = await _mk_correction(conn, "itest-retr-gw", corrected_type="valve")
        # matches by TYPE FAMILY (electricity) only — different gateway + topic
        await _mk_device(conn, "itest-retr-type", gateway_id="gw-B", source_topic="zzz/qqq/t")
        c_type = await _mk_correction(conn, "itest-retr-type", corrected_type="electricity")
        # matches by TOPIC PREFIX (ems/factory) only — different gateway, non-family type
        await _mk_device(conn, "itest-retr-topic", gateway_id="gw-C", source_topic="ems/factory/other")
        c_topic = await _mk_correction(conn, "itest-retr-topic", corrected_type="hvac")
        # NON-match: different everything + deactivated
        await _mk_device(conn, "itest-retr-none", gateway_id="gw-Z", source_topic="no/match/n")
        c_inactive = await _mk_correction(conn, "itest-retr-none", corrected_type="motor", active=False)

        rows = await correction_repo.retrieve_relevant(
            conn, device_id="itest-retr-X", gateway_id="gw-A",
            device_type_family=("electricity",), topic_prefix="ems/factory",
        )
    got = {r["id"] for r in rows}
    assert {c_dev, c_gw, c_type, c_topic} <= got
    assert c_inactive not in got  # is_active=false excluded


async def test_retrieve_relevant_null_gateway_does_not_match_everything(db):
    from device_service.repositories import correction_repo

    async with db.ops_pool.acquire() as conn:
        await _mk_device(conn, "itest-retr-a", gateway_id=None, source_topic="p/q/a")
        ca = await _mk_correction(conn, "itest-retr-a", corrected_type="motor")
        await _mk_device(conn, "itest-retr-b", gateway_id=None, source_topic="r/s/b")
        cb = await _mk_correction(conn, "itest-retr-b", corrected_type="valve")
        # device a, NULL gateway, no family/topic overlap -> only its own correction
        rows = await correction_repo.retrieve_relevant(
            conn, device_id="itest-retr-a", gateway_id=None,
            device_type_family=(), topic_prefix="",
        )
    ids = {r["id"] for r in rows}
    assert ca in ids and cb not in ids


async def test_mark_applied_increments_count_and_timestamp(db):
    from device_service.repositories import correction_repo

    async with db.ops_pool.acquire() as conn:
        await _mk_device(conn, "itest-retr-app", source_topic="a/b/c")
        cid = await _mk_correction(conn, "itest-retr-app")
        await correction_repo.mark_applied(conn, [cid])
        await correction_repo.mark_applied(conn, [cid])
        row = await conn.fetchrow(
            "SELECT applied_count, last_applied_at FROM public.device_corrections WHERE id=$1", cid)
        assert row["applied_count"] == 2 and row["last_applied_at"] is not None
        # empty list is a no-op (must not raise / not touch anything)
        await correction_repo.mark_applied(conn, [])


async def test_latest_corrected_device_type_prefers_device_then_gateway(db):
    from device_service.repositories import correction_repo

    async with db.ops_pool.acquire() as conn:
        await _mk_device(conn, "itest-retr-L", gateway_id="gw-L", source_topic="t/u/L")
        await _mk_device(conn, "itest-retr-Lg", gateway_id="gw-L", source_topic="t/u/Lg")
        # gateway sibling has a correction; target device has none yet
        await _mk_correction(conn, "itest-retr-Lg", corrected_type="pressure")
        via_gw = await correction_repo.latest_corrected_device_type(
            conn, device_id="itest-retr-L", gateway_id="gw-L")
        assert via_gw == "pressure"  # fell back to gateway
        # now the device gets its own newer correction -> device wins
        await _mk_correction(conn, "itest-retr-L", corrected_type="electricity")
        via_dev = await correction_repo.latest_corrected_device_type(
            conn, device_id="itest-retr-L", gateway_id="gw-L")
        assert via_dev == "electricity"
        # no corrections + no gateway match -> None
        await _mk_device(conn, "itest-retr-empty", gateway_id="gw-EMPTY", source_topic="x/y/z")
        assert await correction_repo.latest_corrected_device_type(
            conn, device_id="itest-retr-empty", gateway_id="gw-EMPTY") is None
