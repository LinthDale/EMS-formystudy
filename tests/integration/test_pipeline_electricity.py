"""Integration: end-to-end electricity data pipeline (sim-001 → MQTT → DB → REST)."""
import time

import pytest

from .conftest import wait_for

pytestmark = pytest.mark.integration


class TestPipelineDataFlow:
    def test_sim001_data_arrives_within_30s(self, db_conn):
        def has_data():
            with db_conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM electricity_measurements
                    WHERE device_id = 'sim-001'
                    AND time > NOW() - INTERVAL '30 seconds'
                """)
                return cur.fetchone()[0] > 0

        assert wait_for(has_data, timeout=30.0), (
            "No electricity data for sim-001 in last 30 seconds — "
            "check ems-gateway and ems-ingest containers"
        )

    def test_data_frequency_is_at_least_one_per_10s(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM electricity_measurements
                WHERE device_id = 'sim-001'
                AND time > NOW() - INTERVAL '1 minute'
            """)
            count = cur.fetchone()[0]
        assert count >= 6, f"Only {count} rows in last 60s; expected ≥6 (one per ≤10s)"


class TestDataPlausibility:
    def test_voltage_near_380v(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT AVG(voltage) FROM electricity_measurements
                WHERE device_id = 'sim-001'
                AND time > NOW() - INTERVAL '1 minute'
            """)
            avg_v = cur.fetchone()[0]
        assert avg_v is not None, "No voltage readings in last minute"
        assert 350.0 <= avg_v <= 420.0, f"Mean voltage {avg_v:.1f} V outside 350–420 V range"

    def test_current_positive(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT MIN(current) FROM electricity_measurements
                WHERE device_id = 'sim-001'
                AND time > NOW() - INTERVAL '2 minutes'
            """)
            min_i = cur.fetchone()[0]
        assert min_i is not None
        assert min_i >= 0.0, f"Negative current reading: {min_i} A"

    def test_power_kw_positive(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT MIN(power_kw) FROM electricity_measurements
                WHERE device_id = 'sim-001'
                AND time > NOW() - INTERVAL '2 minutes'
            """)
            min_p = cur.fetchone()[0]
        assert min_p is not None
        assert min_p >= 0.0, f"Negative power_kw: {min_p}"

    def test_energy_kwh_monotonically_increasing(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT energy_kwh FROM electricity_measurements
                WHERE device_id = 'sim-001'
                ORDER BY time ASC
                LIMIT 20
            """)
            values = [r[0] for r in cur.fetchall()]
        assert len(values) >= 2, "Not enough rows to verify monotonicity"
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1], (
                f"energy_kwh decreased at index {i}: {values[i-1]:.4f} → {values[i]:.4f}"
            )


class TestDataQuality:
    def test_no_null_voltage_in_recent_data(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM electricity_measurements
                WHERE device_id = 'sim-001' AND voltage IS NULL
                AND time > NOW() - INTERVAL '5 minutes'
            """)
            assert cur.fetchone()[0] == 0

    def test_no_null_power_in_recent_data(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM electricity_measurements
                WHERE device_id = 'sim-001' AND power_kw IS NULL
                AND time > NOW() - INTERVAL '5 minutes'
            """)
            assert cur.fetchone()[0] == 0

    def test_no_null_energy_in_recent_data(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM electricity_measurements
                WHERE device_id = 'sim-001' AND energy_kwh IS NULL
                AND time > NOW() - INTERVAL '5 minutes'
            """)
            assert cur.fetchone()[0] == 0


class TestFaultInjectionE2E:
    def test_fault_zero_reduces_power_to_near_zero(
        self, db_conn, simulator_client, reset_fault_mode
    ):
        simulator_client.post("/inject-fault", params={"mode": "zero"})
        time.sleep(15)  # wait for ≥2 ingest flush cycles (5s flush_interval)

        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT AVG(power_kw) FROM electricity_measurements
                WHERE device_id = 'sim-001'
                AND time > NOW() - INTERVAL '12 seconds'
            """)
            avg_power = cur.fetchone()[0]

        assert avg_power is not None, "No data during fault window"
        assert avg_power < 1.0, (
            f"power_kw = {avg_power:.2f} kW under fault=zero; expected < 1.0 kW"
        )

    def test_fault_recovery_restores_power(
        self, db_conn, simulator_client, reset_fault_mode
    ):
        simulator_client.post("/inject-fault", params={"mode": "zero"})
        time.sleep(10)
        simulator_client.post("/inject-fault", params={"mode": "none"})
        time.sleep(15)  # wait for normal readings to land

        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT AVG(power_kw) FROM electricity_measurements
                WHERE device_id = 'sim-001'
                AND time > NOW() - INTERVAL '12 seconds'
            """)
            avg_power = cur.fetchone()[0]

        assert avg_power is not None
        assert avg_power > 10.0, (
            f"power_kw = {avg_power:.2f} kW after fault cleared; expected > 10 kW"
        )
