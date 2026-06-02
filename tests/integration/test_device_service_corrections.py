"""Integration: human AI-feedback corrections API (PRD-0003 Phase 1.4 slice 2b)."""
import os

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

_OPS = {"X-API-Key": "ops-k"}
_AI = {"X-API-Key": "ai-k"}


async def _make_app(*, audit_hash_salt: str = "itest-audit-salt"):
    from device_service.config import Settings
    from device_service.db import Database
    from device_service.main import create_app

    settings = Settings(
        _env_file=None,
        db_host=os.getenv("EMS_DB_HOST", "timescaledb"),
        db_port=int(os.getenv("EMS_DB_PORT", "5432")),
        db_name="ems",
        db_ai_password=os.getenv("DB_AI_PASSWORD", "devAI_rotate_in_prod_7x2k"),
        db_ops_password=os.getenv("DB_OPS_PASSWORD", "devOPS_rotate_in_prod_9q4m"),
        ops_api_key="ops-k", ingest_api_key="ing-k", ai_api_key="ai-k",
        audit_hash_salt=audit_hash_salt, audit_salt_version="itest-v1",
    )
    db = Database(host=settings.db_host, port=settings.db_port, name=settings.db_name,
                  ai_password=settings.db_ai_password, ops_password=settings.db_ops_password)
    try:
        await db.connect()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB not reachable / roles not set: {exc}")
    app = create_app()
    app.state.settings = settings
    app.state.db = db
    return app, db


async def _cleanup(db):
    async with db.ops_pool.acquire() as conn:
        await conn.execute("DELETE FROM public.devices WHERE device_id LIKE 'itest-corr-%'")


