"""Login-route behaviour under the auth-provider seam (ADR-024).

The session / CSRF / role plumbing downstream of auth is unchanged and already
covered by test_session_lifecycle.py. Here we pin the provider-selection edges
that the route exposes to the browser:
- local mode (default) mints a session (sanity that the seam did not regress it)
- oidc mode (Phase-1 stub) fails closed with 503 and never sets a cookie
"""
from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from bff.main import create_app
from tests.conftest import ORIGIN, make_settings


def _client(recorder, clock, **overrides) -> TestClient:
    app = create_app(
        settings=make_settings(**overrides),
        upstream_transport=httpx.MockTransport(recorder.handler),
        clock=clock,
    )
    return TestClient(app, base_url="https://testserver")


def test_local_mode_login_succeeds(recorder, clock):
    with _client(recorder, clock, auth_mode="local") as c:
        r = c.post(
            "/api/auth/login",
            json={"username": "ops_user", "password": "ops-pw"},
            headers={"Origin": ORIGIN},
        )
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
        assert "set-cookie" in r.headers


def test_oidc_mode_login_is_503_and_sets_no_cookie(recorder, clock):
    # OIDC selected but not integrated in P1 -> capability error, fail closed.
    with _client(recorder, clock, auth_mode="oidc", auth_users="") as c:
        r = c.post(
            "/api/auth/login",
            json={"username": "ops_user", "password": "ops-pw"},
            headers={"Origin": ORIGIN},
        )
        assert r.status_code == 503, f"OIDC P1 stub must be 503, got {r.status_code}: {r.text}"
        assert "set-cookie" not in r.headers, "no session may be minted when auth is unavailable"
        # error body must not leak provider internals / secrets
        assert "key" not in r.text.lower()
