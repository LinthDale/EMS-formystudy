"""Integration: verify TimescaleDB schema matches expected design."""
import pytest

pytestmark = pytest.mark.integration


class TestElectricityMeasurementsTable:
    def test_table_exists(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'electricity_measurements'
                )
            """)
            assert cur.fetchone()[0] is True

    def test_old_measurements_table_is_gone(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'measurements'
                )
            """)
            assert cur.fetchone()[0] is False, (
                "Old 'measurements' table still exists — run migration 000"
            )

    def test_required_columns_present(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = 'electricity_measurements'
            """)
            cols = {r[0] for r in cur.fetchall()}
        assert {"time", "device_id", "voltage", "current", "power_kw", "energy_kwh"} <= cols

    def test_time_is_timestamptz(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT data_type FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = 'electricity_measurements'
                AND column_name = 'time'
            """)
            assert cur.fetchone()[0] == "timestamp with time zone"

    def test_is_hypertable(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM timescaledb_information.hypertables
                WHERE hypertable_name = 'electricity_measurements'
            """)
            assert cur.fetchone()[0] == 1

    def test_device_time_index_exists(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM pg_indexes
                WHERE tablename = 'electricity_measurements'
                AND indexname = 'idx_electricity_device_time'
            """)
            assert cur.fetchone()[0] == 1


class TestFactoryMeasurementsTable:
    def test_table_exists(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'factory_measurements'
                )
            """)
            assert cur.fetchone()[0] is True

    def test_required_columns_present(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = 'factory_measurements'
            """)
            cols = {r[0] for r in cur.fetchall()}
        required = {
            "time", "device_id", "device_type",
            "temperature", "humidity", "motor_speed",
            "pump_on", "valve_open", "pressure",
        }
        assert required <= cols

    def test_pump_on_is_boolean_type(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT data_type FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = 'factory_measurements'
                AND column_name = 'pump_on'
            """)
            assert cur.fetchone()[0] == "boolean"

    def test_valve_open_is_boolean_type(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT data_type FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = 'factory_measurements'
                AND column_name = 'valve_open'
            """)
            assert cur.fetchone()[0] == "boolean"

    def test_is_hypertable(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM timescaledb_information.hypertables
                WHERE hypertable_name = 'factory_measurements'
            """)
            assert cur.fetchone()[0] == 1

    def test_device_time_index_exists(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM pg_indexes
                WHERE tablename = 'factory_measurements'
                AND indexname = 'idx_factory_device_time'
            """)
            assert cur.fetchone()[0] == 1


class TestApiSchema:
    def test_api_schema_exists(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.schemata
                    WHERE schema_name = 'api'
                )
            """)
            assert cur.fetchone()[0] is True

    def test_electricity_view_exists(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.views
                    WHERE table_schema = 'api'
                    AND table_name = 'electricity_measurements'
                )
            """)
            assert cur.fetchone()[0] is True

    def test_factory_view_exists(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.views
                    WHERE table_schema = 'api'
                    AND table_name = 'factory_measurements'
                )
            """)
            assert cur.fetchone()[0] is True

    def test_web_anon_can_select_electricity_view(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT has_table_privilege('web_anon', 'api.electricity_measurements', 'SELECT')"
            )
            assert cur.fetchone()[0] is True

    def test_web_anon_cannot_insert_electricity_view(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT has_table_privilege('web_anon', 'api.electricity_measurements', 'INSERT')"
            )
            assert cur.fetchone()[0] is False

    def test_web_anon_can_select_factory_view(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT has_table_privilege('web_anon', 'api.factory_measurements', 'SELECT')"
            )
            assert cur.fetchone()[0] is True

    def test_web_anon_cannot_insert_factory_view(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT has_table_privilege('web_anon', 'api.factory_measurements', 'INSERT')"
            )
            assert cur.fetchone()[0] is False


class TestDataInsertAndQuery:
    """Verify basic write/read cycle works for both tables."""

    _ELEC_DEVICE = "test-unit-elec"
    _FACT_DEVICE = "test-unit-fact"

    def test_electricity_insert_and_read(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                INSERT INTO public.electricity_measurements
                    (time, device_id, voltage, current, power_kw, energy_kwh)
                VALUES (NOW(), %s, 380.0, 100.0, 55.9, 1.0)
            """, (self._ELEC_DEVICE,))
            cur.execute("""
                SELECT voltage, current FROM public.electricity_measurements
                WHERE device_id = %s ORDER BY time DESC LIMIT 1
            """, (self._ELEC_DEVICE,))
            row = cur.fetchone()
        assert row is not None
        assert abs(row[0] - 380.0) < 0.01
        assert abs(row[1] - 100.0) < 0.01

    def test_electricity_cleanup(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute(
                "DELETE FROM public.electricity_measurements WHERE device_id = %s",
                (self._ELEC_DEVICE,),
            )
            cur.execute(
                "SELECT COUNT(*) FROM public.electricity_measurements WHERE device_id = %s",
                (self._ELEC_DEVICE,),
            )
            assert cur.fetchone()[0] == 0

    def test_factory_insert_and_read(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute("""
                INSERT INTO public.factory_measurements
                    (time, device_id, device_type, temperature, humidity, pressure, pump_on, valve_open)
                VALUES (NOW(), %s, 'plc', 25.3, 55.2, 1013.0, true, false)
            """, (self._FACT_DEVICE,))
            cur.execute("""
                SELECT temperature, pump_on, valve_open FROM public.factory_measurements
                WHERE device_id = %s ORDER BY time DESC LIMIT 1
            """, (self._FACT_DEVICE,))
            row = cur.fetchone()
        assert row is not None
        assert abs(row[0] - 25.3) < 0.01
        assert row[1] is True
        assert row[2] is False

    def test_factory_cleanup(self, db_conn):
        with db_conn.cursor() as cur:
            cur.execute(
                "DELETE FROM public.factory_measurements WHERE device_id = %s",
                (self._FACT_DEVICE,),
            )
            cur.execute(
                "SELECT COUNT(*) FROM public.factory_measurements WHERE device_id = %s",
                (self._FACT_DEVICE,),
            )
            assert cur.fetchone()[0] == 0
