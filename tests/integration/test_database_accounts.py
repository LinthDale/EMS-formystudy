"""PRD-0023 real PostgreSQL acceptance; AUTH_TEST_DSN must point to disposable DB."""
import concurrent.futures
import json
import os
from pathlib import Path
from uuid import uuid4
import pytest
import psycopg2

pytestmark = pytest.mark.integration
DSN = os.environ.get("AUTH_TEST_DSN")
PHC = "$argon2id$v=19$m=65536,t=3,p=4$YWJjZGVmZ2hpamtsbW5vcA$YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXpBQkNERUY"

@pytest.fixture
def db():
    if not DSN:
        pytest.skip("requires disposable AUTH_TEST_DSN")
    connection = psycopg2.connect(DSN)
    connection.autocommit = True
    sql = Path("infra/timescaledb/migrations/018_bff_accounts.sql").read_text()
    with connection.cursor() as cur:
        cur.execute("SELECT current_database()")
        assert cur.fetchone()[0] == "auth_acceptance", "disposable DB only"
        cur.execute("DROP SCHEMA IF EXISTS bff_auth CASCADE")
        cur.execute(sql)
        cur.execute(sql)
    mutate(connection, "create", "admin_one", "ops", PHC)
    yield connection
    connection.close()

def mutate(db, action, username, role=None, phc=None, request_id=None):
    with db.cursor() as cur:
        cur.execute("SELECT bff_auth.manage_account(%s,%s,%s,%s,%s,%s)",
                    (str(request_id or uuid4()), action, username, phc, role, "acceptance"))
        return cur.fetchone()[0]

def test_01_migration_roles_private_and_bootstrap(db):
    with db.cursor() as cur:
        cur.execute("SELECT role FROM bff_auth.accounts WHERE username=\'admin_one\'")
        assert cur.fetchone()[0] == "ops"
    with db.cursor() as cur:
        for role in ["bff_auth_reader", "bff_auth_admin"]:
            cur.execute("SELECT has_table_privilege(%s,'bff_auth.accounts','UPDATE')", (role,))
            assert cur.fetchone()[0] is False
        cur.execute("SELECT has_table_privilege('bff_auth_admin','bff_auth.account_audit','DELETE')")
        assert not cur.fetchone()[0]
        cur.execute("SELECT has_schema_privilege('public','bff_auth','USAGE')")
        assert not cur.fetchone()[0]

def test_02_last_ops_and_audit_rollback(db):
    with pytest.raises(psycopg2.Error):
        mutate(db, "disable", "admin_one")
    with db.cursor() as cur:
        cur.execute("SELECT enabled FROM bff_auth.accounts WHERE username='admin_one'")
        assert cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM bff_auth.account_audit WHERE action='disable'")
        assert cur.fetchone()[0] == 0

def test_03_audit_idempotence_and_no_secrets(db):
    rid = uuid4()
    first = mutate(db, "create", "reader_one", "readonly", PHC, rid)
    again = mutate(db, "create", "reader_one", "readonly", PHC, rid)
    assert first == again
    changed = mutate(db, "set-role", "reader_one", "ingest")
    assert changed["auth_version"] == first["auth_version"] + 1
    with db.cursor() as cur:
        cur.execute("SELECT row_to_json(a)::text FROM bff_auth.account_audit a")
        assert all("argon2" not in r[0] and "password_hash" not in r[0] for r in cur.fetchall())

def test_04_import_atomic_one_time(db):
    with db.cursor() as cur:
        good = [{"username":"import_ops","password_hash":PHC,"role":"ops"}]
        bad = good + [{"username":"bad name","password_hash":PHC,"role":"readonly"}]
        with pytest.raises(psycopg2.Error):
            cur.execute("SELECT bff_auth.import_legacy(%s::jsonb,%s)", (json.dumps(bad),"acceptance"))
        cur.execute("SELECT count(*) FROM bff_auth.accounts WHERE username='import_ops'")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT bff_auth.import_legacy(%s::jsonb,%s)", (json.dumps(good),"acceptance"))
        assert cur.fetchone()[0]["imported"] == 1
        mutate(db, "disable", "import_ops")
        cur.execute("SELECT bff_auth.import_legacy(%s::jsonb,%s)", (json.dumps(good),"acceptance"))
        assert cur.fetchone()[0]["already_imported"]
        cur.execute("SELECT enabled FROM bff_auth.accounts WHERE username='import_ops'")
        assert not cur.fetchone()[0]

def test_05_last_ops_concurrent(db):
    mutate(db,"create","admin_two","ops",PHC)
    def disable(name):
        conn = psycopg2.connect(DSN)
        conn.autocommit = True
        try:
            mutate(conn,"disable",name)
            return True
        except psycopg2.Error:
            return False
        finally:
            conn.close()
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        result = list(pool.map(disable,["admin_one","admin_two"]))
    assert sorted(result) == [False,True]

def test_06_function_admin_boundary(db):
    with db.cursor() as cur:
        cur.execute("SET ROLE bff_auth_admin")
        try:
            with pytest.raises(psycopg2.Error):
                cur.execute("UPDATE bff_auth.accounts SET enabled=false")
            with pytest.raises(psycopg2.Error):
                cur.execute("DELETE FROM bff_auth.account_audit")
            with pytest.raises(psycopg2.Error):
                cur.execute("TRUNCATE bff_auth.account_audit")
            with pytest.raises(psycopg2.Error):
                cur.execute("SELECT password_hash FROM bff_auth.accounts")
            cur.execute("SELECT username FROM bff_auth.account_summary")
            assert cur.fetchall()
            mutate(db,"create","admin_boundary","readonly",PHC)
        finally:
            cur.execute("RESET ROLE")


def test_07_reject_repeatable_read_and_null_import(db):
    db.autocommit = False
    try:
        with db.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        with pytest.raises(psycopg2.Error):
            mutate(db,"disable","admin_one")
    finally:
        db.rollback()
        db.autocommit = True
    with db.cursor() as cur:
        cur.execute("DELETE FROM bff_auth.imports")
        with pytest.raises(psycopg2.Error):
            cur.execute("SELECT bff_auth.import_legacy(NULL,'acceptance')")
        cur.execute("SELECT count(*) FROM bff_auth.imports")
        assert cur.fetchone()[0] == 0


def test_08_reject_malformed_phc(db):
    invalid = PHC.replace("YWJjZGVmZ2hpamtsbW5vcA", "YWJjZGVmZ2hpZ", 1)
    with pytest.raises(psycopg2.Error):
        mutate(db,"create","invalid_phc","ops",invalid)
