"""Integration: human AI-feedback corrections API (PRD-0003 Phase 1.4 slice 2b)."""
import json
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
    from device_service.classifier import Classifier
    from device_service.llm.guardrail import MockGuardrail
    from device_service.llm.mock_provider import MockProvider
    app = create_app()
    app.state.settings = settings
    app.state.db = db
    app.state.classifier = Classifier(MockProvider(), MockGuardrail())  # for rerun_classification
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


async def test_ai_feedback_rerun_classification_records_and_triggers_reclassify(api):
    """rerun_classification is now supported (no longer 501): the correction is written (201)
    and an on-demand reclassify is triggered AFTER commit. Reclassify is best-effort — this
    candidate has no measurement samples, so it no-ops, but the correction must still persist
    and the request must succeed. (The reclassify primitive itself is covered end-to-end with
    seeded samples in test_device_service_reclassify.py.)"""
    client, db = api
    await _seed_device(client)
    r = await client.post("/devices/itest-corr-1/ai-feedback",
                          json=_body(rerun_classification=True), headers=_OPS)
    assert r.status_code == 201
    async with db.ops_pool.acquire() as conn:
        assert await conn.fetchval(
            "SELECT count(*) FROM public.device_corrections WHERE device_id='itest-corr-1'") == 1


async def test_ai_feedback_demote_only_valid_for_confirmed(api):
    """demote_to_candidate is the §885 confirmed->candidate transition only. A retired
    device (must not be resurrected) AND a still-candidate device (already the target,
    must not wipe classified_by) both -> 409 with no correction written."""
    client, db = api
    # candidate (freshly created, not confirmed) -> 409
    await _seed_device(client)
    r = await client.post("/devices/itest-corr-1/ai-feedback",
                          json=_body(demote_to_candidate=True), headers=_OPS)
    assert r.status_code == 409
    # retired -> 409
    assert (await client.delete("/devices/itest-corr-1", headers=_OPS)).status_code == 204
    r2 = await client.post("/devices/itest-corr-1/ai-feedback",
                           json=_body(demote_to_candidate=True), headers=_OPS)
    assert r2.status_code == 409
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


async def test_ai_feedback_create_demote_deactivate_write_audit_rows(api):
    """Slice B: create / demote / deactivate each persist a device_audit_log row with the
    HMAC actor_key_id (not the raw key). device_audit_log is append-only, so assert on the
    most-recent rows for this device."""
    client, db = api
    await _seed_device(client)
    await client.post("/devices/itest-corr-1/confirm", headers=_OPS)  # -> confirmed (demote target)
    cid = (await client.post("/devices/itest-corr-1/ai-feedback",
                             json=_body(demote_to_candidate=True), headers=_OPS)).json()["id"]
    reason = "this correction is superseded by a later operator review with stronger evidence here"
    assert (await client.post(f"/devices/itest-corr-1/corrections/{cid}/deactivate",
                              json={"reason": reason}, headers=_OPS)).status_code == 200
    async with db.ops_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT event_type, actor, actor_key_id, correction_id, outcome FROM public.device_audit_log "
            "WHERE device_id='itest-corr-1' ORDER BY id DESC LIMIT 3")
    by_type = {r["event_type"]: r for r in rows}
    assert {"ai_feedback_create", "demote", "deactivate"} <= set(by_type)
    assert by_type["ai_feedback_create"]["correction_id"] == cid
    assert by_type["demote"]["correction_id"] == cid
    assert by_type["deactivate"]["correction_id"] == cid
    for t in ("ai_feedback_create", "demote", "deactivate"):
        assert by_type[t]["actor"] == "ops"
        assert by_type[t]["actor_key_id"] and by_type[t]["actor_key_id"] != "ops-k"


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


