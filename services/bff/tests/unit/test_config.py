"""Config boundary validation — project_rules §19 pattern (env > .env > toml > defaults;
secrets only from env/.env; fail fast on malformed input)."""
from __future__ import annotations

import httpx
import pytest
from pydantic import ValidationError

from bff.config import Settings
from bff.main import create_app
from tests.conftest import make_settings, phc


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
    bad = f"root:{phc('pw')}:superadmin"
    with pytest.raises(ValueError):
        create_app(settings=make_settings(auth_users=bad))


def test_bad_password_hash_in_auth_users_fails_fast():
    # a SHA-256-style hex digest is no longer an accepted hash (argon2id PHC only)
    bad = "ops_user:" + ("a" * 64) + ":ops"
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


def test_oidc_mode_without_issuer_fails_fast():
    """auth_mode=oidc with no issuer/client/redirect must not boot (fail closed)."""
    with pytest.raises(ValidationError):
        make_settings(auth_mode="oidc")


def test_oidc_mode_without_role_map_fails_fast():
    with pytest.raises(ValidationError):
        make_settings(
            auth_mode="oidc",
            oidc_issuer="https://idp.example.test",
            oidc_client_id="client",
            oidc_redirect_uri="https://app/cb",
            oidc_role_map="",  # no mapping -> every login would be unmapped
        )


def test_oidc_role_map_parses_to_value_role_dict():
    s = make_settings(
        auth_mode="oidc",
        oidc_issuer="https://idp.example.test",
        oidc_client_id="client",
        oidc_redirect_uri="https://app/cb",
        oidc_role_map="ems-ops:ops, ems-view:readonly",
    )
    assert s.oidc_role_mapping == {"ems-ops": "ops", "ems-view": "readonly"}


def test_oidc_role_map_malformed_entry_fails_fast():
    s = make_settings(
        auth_mode="local",  # mapping parsed lazily; local mode lets us construct
        oidc_role_map="ems-ops",  # missing ':role'
    )
    with pytest.raises(ValueError):
        _ = s.oidc_role_mapping


def test_oidc_client_secret_is_a_secret_field_ignored_in_toml(tmp_path, monkeypatch):
    toml = tmp_path / "bff.toml"
    toml.write_text('oidc_client_secret = "leaked-from-toml"\n', encoding="utf-8")
    monkeypatch.setenv("BFF_CONFIG_FILE", str(toml))
    s = Settings(_env_file=None)
    assert s.oidc_client_secret == "", "oidc_client_secret in TOML must be ignored"


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


def test_oidc_post_login_redirect_must_be_same_origin_path():
    """review P2: an absolute / protocol-relative redirect would be an open redirect
    after a successful OIDC login; only a same-origin '/path' is accepted."""
    for bad in ("https://evil.example", "//evil.example", "/\\evil.example", "http://x"):
        with pytest.raises(ValidationError):
            make_settings(oidc_post_login_redirect=bad)
    assert make_settings(oidc_post_login_redirect="/devices").oidc_post_login_redirect == "/devices"


def test_oidc_endpoints_require_https_except_localhost():
    """review P2: issuer/redirect must be https in real deployments (cleartext only for
    localhost/127.0.0.1 dev)."""
    base = dict(
        auth_mode="oidc", oidc_client_id="client",
        oidc_role_map="ems-ops:ops", oidc_redirect_uri="https://app.example/cb",
    )
    with pytest.raises(ValidationError):  # cleartext non-local issuer
        make_settings(**{**base, "oidc_issuer": "http://idp.evil.example"})
    with pytest.raises(ValidationError):  # cleartext non-local redirect
        make_settings(**{**base, "oidc_issuer": "https://idp.example",
                         "oidc_redirect_uri": "http://app.evil.example/cb"})
    make_settings(**{**base, "oidc_issuer": "https://idp.example"})  # https -> ok
    make_settings(  # http on localhost -> ok (dev)
        auth_mode="oidc", oidc_client_id="client", oidc_role_map="ems-ops:ops",
        oidc_issuer="http://localhost:9000", oidc_redirect_uri="http://localhost:8080/cb",
    )
