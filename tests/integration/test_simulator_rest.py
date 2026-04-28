"""Integration: EMS simulator REST API against running container (port 8001)."""
import pytest

pytestmark = pytest.mark.integration


class TestHealth:
    def test_returns_200(self, simulator_client):
        assert simulator_client.get("/health").status_code == 200

    def test_status_is_ok(self, simulator_client):
        assert simulator_client.get("/health").json() == {"status": "ok"}


class TestGetConfig:
    def test_all_fields_present(self, simulator_client):
        data = simulator_client.get("/config").json()
        for field in (
            "noise_voltage_v", "current_base_a", "current_swing_a",
            "noise_current_a", "power_factor", "period_seconds", "fault_mode",
        ):
            assert field in data, f"Missing field: {field}"

    def test_power_factor_is_float(self, simulator_client):
        data = simulator_client.get("/config").json()
        assert isinstance(data["power_factor"], float)


class TestSetConfig:
    def test_update_field_and_restore(self, simulator_client):
        original = simulator_client.get("/config").json()["noise_voltage_v"]
        new_val = round(original + 1.0, 2)
        resp = simulator_client.post("/config", params={"noise_voltage_v": new_val})
        assert resp.json()["noise_voltage_v"] == new_val
        simulator_client.post("/config", params={"noise_voltage_v": original})

    def test_response_echoes_updated_value(self, simulator_client):
        resp = simulator_client.post("/config", params={"period_seconds": 7200.0})
        assert resp.json()["period_seconds"] == 7200.0
        simulator_client.post("/config", params={"period_seconds": 3600.0})


class TestFaultInjection:
    def test_zero_mode(self, simulator_client, reset_fault_mode):
        resp = simulator_client.post("/inject-fault", params={"mode": "zero"})
        assert resp.json()["fault_mode"] == "zero"

    def test_freeze_mode(self, simulator_client, reset_fault_mode):
        resp = simulator_client.post("/inject-fault", params={"mode": "freeze"})
        assert resp.json()["fault_mode"] == "freeze"

    def test_none_clears_fault(self, simulator_client):
        simulator_client.post("/inject-fault", params={"mode": "zero"})
        resp = simulator_client.post("/inject-fault", params={"mode": "none"})
        assert resp.json()["fault_mode"] == "none"

    def test_invalid_mode_returns_error_key(self, simulator_client):
        resp = simulator_client.post("/inject-fault", params={"mode": "invalid"})
        assert "error" in resp.json()

    def test_fault_mode_visible_in_config(self, simulator_client, reset_fault_mode):
        simulator_client.post("/inject-fault", params={"mode": "freeze"})
        assert simulator_client.get("/config").json()["fault_mode"] == "freeze"
