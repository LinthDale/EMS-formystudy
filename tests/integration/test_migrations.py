"""Integration: verify migration scripts are idempotent and produce correct schema."""
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "infra" / "timescaledb" / "migrations"


def _run_sql_file(db_conn, filename: str):
    sql = (_MIGRATIONS_DIR / filename).read_text()
    with db_conn.cursor() as cur:
        cur.execute(sql)


class TestMigration000RenameIdempotency:
    """000_rename_measurements.sql must be safe to run on an already-migrated DB."""

    def test_run_twice_does_not_raise(self, db_conn):
        _run_sql_file(db_conn, "000_rename_measurements.sql")
        _run_sql_file(db_conn, "000_rename_measurements.sql")  # second run must not fail

    def test_electricity_measurements_exists_after_migration(self, db_conn):
        _run_sql_file(db_conn, "000_rename_measurements.sql")
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'electricity_measurements'
            """)
            assert cur.fetchone() is not None

    def test_old_measurements_table_absent_after_migration(self, db_conn):
        _run_sql_file(db_conn, "000_rename_measurements.sql")
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'measurements'
            """)
            assert cur.fetchone() is None


class TestMigration001AddFactoryIdempotency:
    """001_add_factory.sql must be safe to run on a DB that already has factory_measurements."""

    def test_run_twice_does_not_raise(self, db_conn):
        _run_sql_file(db_conn, "001_add_factory.sql")
        _run_sql_file(db_conn, "001_add_factory.sql")  # second run must not fail

    def test_factory_measurements_exists_after_migration(self, db_conn):
        _run_sql_file(db_conn, "001_add_factory.sql")
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'factory_measurements'
            """)
            assert cur.fetchone() is not None

    def test_factory_view_exists_after_migration(self, db_conn):
        _run_sql_file(db_conn, "001_add_factory.sql")
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.views
                WHERE table_schema = 'api' AND table_name = 'factory_measurements'
            """)
            assert cur.fetchone() is not None

    def test_factory_table_is_hypertable_after_migration(self, db_conn):
        _run_sql_file(db_conn, "001_add_factory.sql")
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM timescaledb_information.hypertables
                WHERE hypertable_name = 'factory_measurements'
            """)
            assert cur.fetchone()[0] == 1
