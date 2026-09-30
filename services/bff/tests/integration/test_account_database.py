"""Real disposable PostgreSQL tests; opt in with AUTH_TEST_DSN."""
import asyncio
import json
import os
from uuid import uuid4
from urllib.parse import urlsplit,urlunsplit
import secrets
import pytest
import asyncpg
from fastapi.testclient import TestClient
from bff.accounts import PostgresAccounts
from bff.account_cli import main
from bff.main import create_app
from tests.conftest import make_settings, login
pytestmark=pytest.mark.integration

@pytest.fixture(scope="module")
def db_roles():
    dsn=os.environ.get("AUTH_TEST_DSN")
    if not dsn:
        pytest.skip("requires disposable AUTH_TEST_DSN")
    assert urlsplit(dsn).path=="/auth_acceptance"
    password=secrets.token_hex(24)
    suffix=uuid4().hex[:12]
    roles={group:"accept_"+group+"_"+suffix for group in ("bff_auth_reader","bff_auth_admin")}
    async def setup(cleanup=False):
        conn=await asyncpg.connect(dsn)
        try:
            for group,role in roles.items():
                if cleanup:
                    await conn.execute(f"DROP ROLE {role}")
                else:
                    await conn.execute(f"CREATE ROLE {role} LOGIN PASSWORD '{password}' IN ROLE {group}")
        finally:
            await conn.close()
    asyncio.run(setup())
    parsed=urlsplit(dsn)
    def role_dsn(group):
        return urlunsplit((parsed.scheme,roles[group]+":"+password+"@"+parsed.netloc.split("@")[-1],
                           parsed.path,parsed.query,parsed.fragment))
    try:
        yield role_dsn("bff_auth_reader"),role_dsn("bff_auth_admin")
    finally:
        asyncio.run(setup(cleanup=True))

def test_cli_real_database_and_runtime_sessions(db_roles,monkeypatch,capsys):
    reader,admin=db_roles
    monkeypatch.setenv("BFF_AUTH_ADMIN_DSN",admin)
    username="accept_"+uuid4().hex[:10]
    password="Acceptance-password-123"
    monkeypatch.setattr("bff.account_cli.getpass",lambda _:password)
    def cli(*args):
        assert main(list(args))==0
        output=capsys.readouterr()
        assert "argon2id" not in output.out and "password_hash" not in output.out
        return json.loads(output.out)
    rid=str(uuid4())
    account=cli("create",username,"--role","ops","--reason","acceptance","--request-id",rid)
    assert account["enabled"]
    assert cli("create",username,"--role","ops","--reason","acceptance","--request-id",rid)==account
    assert any(r["username"]==username for r in cli("list")["items"])
    app=create_app(make_settings(auth_db_dsn=reader))
    with TestClient(app,base_url="https://testserver") as client:
        assert login(client,username,password).status_code==200
        assert client.get("/api/auth/session").status_code==200
        cli("disable",username,"--reason","acceptance")
        assert client.get("/api/auth/session").status_code==401
        cli("enable",username,"--reason","acceptance")
        assert client.get("/api/auth/session").status_code==401
        assert login(client,username,password).status_code==200
        cli("set-role",username,"--role","readonly","--reason","acceptance")
        assert client.get("/api/auth/session").status_code==401
        assert login(client,username,password).status_code==200
        cli("reset-password",username,"--reason","acceptance")
        assert client.get("/api/auth/session").status_code==401
        assert login(client,username,password).status_code==200
    with TestClient(create_app(make_settings(auth_db_dsn=reader)),base_url="https://testserver") as client:
        assert login(client,username,password).status_code==200
    assert len(cli("history","--username",username)["items"])==5
    assert len(cli("history","--request-id",rid)["items"])==1

def test_repository_handles_connection_error():
    async def run():
        with pytest.raises((OSError,asyncpg.PostgresError)):
            await PostgresAccounts.connect("postgresql://none:none@127.0.0.1:1/absent")
    asyncio.run(run())

def test_cli_safe_failure_messages(monkeypatch,capsys):
    monkeypatch.delenv("BFF_AUTH_ADMIN_DSN",raising=False)
    assert main(["list"])==2
    monkeypatch.setenv("BFF_AUTH_ADMIN_DSN","postgresql://secret:secret@127.0.0.1:1/absent")
    assert main(["list"])==1
    assert main(["disable","bad name","--reason","test"])==2
    assert main(["disable","user","--reason"," "])==2
    assert "secret" not in capsys.readouterr().err
