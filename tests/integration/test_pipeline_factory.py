"""Integration: factory pipeline — PLC Modbus writes and MQTT sensor → DB."""
import time

import pytest

from .conftest import wait_for

pytestmark = pytest.mark.integration

# kc_modbus_mcp simulator ranges (from simulator.py):
# temperature:  25 + 5 * sin(elapsed * 0.1)  → 20..30 °C
# humidity:     50 + 10*sin + noise[-2,2]     → ~40..60 %RH
# pressure:     1000 + 100*sin + rand[-20,20] → 880..1120 kPa


class TestPLCPipelineFlow:
    def test_plc001_data_arrives_within_30s(self, db_conn):
        def has_data():
            with db_conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM factory_measurements
                    WHERE device_id = 'plc-001'
                    AND time > NOW() - INTERVAL '30 seconds'
                """)
                return cur.fetchone()[0] > 0

        assert wait_for(has_data, timeout=30.0), (
            "No factory PLC data for plc-001 in last 30 seconds — "
            "check ems-kc-gateway and ems-kc-ingest containers"
        )

    def test_plc_device_type_is_plc(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT device_type FROM factory_measurements
                WHERE device_id = 'plc-001'
            """)
            types = {r[0] for r in cur.fetchall()}
        assert "plc" in types


class TestPLCDataRanges:
    def test_temperature_in_20_to_30_range(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT AVG(temperature) FROM factory_measurements
                WHERE device_id = 'plc-001'
                AND time > NOW() - INTERVAL '1 minute'
            """)
            avg = cur.fetchone()[0]
        assert avg is not None, "No temperature readings"
        assert 15.0 <= avg <= 35.0, f"Temperature avg {avg:.1f}°C outside expected 15–35°C"

    def test_humidity_in_35_to_65_range(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT AVG(humidity) FROM factory_measurements
                WHERE device_id = 'plc-001'
                AND time > NOW() - INTERVAL '1 minute'
            """)
            avg = cur.fetchone()[0]
        assert avg is not None, "No humidity readings"
        assert 35.0 <= avg <= 65.0, f"Humidity avg {avg:.1f}% outside expected 35–65%"

    def test_pressure_in_860_to_1140_range(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT AVG(pressure) FROM factory_measurements
                WHERE device_id = 'plc-001'
                AND time > NOW() - INTERVAL '1 minute'
            """)
            avg = cur.fetchone()[0]
        assert avg is not None, "No pressure readings"
        assert 860.0 <= avg <= 1140.0, f"Pressure avg {avg:.1f} kPa outside expected range"

    def test_no_null_temperature(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM factory_measurements
                WHERE device_id = 'plc-001' AND temperature IS NULL
                AND time > NOW() - INTERVAL '5 minutes'
            """)
            assert cur.fetchone()[0] == 0


class TestModbusWritePropagation:
    """Write Modbus registers → verify values appear in TimescaleDB within 15 seconds."""

    def test_motor_speed_write(self, db_conn, plc_client):
        plc_client.write_register(4, 1500, slave=1)
        time.sleep(15)

        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT motor_speed FROM factory_measurements
                WHERE device_id = 'plc-001'
                ORDER BY time DESC LIMIT 1
            """)
            row = cur.fetchone()
        assert row is not None
        assert abs(row[0] - 1500.0) < 50.0, f"motor_speed = {row[0]}, expected ~1500 RPM"

        plc_client.write_register(4, 0, slave=1)  # restore

    def test_pump_on_write_true(self, db_conn, plc_client):
        plc_client.write_coil(0, True, slave=1)
        time.sleep(15)

        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT pump_on FROM factory_measurements
                WHERE device_id = 'plc-001'
                ORDER BY time DESC LIMIT 1
            """)
            row = cur.fetchone()
        assert row is not None
        assert row[0] is True, f"pump_on = {row[0]}, expected True"

        plc_client.write_coil(0, False, slave=1)

    def test_valve_open_write_true(self, db_conn, plc_client):
        plc_client.write_coil(1, True, slave=1)
        time.sleep(15)

        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT valve_open FROM factory_measurements
                WHERE device_id = 'plc-001'
                ORDER BY time DESC LIMIT 1
            """)
            row = cur.fetchone()
        assert row is not None
        assert row[0] is True, f"valve_open = {row[0]}, expected True"

        plc_client.write_coil(1, False, slave=1)

    def test_pump_and_valve_independent(self, db_conn, plc_client):
        """Writing one coil must not affect the other."""
        plc_client.write_coil(0, True, slave=1)   # pump_on = True
        plc_client.write_coil(1, False, slave=1)  # valve_open = False
        time.sleep(15)

        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT pump_on, valve_open FROM factory_measurements
                WHERE device_id = 'plc-001'
                ORDER BY time DESC LIMIT 1
            """)
            row = cur.fetchone()
        assert row[0] is True, "pump_on should be True"
        assert row[1] is False, "valve_open should be False (independent coil)"

        plc_client.write_coil(0, False, slave=1)


class TestMQTTSensorPipeline:
    def test_sensor001_arrives_within_60s(self, db_conn):
        def has_data():
            with db_conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM factory_measurements
                    WHERE device_id = 'sensor-001'
                    AND time > NOW() - INTERVAL '60 seconds'
                """)
                return cur.fetchone()[0] > 0

        assert wait_for(has_data, timeout=60.0), (
            "No MQTT sensor data for sensor-001 in last 60 seconds — "
            "check ems-kc-mqtt-sim and ems-kc-ingest containers"
        )

    def test_sensor_device_type_is_sensor(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT device_type FROM factory_measurements
                WHERE device_id = 'sensor-001'
            """)
            types = {r[0] for r in cur.fetchall()}
        assert "sensor" in types

    def test_sensor_has_temperature_and_humidity(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT temperature, humidity FROM factory_measurements
                WHERE device_id = 'sensor-001'
                ORDER BY time DESC LIMIT 1
            """)
            row = cur.fetchone()
        assert row is not None
        assert row[0] is not None, "temperature is NULL for sensor-001"
        assert row[1] is not None, "humidity is NULL for sensor-001"

    def test_sensor_pressure_is_null(self, db_conn):
        """JSON MQTT sensor does not publish pressure — must remain NULL."""
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT pressure FROM factory_measurements
                WHERE device_id = 'sensor-001'
                ORDER BY time DESC LIMIT 1
            """)
            row = cur.fetchone()
        if row:
            assert row[0] is None, (
                f"sensor-001 pressure should be NULL, got {row[0]}"
            )

    def test_sensor_motor_speed_is_null(self, db_conn):
        """JSON MQTT sensor does not publish motor_speed — must remain NULL."""
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT motor_speed FROM factory_measurements
                WHERE device_id = 'sensor-001'
                ORDER BY time DESC LIMIT 1
            """)
            row = cur.fetchone()
        if row:
            assert row[0] is None, (
                f"sensor-001 motor_speed should be NULL, got {row[0]}"
            )
