"""Unit: /healthz degraded path + Database.healthz down branch (no real DB)."""
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from device_service.db import Database


class _FakeDB:
    def __init__(self, pools):
        self._pools = pools

    async def healthz(self):
        return self._pools


def _app(pools):
    app = FastAPI()
    app.state.db = _FakeDB(pools)
    from device_service.routes import health
    app.include_router(health.router)
    return app


async def test_healthz_degraded_returns_503():
    app = _app({"ai": "ok", "ops": "down"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/healthz")
    assert r.status_code == 503 and r.json()["status"] == "degraded"


async def test_database_healthz_marks_pool_down_on_error():
    class _BadPool:
        def acquire(self):
            raise RuntimeError("pool exhausted")

    db = Database(host="x", port=1, name="ems", ai_password="", ops_password="")
    db.ai_pool = _BadPool()
    db.ops_pool = _BadPool()
    assert await db.healthz() == {"ai": "down", "ops": "down"}

async def test_database_healthz_none_pool_is_starting():
    db = Database(host="x", port=1, name="ems", ai_password="", ops_password="")
    assert await db.healthz() == {"ai": "starting", "ops": "starting"}


async def test_db_error_handler_maps_status_codes():
    import asyncpg

    from device_service.main import db_error_handler

    assert (await db_error_handler(None, asyncpg.UniqueViolationError("dup"))).status_code == 409
    assert (await db_error_handler(None, asyncpg.CheckViolationError("bad"))).status_code == 422
    assert (await db_error_handler(None, asyncpg.PostgresError("other"))).status_code == 500