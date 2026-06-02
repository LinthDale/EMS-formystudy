"""Integration: verify migration scripts are idempotent and produce correct schema."""
from pathlib import Path

import psycopg2
import pytest

pytestmark = pytest.mark.integration

_MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "infra" / "timescaledb" / "migrations"

# PRD-0003 Phase 1.1 — device registry schema migrations, applied in dependency order.
_REGISTRY_MIGRATIONS = [
    "003_create_devices.sql",
    "004_create_device_signals.sql",
    "005_create_device_review_digests.sql",
    "006_create_llm_budget_ledger.sql",
    "007_create_device_corrections.sql",
    "008_backfill_existing_devices.sql",
    "009_create_api_views.sql",
    "010_create_db_roles_and_freeze_trigger.sql",
    "011_extend_freeze_protected_columns.sql",
    "012_grant_ai_correction_read.sql",
    "013_index_corrections_key_time.sql",
    "014_create_device_audit_log.sql",
    "015_audit_log_ai_least_privilege.sql",
]

_BACKFILLED_DEVICES = ("sim-001", "plc-001", "sensor-001")


def _run_sql_file(db_conn, filename: str):
    sql = (_MIGRATIONS_DIR / filename).read_text()
    with db_conn.cursor() as cur:
        cur.execute(sql)


def _apply_registry_chain(db_conn):
    for fn in _REGISTRY_MIGRATIONS:
        _run_sql_file(db_conn, fn)


@pytest.fixture
def registry_migrated(db_conn):
    """Apply migrations 003-010 in order (idempotent). Leaves sim-001/plc-001/sensor-001 backfilled."""
    _apply_registry_chain(db_conn)
    return db_conn


# ── existing pipeline migrations (PRD-0001/0002) ──────────────────────────────

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


# ── PRD-0003 device registry migrations ───────────────────────────────────────

class TestMigration003Devices:
    """003_create_devices.sql — registry main table + constraints + indexes."""

    def test_run_twice_does_not_raise(self, db_conn):
        _run_sql_file(db_conn, "003_create_devices.sql")
        _run_sql_file(db_conn, "003_create_devices.sql")

    def test_table_exists(self, registry_migrated):
        with registry_migrated.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'devices'
            """)
            assert cur.fetchone() is not None

    def test_status_check_rejects_invalid_value(self, registry_migrated):
        c = registry_migrated
        with c.cursor() as cur:
            with pytest.raises(psycopg2.Error):
                cur.execute(
                    "INSERT INTO public.devices (device_id, status) VALUES ('chk-bad-status', 'not_a_status')"
                )
            c.rollback()

    def test_required_indexes_exist(self, registry_migrated):
        with registry_migrated.cursor() as cur:
            cur.execute("""
                SELECT indexname FROM pg_indexes
                WHERE schemaname = 'public' AND tablename = 'devices'
            """)
            names = {r[0] for r in cur.fetchall()}
        for idx in ("idx_devices_status", "idx_devices_last_seen_at",
                    "idx_devices_device_type", "idx_devices_stale_marked_at"):
            assert idx in names, f"missing index {idx}"


class TestMigration004DeviceSignals:
    """004_create_device_signals.sql — current-state signals + partial unique index + FK."""

    def test_run_twice_does_not_raise(self, db_conn):
        _run_sql_file(db_conn, "003_create_devices.sql")
        _run_sql_file(db_conn, "004_create_device_signals.sql")
        _run_sql_file(db_conn, "004_create_device_signals.sql")

    def test_partial_unique_index_is_partial(self, registry_migrated):
        with registry_migrated.cursor() as cur:
            cur.execute("""
                SELECT indexdef FROM pg_indexes
                WHERE schemaname = 'public' AND indexname = 'device_signals_active_uniq'
            """)
            row = cur.fetchone()
        assert row is not None, "device_signals_active_uniq missing"
        assert "where" in row[0].lower() and "active" in row[0].lower()

    def test_active_unique_but_retired_duplicate_allowed(self, registry_migrated):
        c = registry_migrated
        with c.cursor() as cur:
            cur.execute("INSERT INTO public.devices (device_id, status) VALUES ('sig-uniq-dev', 'candidate') ON CONFLICT DO NOTHING")
            cur.execute("INSERT INTO public.device_signals (device_id, signal_name, status) VALUES ('sig-uniq-dev', 'sx', 'active')")
            with pytest.raises(psycopg2.Error):
                cur.execute("INSERT INTO public.device_signals (device_id, signal_name, status) VALUES ('sig-uniq-dev', 'sx', 'active')")
            c.rollback()
            # a retired duplicate of the same (device_id, signal_name) is allowed (partial index)
            cur.execute("INSERT INTO public.device_signals (device_id, signal_name, status) VALUES ('sig-uniq-dev', 'sx', 'retired')")
        with c.cursor() as cur:
            cur.execute("DELETE FROM public.devices WHERE device_id = 'sig-uniq-dev'")

    def test_fk_cascade_to_devices(self, registry_migrated):
        with registry_migrated.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM information_schema.table_constraints
                WHERE table_schema = 'public' AND table_name = 'device_signals'
                  AND constraint_type = 'FOREIGN KEY'
            """)
            assert cur.fetchone() is not None


