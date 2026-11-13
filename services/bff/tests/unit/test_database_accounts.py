"""PRD-0023 FR-2301/06: session revocation and DB outage boundaries."""
import asyncio
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from bff.accounts import AccountAuth, AccountUnavailable, validate_phc
from bff.main import create_app
from bff.roles import Role
from tests.account_fakes import FakeAccounts
from tests.conftest import AUTH_USERS, make_settings, login, phc

def setup_client(repo):
    return TestClient(create_app(make_settings(), account_repository=repo),
                      base_url="https://testserver")

@pytest.mark.parametrize("change", [
    {"enabled": False}, {"role": Role.READONLY}, {"password_hash": phc("new-password")},
])
def test_change_revokes_old_session_and_reversing_does_not_restore(change):
    repo = FakeAccounts(AUTH_USERS)
    before = repo.rows["ops_user"]
    with setup_client(repo) as client:
        assert login(client, "ops_user", "ops-pw").status_code == 200
        repo.change("ops_user", **change)
        repo.change("ops_user", enabled=before.enabled, role=before.role,
                    password_hash=before.password_hash)
        assert client.get("/api/auth/session").status_code == 401

def test_database_outage_fail_closed_on_login_and_existing_session():
    repo = FakeAccounts(AUTH_USERS)
    with setup_client(repo) as client:
        assert login(client, "ops_user", "ops-pw").status_code == 200
        repo.unavailable = True
        assert client.get("/api/auth/session").status_code == 503
        assert login(client, "ops_user", "ops-pw").status_code == 503

def test_disabled_unknown_wrong_password_same_response():
    repo = FakeAccounts(AUTH_USERS)
    repo.change("ops_user", enabled=False)
    with setup_client(repo) as client:
        results = [login(client, n, p) for n,p in [
            ("ops_user","ops-pw"),("nobody","ops-pw"),("view_user","wrong")]]
        assert all(r.status_code == 401 for r in results)
        assert len({r.text for r in results}) == 1

def test_missing_dsn_does_not_fall_back_to_env(monkeypatch):
    monkeypatch.setenv("BFF_AUTH_USERS", AUTH_USERS)
    with pytest.raises(RuntimeError, match="BFF_AUTH_DB_DSN"):
        with TestClient(create_app(make_settings(auth_db_dsn=""))):
            pass

def test_password_reset_during_verify_never_mints_new_version():
    repo = FakeAccounts(AUTH_USERS)
    version = repo.rows["ops_user"].auth_version
    def verify_and_reset(*args):
        repo.change("ops_user", password_hash=phc("different-password"))
        return Role.OPS
    async def run():
        with patch("bff.accounts.verify", verify_and_reset):
            result = await AccountAuth(repo).authenticate("ops_user","ops-pw")
        assert result.auth_version == version
        assert result.auth_version != repo.rows["ops_user"].auth_version
    asyncio.run(run())

@pytest.mark.parametrize("bad", [
    "abc", "$argon2id$v=19$m=65536,t=3,p=4$YWJjZGVmZ2hpZ$YWJjZGVmZ2hpamtsbW5vcA", "$argon2i$v=19$m=65536,t=3,p=4$aaaa$bbbb",
    "$argon2id$v=19$m=999999999,t=3,p=4$YWJjZGVmZ2g$YWJjZGVmZ2hpamtsbW5vcA",
    "$argon2id$v=19$m=65536,t=9999,p=4$YWJjZGVmZ2g$YWJjZGVmZ2hpamtsbW5vcA",
])
def test_reject_unbounded_or_invalid_import_hash(bad):
    with pytest.raises(ValueError):
        validate_phc(bad)

def test_valid_hash():
    validate_phc(phc("any"))


def test_repeated_cancellation_keeps_argon_worker_slot():
    import threading
    release = threading.Event()
    repo = FakeAccounts(AUTH_USERS)
    async def run():
        loop=asyncio.get_running_loop()
        started=asyncio.Queue()
        count=0
        def blocked(*args):
            nonlocal count
            count+=1
            loop.call_soon_threadsafe(started.put_nowait,count)
            assert release.wait(timeout=3)
            return Role.OPS
        auth=AccountAuth(repo)
        with patch("bff.accounts.verify",blocked):
            first=asyncio.create_task(auth.authenticate("ops_user","ops-pw"))
            await asyncio.wait_for(started.get(),1)
            first.cancel()
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            second=asyncio.create_task(auth.authenticate("ops_user","ops-pw"))
            third=asyncio.create_task(auth.authenticate("ops_user","ops-pw"))
            await asyncio.wait_for(started.get(),1)
            await asyncio.sleep(0)
            assert count==2
            release.set()
            await asyncio.gather(second,third)
    try:
        asyncio.run(run())
    finally:
        release.set()
