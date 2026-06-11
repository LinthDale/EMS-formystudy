"""Config boundary validation — project_rules §19 pattern (env > .env > toml > defaults;
secrets only from env/.env; fail fast on malformed input)."""
from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError

from bff.config import Settings
from bff.main import create_app
from tests.conftest import make_settings, sha


def test_idle_timeout_cannot_exceed_max_lifetime():
    with pytest.raises(ValidationError):
        make_settings(session_max_lifetime_s=100, session_idle_timeout_s=200)


def test_non_positive_lifetimes_rejected():
    with pytest.raises(ValidationError):
        make_settings(session_max_lifetime_s=0)
    with pytest.raises(ValidationError):
        make_settings(session_idle_timeout_s=-5)


def test_malformed_auth_users_fails_fast_at_startup():
    with pytest.raises(ValueError):
        create_app(settings=make_settings(auth_users="this-is-not-a-user-record"))


def test_unknown_role_in_auth_users_fails_fast():
    bad = f"root:{sha('pw')}:superadmin"
    with pytest.raises(ValueError):
        create_app(settings=make_settings(auth_users=bad))


def test_bad_password_hash_in_auth_users_fails_fast():
    bad = "ops_user:nothex:ops"
    with pytest.raises(ValueError):
        create_app(settings=make_settings(auth_users=bad))


def test_empty_auth_users_means_no_login_possible(recorder, clock):
    """Fail closed: no configured users -> every login attempt is 401."""
    from fastapi.testclient import TestClient

    app = create_app(
        settings=make_settings(auth_users=""),
        upstream_transport=httpx.MockTransport(recorder.handler),
        clock=clock,
    )
    with TestClient(app, base_url="https://testserver") as c:
        r = c.post(
            "/api/auth/login",
            json={"username": "ops_user", "password": "ops-pw"},
            headers={"Origin": "https://testserver"},
        )
        assert r.status_code == 401, f"got {r.status_code}"


def test_toml_source_ignores_secret_fields(tmp_path, monkeypatch):
    """Secrets must come from env/.env only — a committed TOML cannot smuggle keys."""
    toml = tmp_path / "bff.toml"
    toml.write_text(
        'ops_api_key = "evil-key-from-toml"\n'
        "session_idle_timeout_s = 123\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BFF_CONFIG_FILE", str(toml))
    s = Settings(_env_file=None)
    assert s.session_idle_timeout_s == 123, "tunables must load from TOML"
    assert s.ops_api_key == "", "secret fields in TOML must be ignored"