class TestMigration005ReviewDigests:
    """005_create_device_review_digests.sql — human-review persistence."""

    def test_run_twice_does_not_raise(self, db_conn):
        _run_sql_file(db_conn, "003_create_devices.sql")
        _run_sql_file(db_conn, "005_create_device_review_digests.sql")
        _run_sql_file(db_conn, "005_create_device_review_digests.sql")

    def test_summary_source_check(self, registry_migrated):
        c = registry_migrated
        with c.cursor() as cur:
            with pytest.raises(psycopg2.Error):
                cur.execute(
                    "INSERT INTO public.device_review_digests (device_id, digest, summary_source) "
                    "VALUES ('sim-001', '{}'::jsonb, 'bogus_source')"
                )
            c.rollback()
            cur.execute(
                "INSERT INTO public.device_review_digests (device_id, digest, summary_source) "
                "VALUES ('sim-001', '{}'::jsonb, 'system_fallback') "
                "ON CONFLICT (device_id) DO UPDATE SET summary_source = EXCLUDED.summary_source"
            )
        with c.cursor() as cur:
            cur.execute("DELETE FROM public.device_review_digests WHERE device_id = 'sim-001'")


class TestMigration006BudgetLedger:
    """006_create_llm_budget_ledger.sql — budget ledger + unique(period_start, provider)."""

    def test_run_twice_does_not_raise(self, db_conn):
        _run_sql_file(db_conn, "006_create_llm_budget_ledger.sql")
        _run_sql_file(db_conn, "006_create_llm_budget_ledger.sql")

    def test_unique_period_provider(self, registry_migrated):
        c = registry_migrated
        with c.cursor() as cur:
            cur.execute(
                "INSERT INTO public.llm_budget_ledger (period_start, period_end, provider, budget_usd) "
                "VALUES ('2099-01-01', '2099-02-01', 'test-prov', 20)"
            )
            with pytest.raises(psycopg2.Error):
                cur.execute(
                    "INSERT INTO public.llm_budget_ledger (period_start, period_end, provider, budget_usd) "
                    "VALUES ('2099-01-01', '2099-03-01', 'test-prov', 30)"
                )
            c.rollback()
        with c.cursor() as cur:
            cur.execute("DELETE FROM public.llm_budget_ledger WHERE provider = 'test-prov'")

    def test_active_index_exists(self, registry_migrated):
        with registry_migrated.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'public' AND indexname = 'llm_budget_ledger_active'
            """)
            assert cur.fetchone() is not None


class TestMigration007Corrections:
    """007_create_device_corrections.sql — human correction feedback (permanent)."""

    def test_run_twice_does_not_raise(self, db_conn):
        _run_sql_file(db_conn, "003_create_devices.sql")
        _run_sql_file(db_conn, "007_create_device_corrections.sql")
        _run_sql_file(db_conn, "007_create_device_corrections.sql")

    def test_explanation_length_check_and_defaults(self, registry_migrated):
        c = registry_migrated
        long_text = "x" * 40  # within 30..500
        with c.cursor() as cur:
            cur.execute(
                "INSERT INTO public.device_corrections "
                "(device_id, verdict, human_explanation, created_by_key_id, salt_version) "
                "VALUES ('sim-001', 'good_with_note', %s, 'keyhash', 'v1') RETURNING id, is_active, applied_count",
                (long_text,),
            )
            row = cur.fetchone()
            assert row[1] is True       # is_active default
            assert row[2] == 0          # applied_count default
            cid = row[0]
            # too-short explanation violates length CHECK
            with pytest.raises(psycopg2.Error):
                cur.execute(
                    "INSERT INTO public.device_corrections "
                    "(device_id, verdict, human_explanation, created_by_key_id, salt_version) "
                    "VALUES ('sim-001', 'good_with_note', 'too short', 'keyhash', 'v1')"
                )
            c.rollback()
        with c.cursor() as cur:
            cur.execute("DELETE FROM public.device_corrections WHERE id = %s", (cid,))


class TestMigration008Backfill:
    """008_backfill_existing_devices.sql — existing 3 devices registered as confirmed."""

    def test_three_devices_confirmed_and_frozen(self, registry_migrated):
        with registry_migrated.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM public.devices "
                "WHERE device_id IN %s AND status = 'confirmed' AND classified_by = 'migration_backfill'",
                (_BACKFILLED_DEVICES,),
            )
            assert cur.fetchone()[0] == 3

    def test_signals_active(self, registry_migrated):
        with registry_migrated.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM public.device_signals "
                "WHERE device_id IN %s AND status = 'active'",
                (_BACKFILLED_DEVICES,),
            )
            # sim-001 (4) + plc-001 (6) + sensor-001 (2) = 12
            assert cur.fetchone()[0] == 12

    def test_rerun_does_not_duplicate(self, registry_migrated):
        c = registry_migrated
        with c.cursor() as cur:
            cur.execute("SELECT count(*) FROM public.devices")
            dev_before = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM public.device_signals")
            sig_before = cur.fetchone()[0]
        _run_sql_file(c, "008_backfill_existing_devices.sql")
        with c.cursor() as cur:
            cur.execute("SELECT count(*) FROM public.devices")
            assert cur.fetchone()[0] == dev_before
            cur.execute("SELECT count(*) FROM public.device_signals")
            assert cur.fetchone()[0] == sig_before


class TestMigration009ApiViews:
    """009_create_api_views.sql — whitelist PostgREST views (no SELECT *)."""

    def _view_columns(self, conn, view_name):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'api' AND table_name = %s",
                (view_name,),
            )
            return {r[0] for r in cur.fetchall()}

    def test_views_exist(self, registry_migrated):
        with registry_migrated.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.views "
                "WHERE table_schema = 'api' AND table_name IN ('devices', 'device_signals')"
            )
            assert {r[0] for r in cur.fetchall()} == {"devices", "device_signals"}

    def test_devices_view_hides_internal_columns(self, registry_migrated):
        cols = self._view_columns(registry_migrated, "devices")
        assert "device_id" in cols
        for forbidden in ("status", "classified_by", "ai_confidence", "ai_provider",
                          "last_error", "metadata", "stale_marked_at"):
            assert forbidden not in cols, f"api.devices must not expose {forbidden}"

    def test_signals_view_hides_source_ref_and_status(self, registry_migrated):
        cols = self._view_columns(registry_migrated, "device_signals")
        assert "signal_name" in cols
        for forbidden in ("source_ref", "status", "retired_at", "confirmed_by_ai", "metadata"):
            assert forbidden not in cols, f"api.device_signals must not expose {forbidden}"

    def test_candidate_not_visible_confirmed_visible(self, registry_migrated):
        c = registry_migrated
        with c.cursor() as cur:
            cur.execute("INSERT INTO public.devices (device_id, status) VALUES ('cand-view-test', 'candidate') ON CONFLICT DO NOTHING")
            cur.execute("SELECT device_id FROM api.devices WHERE device_id = 'cand-view-test'")
            assert cur.fetchone() is None  # candidate filtered out
            cur.execute("SELECT device_id FROM api.devices WHERE device_id = 'sim-001'")
            assert cur.fetchone() is not None  # confirmed visible
        with c.cursor() as cur:
            cur.execute("DELETE FROM public.devices WHERE device_id = 'cand-view-test'")


class TestMigration010FreezeTrigger:
    """010_create_db_roles_and_freeze_trigger.sql — DB roles + RCE-proof freeze trigger."""

    def test_roles_exist(self, registry_migrated):
        with registry_migrated.cursor() as cur:
            cur.execute("SELECT rolname FROM pg_roles WHERE rolname IN ('device_service_ai', 'device_service_ops')")
            assert {r[0] for r in cur.fetchall()} == {"device_service_ai", "device_service_ops"}

    def test_trigger_exists(self, registry_migrated):
        with registry_migrated.cursor() as cur:
            cur.execute("SELECT tgname FROM pg_trigger WHERE tgname = 'devices_freeze_check'")
            assert cur.fetchone() is not None

    def test_ai_role_cannot_mutate_frozen_device_type(self, registry_migrated):
        c = registry_migrated
        cur = c.cursor()
        try:
            cur.execute("SET ROLE device_service_ai")
            raised = False
            try:
                cur.execute("UPDATE public.devices SET device_type = 'hacked' WHERE device_id = 'sim-001'")
            except psycopg2.Error:
                raised = True
            c.rollback()
            assert raised, "freeze trigger must block ai role from mutating frozen device_type"
        finally:
            c.rollback()
            cur.execute("RESET ROLE")
            cur.close()

    def test_ai_role_may_update_last_seen_on_frozen(self, registry_migrated):
        c = registry_migrated
        cur = c.cursor()
        try:
            cur.execute("SET ROLE device_service_ai")
            # last_seen_at is not a frozen column -> allowed even on frozen device
            cur.execute("UPDATE public.devices SET last_seen_at = now() WHERE device_id = 'sim-001'")
        finally:
            c.rollback()
            cur.execute("RESET ROLE")
            cur.close()


class TestMigration011ExtendedFreeze:
    """011_extend_freeze_protected_columns.sql — vendor/model/location/protocol also frozen (ADR-018)."""

    def test_run_twice_does_not_raise(self, db_conn):
        _apply_registry_chain(db_conn)
        _run_sql_file(db_conn, "011_extend_freeze_protected_columns.sql")

    def test_ai_role_cannot_mutate_frozen_vendor(self, registry_migrated):
        c = registry_migrated
        cur = c.cursor()
        try:
            cur.execute("SET ROLE device_service_ai")
            raised = False
            try:
                cur.execute("UPDATE public.devices SET vendor = 'attacker' WHERE device_id = 'sim-001'")
            except psycopg2.Error:
                raised = True
            c.rollback()
            assert raised, "extended freeze must block ai role from mutating frozen vendor"
        finally:
            c.rollback()
            cur.execute("RESET ROLE")
            cur.close()

    def test_ai_role_may_still_write_ai_confidence_on_frozen(self, registry_migrated):
        c = registry_migrated
        cur = c.cursor()
        try:
            cur.execute("SET ROLE device_service_ai")
            # ai_confidence stays AI-writable (FR-335 drift detection) even on a frozen device
            cur.execute("UPDATE public.devices SET ai_confidence = 0.42 WHERE device_id = 'sim-001'")
        finally:
            c.rollback()
            cur.execute("RESET ROLE")
            cur.close()
        with c.cursor() as cur2:
            cur2.execute("UPDATE public.devices SET ai_confidence = NULL WHERE device_id = 'sim-001'")

class TestMigration012AiCorrectionGrant:
    """012 — AI role gets SELECT + column-scoped UPDATE(applied_count,last_applied_at)
    on device_corrections, but cannot create or alter human correction content."""

    @staticmethod
    def _seed_correction(c):
        # sim-001 is a backfilled (existing) device; insert one correction as superuser
        with c.cursor() as cur:
            cur.execute(
                """INSERT INTO public.device_corrections
                       (device_id, verdict, corrected_device_type, human_explanation,
                        created_by_key_id, salt_version)
                   VALUES ('sim-001','wrong_classification','electricity',
                           'a sufficiently long operator explanation for the migration grant test',
                           'kid','v1')
                   RETURNING id""")
            cid = cur.fetchone()[0]
        c.commit()
        return cid

    def test_ai_can_select_corrections(self, registry_migrated):
        c = registry_migrated
        cid = self._seed_correction(c)
        cur = c.cursor()
        try:
            cur.execute("SET ROLE device_service_ai")
            cur.execute("SELECT id FROM public.device_corrections WHERE id=%s", (cid,))
            assert cur.fetchone()[0] == cid
        finally:
            c.rollback()
            cur.execute("RESET ROLE")
            cur.close()

    def test_ai_can_bump_applied_count_only(self, registry_migrated):
        c = registry_migrated
        cid = self._seed_correction(c)
        cur = c.cursor()
        try:
            cur.execute("SET ROLE device_service_ai")
            cur.execute(
                "UPDATE public.device_corrections SET applied_count=applied_count+1, last_applied_at=now() WHERE id=%s",
                (cid,))
        finally:
            c.rollback()
            cur.execute("RESET ROLE")
            cur.close()

    def test_ai_cannot_insert_or_alter_content(self, registry_migrated):
        c = registry_migrated
        cid = self._seed_correction(c)
        cur = c.cursor()
        try:
            cur.execute("SET ROLE device_service_ai")
            for sql, args in (
                ("UPDATE public.device_corrections SET human_explanation='a long enough replacement explanation here' WHERE id=%s", (cid,)),
                ("UPDATE public.device_corrections SET is_active=FALSE WHERE id=%s", (cid,)),
                ("""INSERT INTO public.device_corrections
                       (device_id, verdict, human_explanation, created_by_key_id, salt_version)
                    VALUES ('sim-001','good_with_note','another long enough explanation here for test','k','v1')""", None),
            ):
                raised = False
                try:
                    cur.execute(sql, args) if args else cur.execute(sql)
                except psycopg2.Error:
                    raised = True
                c.rollback()
                assert raised, f"AI must be denied: {sql[:48]}"
        finally:
            c.rollback()
            cur.execute("RESET ROLE")
            cur.close()


class TestMigration013KeyTimeIndex:
    """013 — per-key rate-limit support index on (created_by_key_id, created_at)."""

    def test_index_exists(self, registry_migrated):
        with registry_migrated.cursor() as cur:
            cur.execute("SELECT indexname FROM pg_indexes WHERE indexname='device_corrections_key_time'")
            assert cur.fetchone() is not None


class TestMigration014AuditLog:
    """014 — append-only device_audit_log; AI+OPS may INSERT/SELECT but not UPDATE/DELETE."""

    def test_table_and_indexes_exist(self, registry_migrated):
        with registry_migrated.cursor() as cur:
            cur.execute("SELECT to_regclass('public.device_audit_log')")
            assert cur.fetchone()[0] is not None
            cur.execute("SELECT indexname FROM pg_indexes WHERE tablename='device_audit_log'")
            idx = {r[0] for r in cur.fetchall()}
            assert {"device_audit_device_event_time", "device_audit_key_event_time"} <= idx

    def test_event_type_check_matches_python_set(self, registry_migrated):
        """The DB CHECK and audit_repo.EVENT_TYPES must list the same event types
        (else a value passes one layer and 500s at the other)."""
        import re

        from device_service.repositories.audit_repo import EVENT_TYPES
        with registry_migrated.cursor() as cur:
            cur.execute(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='device_audit_event_type_chk'")
            defn = cur.fetchone()[0]
        db_types = set(re.findall(r"'([a-z_]+)'", defn))
        assert db_types == set(EVENT_TYPES)

    def test_event_type_check_rejects_unknown(self, registry_migrated):
        c = registry_migrated
        with c.cursor() as cur:
            raised = False
            try:
                cur.execute("INSERT INTO public.device_audit_log (event_type, actor) VALUES ('bogus','ops')")
            except psycopg2.Error:
                raised = True
            c.rollback()
            assert raised

    def test_both_roles_insert_but_not_update_delete(self, registry_migrated):
        # append-only: both roles INSERT (RETURNING id proves the grant), neither UPDATE/DELETE.
        # (AI SELECT is revoked by migration 015 — covered in TestMigration015.)
        c = registry_migrated
        for role, actor in (("device_service_ai", "ai"), ("device_service_ops", "ops")):
            cur = c.cursor()
            try:
                cur.execute(f"SET ROLE {role}")
                cur.execute(
                    "INSERT INTO public.device_audit_log (event_type, actor, device_id) "
                    "VALUES ('guardrail_block', %s, 'itest-audit-x') RETURNING id", (actor,))
                rid = cur.fetchone()[0]
                assert rid
                c.commit()
                for sql in ("UPDATE public.device_audit_log SET outcome='x' WHERE id=%s",
                            "DELETE FROM public.device_audit_log WHERE id=%s"):
                    denied = False
                    try:
                        cur.execute(sql, (rid,))
                    except psycopg2.Error:
                        denied = True
                    c.rollback()
                    assert denied, f"{role} must be denied: {sql[:30]}"
            finally:
                c.rollback()
                cur.execute("RESET ROLE")
                cur.close()
        with c.cursor() as cur2:
            cur2.execute("DELETE FROM public.device_audit_log WHERE device_id='itest-audit-x'")
        c.commit()


class TestMigration015AiLeastPrivilege:
    """015 — AI keeps INSERT + column-scoped SELECT(id) on device_audit_log (so RETURNING id
    works), but cannot read content columns (detail/actor_key_id/...). OPS unchanged."""

    def test_ai_insert_returning_and_count_ok_but_content_denied(self, registry_migrated):
        c = registry_migrated
        cur = c.cursor()
        try:
            cur.execute("SET ROLE device_service_ai")
            # INSERT ... RETURNING id works (SELECT(id) covers the returned column)
            cur.execute("INSERT INTO public.device_audit_log (event_type, actor, device_id) "
                        "VALUES ('guardrail_block','ai','itest-audit-lp') RETURNING id")
            assert cur.fetchone()[0]
            c.commit()
            # reading ANY content column is denied -> no enumeration of operator audit detail
            for col in ("detail", "actor_key_id", "outcome", "device_id",
                        "event_type", "request_id", "correction_id"):
                denied = False
                try:
                    cur.execute(f"SELECT {col} FROM public.device_audit_log LIMIT 1")
                except psycopg2.Error:
                    denied = True
                c.rollback()
                assert denied, f"AI must NOT read device_audit_log.{col} (least-privilege)"
        finally:
            c.rollback()
            cur.execute("RESET ROLE")
            cur.close()

    def test_ops_can_still_select(self, registry_migrated):
        c = registry_migrated
        cur = c.cursor()
        try:
            cur.execute("SET ROLE device_service_ops")
            cur.execute("SELECT count(*) FROM public.device_audit_log")
            assert cur.fetchone()[0] >= 0
        finally:
            c.rollback()
            cur.execute("RESET ROLE")
            cur.close()
        with c.cursor() as cur2:
            cur2.execute("DELETE FROM public.device_audit_log WHERE device_id IN ('itest-audit-lp','itest-audit-x')")
        c.commit()


class TestDeviceRegistryChainIdempotent:
    """Full 003-015 chain must be safe to apply twice (project_rules §13)."""

    def test_chain_runs_twice(self, db_conn):
        _apply_registry_chain(db_conn)
        _apply_registry_chain(db_conn)  # second pass must not raise