@pytest.fixture
async def api():
    app, db = await _make_app()
    await _cleanup(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        yield client, db
    await _cleanup(db)
    await db.close()


async def _seed_device(client, device_id: str = "itest-corr-1"):
    r = await client.post("/devices", json={"device_id": device_id, "device_type": "unknown"}, headers=_OPS)
    assert r.status_code == 201


def _body(**overrides):
    body = {
        "verdict": "wrong_classification",
        "corrected_device_type": "electricity",
        "corrected_signals": [{"signal_name": "voltage", "unit": "V"}],
        "human_explanation": "The device is an electricity meter based on the voltage telemetry pattern.",
        "prompt_version_at_correction": "pv-itest",
    }
    body.update(overrides)
    return body


async def test_ai_feedback_creates_correction_and_hides_raw_key(api):
    client, db = api
    await _seed_device(client)

    r = await client.post("/devices/itest-corr-1/ai-feedback", json=_body(), headers=_OPS)
    assert r.status_code == 201
    body = r.json()
    assert body["device_id"] == "itest-corr-1"
    assert body["verdict"] == "wrong_classification"
    assert body["corrected_signals"][0]["signal_name"] == "voltage"
    assert body["created_by_key_id"] != "ops-k"
    assert len(body["created_by_key_id"]) == 64
    assert body["salt_version"] == "itest-v1"
    assert body["is_active"] is True and body["applied_count"] == 0
    # provenance is server-stamped (PROMPT_VERSION), not whatever the client sent
    assert body["prompt_version_at_correction"] == "v1"

    async with db.ops_pool.acquire() as conn:
        assert await conn.fetchval(
            "SELECT count(*) FROM public.device_corrections WHERE device_id='itest-corr-1'"
        ) == 1


async def test_ai_feedback_validates_text_and_requires_ops_channel(api):
    client, _ = api
    await _seed_device(client)

    bad = _body(human_explanation="too short")
    r = await client.post("/devices/itest-corr-1/ai-feedback", json=bad, headers=_OPS)
    assert r.status_code == 400  # FR-330: content-rule violation -> 400 (not 422)
    assert r.json()["detail"]["reason"] == "length"

    assert (await client.post("/devices/itest-corr-1/ai-feedback", json=_body(), headers=_AI)).status_code == 403
    assert (await client.post("/devices/itest-corr-1/ai-feedback", json=_body())).status_code == 401


async def test_ai_feedback_missing_device_404(api):
    client, _ = api
    r = await client.post("/devices/itest-corr-missing/ai-feedback", json=_body(), headers=_OPS)
    assert r.status_code == 404


async def test_ai_feedback_rerun_classification_deferred_501(api):
    """rerun_classification needs the on-demand reclassify pipeline (MCP classify_with_context
    primitive); a true value is rejected (501) rather than silently ignored, with no DB write."""
    client, db = api
    await _seed_device(client)
    r = await client.post("/devices/itest-corr-1/ai-feedback",
                          json=_body(rerun_classification=True), headers=_OPS)
    assert r.status_code == 501
    # combined with demote, the 501 still wins (rerun checked first) and nothing is written
    r2 = await client.post("/devices/itest-corr-1/ai-feedback",
                           json=_body(rerun_classification=True, demote_to_candidate=True), headers=_OPS)
    assert r2.status_code == 501
    async with db.ops_pool.acquire() as conn:
        assert await conn.fetchval(
            "SELECT count(*) FROM public.device_corrections WHERE device_id='itest-corr-1'") == 0


async def test_ai_feedback_demote_retired_device_409(api):
    """A retired device must not be resurrected into the AI pipeline via demote (HIGH fix).
    409 + no correction written."""
    client, db = api
    await _seed_device(client)
    assert (await client.delete("/devices/itest-corr-1", headers=_OPS)).status_code == 204  # -> retired
    r = await client.post("/devices/itest-corr-1/ai-feedback",
                          json=_body(demote_to_candidate=True), headers=_OPS)
    assert r.status_code == 409
    async with db.ops_pool.acquire() as conn:
        assert await conn.fetchval(
            "SELECT count(*) FROM public.device_corrections WHERE device_id='itest-corr-1'") == 0


async def test_ai_feedback_demote_to_candidate_reopens_frozen_device(api):
    """FR-330 demote_to_candidate: re-open a human-confirmed (frozen) device for review.
    The correction is written AND the device flips confirmed->candidate (classified_by
    cleared) via the freeze-override token, so the AI path may re-classify it later."""
    client, db = api
    await _seed_device(client)
    # confirm -> frozen (classified_by=human, status=confirmed)
    assert (await client.post("/devices/itest-corr-1/confirm", headers=_OPS)).json()["status"] == "confirmed"
    # a plain PATCH on the frozen device is blocked (proves it is frozen)
    assert (await client.patch("/devices/itest-corr-1", json={"device_type": "motor"}, headers=_OPS)).status_code == 409

    r = await client.post("/devices/itest-corr-1/ai-feedback",
                          json=_body(demote_to_candidate=True), headers=_OPS)
    assert r.status_code == 201  # correction recorded
    dev = (await client.get("/devices/itest-corr-1", headers=_OPS)).json()
    assert dev["status"] == "candidate" and dev["classified_by"] is None and dev["confirmed_at"] is None


async def test_list_and_deactivate_corrections(api):
    client, _ = api
    await _seed_device(client)
    created = (await client.post("/devices/itest-corr-1/ai-feedback", json=_body(), headers=_OPS)).json()

    listed = (await client.get("/devices/itest-corr-1/corrections", headers=_OPS)).json()
    assert [c["id"] for c in listed] == [created["id"]]

    reason = "This correction is superseded by a newer operator review with better evidence."
    r = await client.post(f"/devices/itest-corr-1/corrections/{created['id']}/deactivate",
                          json={"reason": reason}, headers=_OPS)
    assert r.status_code == 200
    assert r.json()["is_active"] is False
    assert r.json()["deactivation_reason"] == reason

    assert (await client.post(f"/devices/itest-corr-1/corrections/{created['id']}/deactivate",
                              json={"reason": reason}, headers=_OPS)).status_code == 409

    # active_only filters out the now-deactivated correction
    all_listed = (await client.get("/devices/itest-corr-1/corrections", headers=_OPS)).json()
    active = (await client.get("/devices/itest-corr-1/corrections",
                               params={"active_only": "true"}, headers=_OPS)).json()
    assert [c["id"] for c in all_listed] == [created["id"]] and active == []


async def test_corrections_list_and_deactivate_missing_device_404(api):
    client, _ = api
    assert (await client.get("/devices/itest-corr-absent/corrections", headers=_OPS)).status_code == 404
    r = await client.post("/devices/itest-corr-absent/corrections/1/deactivate",
                          json={"reason": "a sufficiently long operator reason for deactivating here"},
                          headers=_OPS)
    assert r.status_code == 404


async def test_ai_feedback_rate_limits_per_device_and_key(api):
    client, db = api
    await _seed_device(client)
    async with db.ops_pool.acquire() as conn:
        key_id = "k" * 64
        await conn.executemany(
            """INSERT INTO public.device_corrections
                  (device_id, verdict, human_explanation, created_by_key_id, salt_version)
               VALUES ('itest-corr-1', 'good_with_note', $1, $2, 'itest-v1')""",
            [(f"valid operator explanation number {i} with enough text", key_id) for i in range(10)],
        )
    r = await client.post("/devices/itest-corr-1/ai-feedback", json=_body(), headers=_OPS)
    assert r.status_code == 429
    assert "per-device" in r.json()["detail"]

    await _seed_device(client, "itest-corr-key")
    async with db.ops_pool.acquire() as conn:
        from device_service.key_id import hash_key_id
        real_key_id = hash_key_id("ops-k", "itest-audit-salt", "itest-v1")
        for i in range(30):
            dev = f"itest-corr-key-{i}"
            await conn.execute(
                "INSERT INTO public.devices (device_id, status) VALUES ($1, 'candidate') ON CONFLICT DO NOTHING",
                dev,
            )
            await conn.execute(
                """INSERT INTO public.device_corrections
                      (device_id, verdict, human_explanation, created_by_key_id, salt_version)
                   VALUES ($1, 'good_with_note', $2, $3, 'itest-v1')""",
                dev, f"valid operator explanation for key limit {i} with enough text", real_key_id,
            )
    r = await client.post("/devices/itest-corr-key/ai-feedback", json=_body(), headers=_OPS)
    assert r.status_code == 429
    assert "per-key" in r.json()["detail"]


async def test_ai_feedback_missing_audit_salt_fails_closed():
    app, db = await _make_app(audit_hash_salt="")
    await _cleanup(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        await _seed_device(client)
        r = await client.post("/devices/itest-corr-1/ai-feedback", json=_body(), headers=_OPS)
        assert r.status_code == 503
        async with db.ops_pool.acquire() as conn:
            assert await conn.fetchval(
                "SELECT count(*) FROM public.device_corrections WHERE device_id='itest-corr-1'"
            ) == 0
    await _cleanup(db)
    await db.close()
