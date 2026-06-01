"""Unit: X-API-Key three-channel auth (FR-310)."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from device_service.auth import Channel, require, resolve_channel

_SETTINGS = SimpleNamespace(ops_api_key="ops-k", ingest_api_key="ing-k", ai_api_key="ai-k")


def test_resolve_channel_matches_each_key():
    assert resolve_channel("ops-k", _SETTINGS) is Channel.OPS
    assert resolve_channel("ing-k", _SETTINGS) is Channel.INGEST
    assert resolve_channel("ai-k", _SETTINGS) is Channel.AI


def test_resolve_channel_unknown_and_empty():
    assert resolve_channel("nope", _SETTINGS) is None
    assert resolve_channel(None, _SETTINGS) is None


def test_blank_configured_key_never_matches():
    s = SimpleNamespace(ops_api_key="", ingest_api_key="ing-k", ai_api_key="ai-k")
    assert resolve_channel("", s) is None


def _app():
    app = FastAPI()
    app.state.settings = _SETTINGS

    @app.get("/ops-only", dependencies=[require(Channel.OPS)])
    async def _ops():
        return {"ok": True}

    return app


async def _call(headers):
    app = _app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        return await c.get("/ops-only", headers=headers)


async def test_missing_key_401():
    assert (await _call({})).status_code == 401


async def test_wrong_channel_403():
    assert (await _call({"X-API-Key": "ai-k"})).status_code == 403


async def test_correct_channel_200():
    assert (await _call({"X-API-Key": "ops-k"})).status_code == 200