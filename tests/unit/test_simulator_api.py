"""Unit tests for FastAPI endpoints — use ASGI transport, no Docker required."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import main


@pytest.fixture(autouse=True)
def _reset_config():
    """Restore global SimConfig state after each test."""
    saved = {k: getattr(main.config, k) for k in vars(main.config)}
    yield
    for k, v in saved.items():
        setattr(main.config, k, v)


@pytest.fixture
def _mock_modbus():
    """Prevent real Modbus server from binding a port during tests."""
    with patch("main.StartAsyncTcpServer", new_callable=AsyncMock):
        yield


@pytest.fixture
async def client(_mock_modbus):
    async with AsyncClient(
        transport=ASGITransport(app=main.app), base_url="http://test"
    ) as ac:
        yield ac


# ── /health ──────────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    async def test_returns_200(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_body_is_ok(self, client):
        assert (await client.get("/health")).json() == {"status": "ok"}


# ── GET /config ───────────────────────────────────────────────────────────────

class TestGetConfig:
    async def test_returns_200(self, client):
        assert (await client.get("/config")).status_code == 200

    async def test_contains_all_seven_fields(self, client):
        data = (await client.get("/config")).json()
        expected = {
            "noise_voltage_v", "current_base_a", "current_swing_a",
            "noise_current_a", "power_factor", "period_seconds", "fault_mode",
        }
        assert set(data.keys()) == expected

    async def test_default_power_factor(self, client):
        assert (await client.get("/config")).json()["power_factor"] == 0.85

    async def test_default_fault_mode_is_none(self, client):
        assert (await client.get("/config")).json()["fault_mode"] == "none"


# ── POST /config ──────────────────────────────────────────────────────────────

class TestSetConfig:
    async def test_update_single_field(self, client):
        resp = await client.post("/config", params={"noise_voltage_v": 9.0})
        assert resp.status_code == 200
        assert resp.json()["noise_voltage_v"] == 9.0

    async def test_unspecified_fields_unchanged(self, client):
        before = (await client.get("/config")).json()["current_base_a"]
        await client.post("/config", params={"noise_voltage_v": 9.0})
        after = (await client.get("/config")).json()["current_base_a"]
        assert after == before

    async def test_update_multiple_fields_in_one_call(self, client):
        resp = await client.post(
            "/config",
            params={"current_base_a": 150.0, "power_factor": 0.95},
        )
        data = resp.json()
        assert data["current_base_a"] == 150.0
        assert data["power_factor"] == 0.95

    async def test_updated_value_persists_across_get(self, client):
        await client.post("/config", params={"current_swing_a": 99.0})
        assert (await client.get("/config")).json()["current_swing_a"] == 99.0

    async def test_response_echoes_full_config(self, client):
        resp = await client.post("/config", params={"noise_voltage_v": 5.0})
        keys = resp.json().keys()
        for field in ("noise_voltage_v", "current_base_a", "fault_mode"):
            assert field in keys


# ── POST /inject-fault ────────────────────────────────────────────────────────

class TestInjectFault:
    async def test_mode_zero(self, client):
        resp = await client.post("/inject-fault", params={"mode": "zero"})
        assert resp.status_code == 200
        assert resp.json() == {"fault_mode": "zero"}

    async def test_mode_freeze(self, client):
        resp = await client.post("/inject-fault", params={"mode": "freeze"})
        assert resp.json() == {"fault_mode": "freeze"}

    async def test_mode_none_clears_fault(self, client):
        await client.post("/inject-fault", params={"mode": "zero"})
        resp = await client.post("/inject-fault", params={"mode": "none"})
        assert resp.json() == {"fault_mode": "none"}

    async def test_fault_mode_reflected_in_get_config(self, client):
        await client.post("/inject-fault", params={"mode": "freeze"})
        cfg = (await client.get("/config")).json()
        assert cfg["fault_mode"] == "freeze"

    async def test_invalid_mode_returns_error_key(self, client):
        resp = await client.post("/inject-fault", params={"mode": "explosion"})
        # BUG: current impl returns HTTP 200 with {"error": "..."} instead of 4xx.
        # Test documents actual behaviour; fix would be to raise HTTPException(400).
        assert "error" in resp.json()

    async def test_invalid_mode_does_not_change_fault_mode(self, client):
        await client.post("/inject-fault", params={"mode": "zero"})
        await client.post("/inject-fault", params={"mode": "bad"})
        cfg = (await client.get("/config")).json()
        assert cfg["fault_mode"] == "zero"  # unchanged after invalid attempt