async def test_mass_deactivate_marks_audit_row_suspicious(api):
    """FR-344: when a single OPS key crosses the 1h>=5 deactivate window, the deactivate
    audit row is marked suspicious. Robust to append-only accumulation (count only grows)."""
    from device_service.key_id import hash_key_id
    client, db = api
    real_key_id = hash_key_id("ops-k", "itest-audit-salt", "itest-v1")
    # seed 4 prior deactivate audit rows for this key (within the 1h window)
    async with db.ops_pool.acquire() as conn:
        for i in range(4):
            await conn.execute(
                "INSERT INTO public.device_audit_log "
                "(event_type, actor, device_id, actor_key_id, salt_version, correction_id, outcome) "
                "VALUES ('deactivate','ops','itest-corr-seed',$1,'itest-v1',$2,'success')", real_key_id, i)
    # the 5th deactivate (a real one, same OPS key) crosses the threshold
    await _seed_device(client)
    cid = (await client.post("/devices/itest-corr-1/ai-feedback", json=_body(), headers=_OPS)).json()["id"]
    reason = "this correction is being retired after a broader operator audit of the gateway here"
    assert (await client.post(f"/devices/itest-corr-1/corrections/{cid}/deactivate",
                              json={"reason": reason}, headers=_OPS)).status_code == 200
    async with db.ops_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT detail FROM public.device_audit_log WHERE device_id='itest-corr-1' "
            "AND event_type='deactivate' ORDER BY id DESC LIMIT 1")
    detail = json.loads(row["detail"])
    assert detail.get("suspicious") is True and detail["count_1h"] >= 5
    assert detail["count_24h"] >= detail["count_1h"]  # 24h window is a superset of 1h


async def test_deactivate_without_audit_salt_degrades_gracefully():
    """A correction WRITE 503s without AUDIT_HASH_SALT, but deactivate must NOT — its audit
    attribution is best-effort (actor_key_id NULL), the action still succeeds."""
    app, db = await _make_app(audit_hash_salt="")
    await _cleanup(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        await _seed_device(client)
        async with db.ops_pool.acquire() as conn:  # seed a correction directly (API create would 503)
            cid = await conn.fetchval(
                "INSERT INTO public.device_corrections "
                "(device_id, verdict, human_explanation, created_by_key_id, salt_version) "
                "VALUES ('itest-corr-1','good_with_note',"
                "'a valid operator explanation with enough length to pass the check','kid','v1') RETURNING id")
        reason = "this correction is no longer applicable per the latest field operator review here"
        r = await client.post(f"/devices/itest-corr-1/corrections/{cid}/deactivate",
                              json={"reason": reason}, headers=_OPS)
        assert r.status_code == 200  # NOT 503 — graceful degradation
        async with db.ops_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT actor_key_id FROM public.device_audit_log WHERE device_id='itest-corr-1' "
                "AND event_type='deactivate' ORDER BY id DESC LIMIT 1")
        assert row is not None and row["actor_key_id"] is None  # best-effort NULL without salt
    await _cleanup(db)
    await db.close()


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
    # FR-343: the rejection persists a rate_limit_exceeded audit row (committed in its own tx
    # so the 429 rollback does not wipe it), scope=device.
    async with db.ops_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT outcome, detail FROM public.device_audit_log WHERE device_id='itest-corr-1' "
            "AND event_type='rate_limit_exceeded' ORDER BY id DESC LIMIT 1")
    assert row is not None and row["outcome"] == "rate_limited"
    assert json.loads(row["detail"])["scope"] == "device"

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
    async with db.ops_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT detail FROM public.device_audit_log WHERE device_id='itest-corr-key' "
            "AND event_type='rate_limit_exceeded' ORDER BY id DESC LIMIT 1")
    assert row is not None and json.loads(row["detail"])["scope"] == "key"


async def test_ai_feedback_missing_audit_salt_fails_closed():
    app, db = await _make_app(audit_hash_salt="")
    await _cleanup(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        await _seed_device(client)
        # device_audit_log is append-only (not cleaned), so measure a delta around the call
        async with db.ops_pool.acquire() as conn:
            audit_before = await conn.fetchval(
                "SELECT count(*) FROM public.device_audit_log WHERE device_id='itest-corr-1'")
        r = await client.post("/devices/itest-corr-1/ai-feedback", json=_body(), headers=_OPS)
        assert r.status_code == 503
        async with db.ops_pool.acquire() as conn:
            assert await conn.fetchval(
                "SELECT count(*) FROM public.device_corrections WHERE device_id='itest-corr-1'") == 0
            # fail-closed before any side effect: no NEW audit row (503 raised pre-tx)
            assert await conn.fetchval(
                "SELECT count(*) FROM public.device_audit_log WHERE device_id='itest-corr-1'") == audit_before
    await _cleanup(db)
    await db.close()
