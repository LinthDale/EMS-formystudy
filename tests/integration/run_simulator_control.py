"""Run a temporary, unexposed BFF against live demo targets; never alter live login users."""
import os
import secrets
import sqlite3
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from argon2 import PasswordHasher
from bff.config import Settings
os.environ["BFF_SIM_CONTROL_ENABLED"] = "false"  # global app stays unconfigured
from bff.main import create_app
"""In-memory repository for explicit app-factory injection, never runtime config."""
from dataclasses import replace
from uuid import uuid4
from bff.accounts import Account, AccountUnavailable
from bff.credentials import parse_auth_users

class FakeAccounts:
    def __init__(self, raw=""):
        self.rows = {name: Account(uuid4(), name, phc, role, True, 1)
                     for name, (phc, role) in parse_auth_users(raw).items()}
        self.unavailable = False
    async def by_username(self, name):
        if self.unavailable:
            raise AccountUnavailable()
        return self.rows.get(name)
    async def by_id(self, account_id):
        if self.unavailable:
            raise AccountUnavailable()
        return next((r for r in self.rows.values() if r.id == account_id), None)
    def change(self, name, **fields):
        old = self.rows[name]
        self.rows[name] = replace(old, auth_version=old.auth_version + 1, **fields)


password = secrets.token_urlsafe(32)
username = "sim-control-acceptance"
os.environ.update(
    EMS_BFF_URL="http://127.0.0.1:18003",
    EMS_BFF_ORIGIN="http://127.0.0.1:18003",
    EMS_TEST_USERNAME=username, EMS_TEST_PASSWORD=password,
    EMS_POSTGREST_URL="http://query:3000",
)
settings = Settings(
    _env_file=None, auth_mode="local",
    session_cookie_secure=False, public_origins="http://127.0.0.1:18003",
    sim_control_enabled=True, sim_control_token=os.environ["SIM_CONTROL_TOKEN"],
    sim_control_db=os.getenv("EMS_ACCEPTANCE_AUDIT_PATH", "/tmp/acceptance-audit.sqlite3"),
)


def start():
    server = uvicorn.Server(uvicorn.Config(create_app(settings=settings, account_repository=FakeAccounts(f"{username}:{PasswordHasher().hash(password)}:ops")), host="127.0.0.1",
                                          port=18003, log_level="warning", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("test BFF startup failed")
        time.sleep(.05)
    return server, thread


def stop(server, thread):
    server.should_exit = True
    thread.join(timeout=10)
    assert not thread.is_alive(), "test BFF did not close"


server, thread = start()
try:
    code = pytest.main([
        "tests/integration/test_simulator_rest.py",
        "tests/integration/test_pipeline_electricity.py",
        "tests/integration/test_pipeline_factory.py",
        "tests/integration/test_pipeline_delta_control.py",
        "-q", "-p", "no:cacheprovider",
    ])
finally:
    stop(server, thread)
with sqlite3.connect(settings.sim_control_db) as db:
    count = db.execute("SELECT count(*) FROM operations").fetchone()[0]
assert count > 0
server, thread = start()
try:
    with httpx.Client(base_url="http://127.0.0.1:18003", trust_env=False) as client:
        result = client.post("/api/auth/login", headers={"Origin": "http://127.0.0.1:18003"},
                             json={"username": username, "password": password})
        assert result.status_code == 200
        rows = client.get("/api/simulators/operations?limit=100").json()["items"]
        assert len(rows) == count
        assert all(row["actor"] == username for row in rows)
        print(f"Audit survives BFF restart: {count} operations; credentials never persisted")
finally:
    stop(server, thread)
raise SystemExit(code)
