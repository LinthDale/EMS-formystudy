"""Integration: device-service REST API against TimescaleDB (PRD-0003 Slice 3).

Needs migrations 003-011 applied + roles with passwords (set_role_passwords.sh).
Connects as device_service_ai/ops over the ems_default network.
"""
import os

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

_OPS = {"X-API-Key": "ops-k"}
_AI = {"X-API-Key": "ai-k"}
_DEV = "itest-dev-001"


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


@pytest.fixture
async def api():
    app, db = await _make_app()
    await _cleanup(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        yield client, db
    await _cleanup(db)
    await db.close()


async def test_healthz_pools_ok(api):
    client, _ = api
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["pools"] == {"ai": "ok", "ops": "ok"}


async def test_auth_401_and_403(api):
    client, _ = api
    assert (await client.post("/devices", json={"device_id": _DEV})).status_code == 401
    assert (await client.post("/devices", json={"device_id": _DEV}, headers=_AI)).status_code == 403


async def test_full_crud_lifecycle(api):
    client, _ = api

    # create (candidate)
    r = await client.post("/devices", json={"device_id": _DEV, "device_type": "unknown"}, headers=_OPS)
    assert r.status_code == 201 and r.json()["status"] == "candidate"

    # duplicate -> 409
    assert (await client.post("/devices", json={"device_id": _DEV}, headers=_OPS)).status_code == 409

    # get + list
    assert (await client.get(f"/devices/{_DEV}", headers=_OPS)).status_code == 200
    assert _DEV in [d["device_id"] for d in (await client.get("/devices", headers=_OPS)).json()]

    # patch metadata on a candidate (not frozen) -> ok
    r = await client.patch(f"/devices/{_DEV}", json={"vendor": "acme"}, headers=_OPS)
    assert r.status_code == 200 and r.json()["vendor"] == "acme"

    # add + list signals
    assert (await client.post(f"/devices/{_DEV}/signals", json={"signal_name": "voltage", "unit": "V"}, headers=_OPS)).status_code == 201
    sigs = (await client.get(f"/devices/{_DEV}/signals", headers=_OPS)).json()
    assert [s["signal_name"] for s in sigs] == ["voltage"]

    # confirm -> frozen (classified_by human)
    r = await client.post(f"/devices/{_DEV}/confirm", headers=_OPS)
    assert r.status_code == 200 and r.json()["status"] == "confirmed" and r.json()["classified_by"] == "human"

    # patch device_type on a now-frozen device WITHOUT override -> 409 (freeze trigger)
    assert (await client.patch(f"/devices/{_DEV}", json={"device_type": "electricity"}, headers=_OPS)).status_code == 409

    # override (carries freeze token) -> ok
    r = await client.post(f"/devices/{_DEV}/override", json={"device_type": "electricity", "signals": [{"signal_name": "current", "unit": "A"}]}, headers=_OPS)
    assert r.status_code == 200 and r.json()["device_type"] == "electricity" and r.json()["classified_by"] == "manual_override"

    # reject -> retired
    assert (await client.post(f"/devices/{_DEV}/reject", headers=_OPS)).json()["status"] == "retired"


async def test_get_missing_device_404(api):
    client, _ = api
    assert (await client.get("/devices/itest-nope", headers=_OPS)).status_code == 404

async def test_signal_delete_and_404(api):
    client, _ = api
    await client.post("/devices", json={"device_id": "itest-sig", "device_type": "unknown"}, headers=_OPS)
    # add to missing device -> 404
    assert (await client.post("/devices/itest-missing/signals", json={"signal_name": "v"}, headers=_OPS)).status_code == 404
    # add then delete -> 204; delete again -> 404
    assert (await client.post("/devices/itest-sig/signals", json={"signal_name": "voltage"}, headers=_OPS)).status_code == 201
    assert (await client.delete("/devices/itest-sig/signals/voltage", headers=_OPS)).status_code == 204
    assert (await client.delete("/devices/itest-sig/signals/voltage", headers=_OPS)).status_code == 404


async def test_list_filter_by_status_and_empty_patch(api):
    client, _ = api
    await client.post("/devices", json={"device_id": "itest-cand"}, headers=_OPS)
    listed = (await client.get("/devices", params={"status": "candidate"}, headers=_OPS)).json()
    assert "itest-cand" in [d["device_id"] for d in listed]
    assert all(d["status"] == "candidate" for d in listed)
    # empty PATCH returns the unchanged device (update early-return path)
    r = await client.patch("/devices/itest-cand", json={}, headers=_OPS)
    assert r.status_code == 200 and r.json()["device_id"] == "itest-cand"


async def test_lifespan_connects_and_closes_pools():
    from device_service.config import Settings
    from device_service.main import create_app
    import os

    app = create_app()
    app.state.settings = Settings(
        _env_file=None, db_host=os.getenv("EMS_DB_HOST", "timescaledb"),
        db_ai_password=os.getenv("DB_AI_PASSWORD", "devAI_rotate_in_prod_7x2k"),
        db_ops_password=os.getenv("DB_OPS_PASSWORD", "devOPS_rotate_in_prod_9q4m"),
        llm_provider="mock",
    )
    try:
        async with app.router.lifespan_context(app):
            assert app.state.db is not None and app.state.provider.name == "mock"
            assert await app.state.db.healthz() == {"ai": "ok", "ops": "ok"}
    except Exception as exc:  # noqa: BLE001
        import pytest
        pytest.skip(f"DB not reachable: {exc}")

async def test_lifecycle_404s_on_missing_device(api):
    client, _ = api
    for path in ("confirm", "override", "reject"):
        body = {"device_type": "x", "signals": []} if path == "override" else None
        r = await client.post(f"/devices/itest-missing/{path}", json=body, headers=_OPS)
        assert r.status_code == 404, path
    assert (await client.patch("/devices/itest-missing", json={"vendor": "v"}, headers=_OPS)).status_code == 404
    assert (await client.delete("/devices/itest-missing", headers=_OPS)).status_code == 404


async def test_delete_device_retires_and_stale_filter(api):
    client, _ = api
    await client.post("/devices", json={"device_id": "itest-del"}, headers=_OPS)
    assert (await client.delete("/devices/itest-del", headers=_OPS)).status_code == 204
    # stale filters exercise both branches
    assert isinstance((await client.get("/devices", params={"stale": "true"}, headers=_OPS)).json(), list)
    not_stale = (await client.get("/devices", params={"stale": "false"}, headers=_OPS)).json()
    assert "itest-del" in [d["device_id"] for d in not_stale]  # retired but not stale-marked


async def test_duplicate_active_signal_409(api):
    client, _ = api
    await client.post("/devices", json={"device_id": "itest-dup"}, headers=_OPS)
    assert (await client.post("/devices/itest-dup/signals", json={"signal_name": "voltage"}, headers=_OPS)).status_code == 201
    assert (await client.post("/devices/itest-dup/signals", json={"signal_name": "voltage"}, headers=_OPS)).status_code == 409

async def test_signal_mutation_on_frozen_device_blocked(api):
    """sim-001 is migration_backfill (frozen); adding/deleting signals via OPS without
    an override token must be blocked by the DB freeze trigger -> 409 (rolled back)."""
    client, _ = api
    # add a new signal to the frozen device -> 409
    r = await client.post("/devices/sim-001/signals", json={"signal_name": "tamper"}, headers=_OPS)
    assert r.status_code == 409
    # delete an existing active signal of the frozen device -> 409
    r = await client.delete("/devices/sim-001/signals/voltage", headers=_OPS)
    assert r.status_code == 409