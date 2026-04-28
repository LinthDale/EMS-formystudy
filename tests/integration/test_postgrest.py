"""Integration: PostgREST API contract tests (port 3001)."""
import pytest

pytestmark = pytest.mark.integration


class TestElectricityEndpoint:
    def test_returns_200(self, postgrest_client):
        assert postgrest_client.get("/electricity_measurements").status_code == 200

    def test_response_is_json_array(self, postgrest_client):
        assert isinstance(postgrest_client.get("/electricity_measurements").json(), list)

    def test_limit_parameter_honoured(self, postgrest_client):
        rows = postgrest_client.get(
            "/electricity_measurements", params={"limit": 3}
        ).json()
        assert len(rows) <= 3

    def test_order_desc_by_time(self, postgrest_client):
        rows = postgrest_client.get(
            "/electricity_measurements",
            params={"order": "time.desc", "limit": 10},
        ).json()
        if len(rows) >= 2:
            assert rows[0]["time"] >= rows[1]["time"]

    def test_device_id_filter(self, postgrest_client):
        rows = postgrest_client.get(
            "/electricity_measurements",
            params={"device_id": "eq.sim-001", "limit": 5},
        ).json()
        assert all(r["device_id"] == "sim-001" for r in rows)

    def test_response_has_expected_fields(self, postgrest_client):
        rows = postgrest_client.get(
            "/electricity_measurements",
            params={"order": "time.desc", "limit": 1},
        ).json()
        if rows:
            row = rows[0]
            for field in ("time", "device_id", "voltage", "current", "power_kw", "energy_kwh"):
                assert field in row, f"Missing field '{field}' in response"

    def test_unknown_table_returns_error(self, postgrest_client):
        resp = postgrest_client.get("/nonexistent_table_xyz")
        assert resp.status_code in (400, 404)


class TestFactoryEndpoint:
    def test_returns_200(self, postgrest_client):
        assert postgrest_client.get("/factory_measurements").status_code == 200

    def test_response_is_json_array(self, postgrest_client):
        assert isinstance(postgrest_client.get("/factory_measurements").json(), list)

    def test_filter_by_device_type_plc(self, postgrest_client):
        rows = postgrest_client.get(
            "/factory_measurements",
            params={"device_type": "eq.plc", "limit": 5},
        ).json()
        assert all(r["device_type"] == "plc" for r in rows)

    def test_filter_by_device_type_sensor(self, postgrest_client):
        rows = postgrest_client.get(
            "/factory_measurements",
            params={"device_type": "eq.sensor", "limit": 5},
        ).json()
        assert all(r["device_type"] == "sensor" for r in rows)

    def test_filter_by_plc_device_id(self, postgrest_client):
        rows = postgrest_client.get(
            "/factory_measurements",
            params={"device_id": "eq.plc-001", "limit": 3},
        ).json()
        assert all(r["device_id"] == "plc-001" for r in rows)

    def test_response_has_factory_fields(self, postgrest_client):
        rows = postgrest_client.get(
            "/factory_measurements",
            params={"order": "time.desc", "limit": 1},
        ).json()
        if rows:
            row = rows[0]
            for field in ("time", "device_id", "device_type"):
                assert field in row

    def test_no_electricity_fields_in_factory_response(self, postgrest_client):
        rows = postgrest_client.get(
            "/factory_measurements",
            params={"device_id": "eq.plc-001", "limit": 1},
        ).json()
        if rows:
            row = rows[0]
            assert "voltage" not in row
            assert "energy_kwh" not in row


class TestPostgRESTSecurity:
    def test_insert_rejected_by_web_anon(self, postgrest_client):
        resp = postgrest_client.post(
            "/electricity_measurements",
            json={"time": "2026-01-01T00:00:00Z", "device_id": "hacker", "voltage": 999},
        )
        assert resp.status_code in (401, 403, 405)

    def test_delete_rejected_by_web_anon(self, postgrest_client):
        resp = postgrest_client.delete(
            "/electricity_measurements",
            params={"device_id": "eq.sim-001"},
        )
        assert resp.status_code in (401, 403, 405)
