"""Integration: GET /devices/{id}/human-review (PRD-0003 §8.4, Phase 1.4).

Read-only digest endpoint — never calls the LLM. Returns the stored
device_review_digests row (llm or system_fallback). Needs migrations 003-011
applied + roles with passwords, over the ems_default network.
"""
import json
import os

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

_OPS = {"X-API-Key": "ops-k"}
_AI = {"X-API-Key": "ai-k"}


async def _make_app():
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
        await conn.execute("DELETE FROM public.devices WHERE device_id LIKE 'itest-%'")


async def _seed_digest(db, device_id: str, digest: dict, summary_source: str):
    async with db.ops_pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO public.devices (device_id, status, classified_by)
               VALUES ($1, 'candidate', 'ai') ON CONFLICT (device_id) DO NOTHING""",
            device_id,
        )
        await conn.execute(
            """INSERT INTO public.device_review_digests
                   (device_id, digest, summary_source, provider, model, prompt_version)
               VALUES ($1, $2::jsonb, $3, 'mock', 'm', 'v1')
               ON CONFLICT (device_id) DO UPDATE SET
                   digest=EXCLUDED.digest, summary_source=EXCLUDED.summary_source""",
            device_id, json.dumps(digest), summary_source,
        )


@pytest.fixture
async def api():
    app, db = await _make_app()
    await _cleanup(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        yield client, db
    await _cleanup(db)
    await db.close()


async def test_human_review_returns_llm_digest(api):
    client, db = api
    digest = {
        "schema_version": "1.0", "device_id": "itest-hr-1",
        "summary_source": "llm", "ai_confidence": 0.42,
        "suggested_device_type": "electricity", "summary_zh": "測試摘要",
    }
    await _seed_digest(db, "itest-hr-1", digest, "llm")
    r = await client.get("/devices/itest-hr-1/human-review", headers=_OPS)
    assert r.status_code == 200
    body = r.json()
    assert body["summary_source"] == "llm"
    assert body["digest"]["suggested_device_type"] == "electricity"
    assert body["digest"]["ai_confidence"] == 0.42
    assert body["provider"] == "mock" and body["model"] == "m"


async def test_human_review_returns_fallback_digest_200(api):
    client, db = api
    digest = {
        "schema_version": "1.0", "device_id": "itest-hr-2",
        "summary_source": "system_fallback", "ai_confidence": 0.0,
        "suggested_device_type": "unknown", "why_low_confidence": "LLM 不可用，請人工判斷",
    }
    await _seed_digest(db, "itest-hr-2", digest, "system_fallback")
    r = await client.get("/devices/itest-hr-2/human-review", headers=_OPS)
    assert r.status_code == 200
    assert r.json()["summary_source"] == "system_fallback"
    assert r.json()["digest"]["why_low_confidence"]


async def test_human_review_404_missing_device(api):
    client, _ = api
    r = await client.get("/devices/itest-nope/human-review", headers=_OPS)
    assert r.status_code == 404
    assert "device not found" in r.json()["detail"]


async def test_human_review_404_device_without_digest(api):
    client, _ = api
    await client.post("/devices", json={"device_id": "itest-hr-nodigest"}, headers=_OPS)
    r = await client.get("/devices/itest-hr-nodigest/human-review", headers=_OPS)
    assert r.status_code == 404
    assert "digest" in r.json()["detail"].lower()


async def test_digest_repo_get_digest_only(api):
    """digest_repo.get() is the digest-only accessor (no device existence check) reused
    by the future MCP get_device_digest tool. Returns the shaped dict, or None if absent."""
    from device_service.repositories import digest_repo
    _, db = api
    await _seed_digest(db, "itest-hr-repo", {"device_id": "itest-hr-repo", "k": 1}, "llm")
    async with db.ops_pool.acquire() as conn:
        rec = await digest_repo.get(conn, "itest-hr-repo")
        assert rec is not None and rec["digest"]["k"] == 1 and rec["summary_source"] == "llm"
        assert await digest_repo.get(conn, "itest-hr-absent") is None


async def test_human_review_requires_ops_channel(api):
    client, db = api
    await _seed_digest(db, "itest-hr-3", {"device_id": "itest-hr-3"}, "llm")
    # no key -> 401
    assert (await client.get("/devices/itest-hr-3/human-review")).status_code == 401
    # AI channel -> 403 (human review is an OPS read; AI uses MCP get_device_digest)
    assert (await client.get("/devices/itest-hr-3/human-review", headers=_AI)).status_code == 403
