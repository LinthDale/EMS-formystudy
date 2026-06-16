"""Login-route behaviour under the auth-provider seam (ADR-024).

The session / CSRF / role plumbing downstream of auth is unchanged and already
covered by test_session_lifecycle.py. Here we pin the provider-selection edges
that the route exposes to the browser:
- local mode (default) mints a session (sanity that the seam did not regress it)
- oidc mode (Phase-1 stub) fails closed with 503 and never sets a cookie
"""
from __future__ import annotations

import asyncio

import httpx
from fastapi.testclient import TestClient

from bff.main import create_app
from bff.oidc import OidcClient
from tests import oidc_fixtures as mock
from tests.conftest import ORIGIN, make_settings


def _client(recorder, clock, oidc_client=None, **overrides) -> TestClient:
    app = create_app(
        settings=make_settings(**overrides),
        upstream_transport=httpx.MockTransport(recorder.handler),
        clock=clock,
        oidc_client=oidc_client,
    )
    return TestClient(app, base_url="https://testserver")


def _oidc_app(recorder, clock):
    """Build an oidc-mode app with a pre-discovered client (mock IdP, no network)."""
    issuer = mock.MockIssuer()
    settings = make_settings(auth_users="", **mock.oidc_overrides())

    async def _discover() -> OidcClient:
        idp_http = httpx.AsyncClient(transport=httpx.MockTransport(issuer.handler))
        return await OidcClient.discover(settings, idp_http)

    return create_app(
        settings=settings,
        upstream_transport=httpx.MockTransport(recorder.handler),
        clock=clock,
        oidc_client=asyncio.run(_discover()),
    )


def test_local_mode_login_succeeds(recorder, clock):
    with _client(recorder, clock, auth_mode="local") as c:
        r = c.post(
            "/api/auth/login",
            json={"username": "ops_user", "password": "ops-pw"},
            headers={"Origin": ORIGIN},
        )
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
        assert "set-cookie" in r.headers


def test_oidc_mode_password_login_is_503_and_sets_no_cookie(recorder, clock):
    # In OIDC mode the password route is not the auth path (login is the redirect
    # flow at GET /api/auth/oidc/login). The password POST fails closed with 503
    # rather than silently degrading. A pre-built oidc_client avoids live discovery.
    app = _oidc_app(recorder, clock)
    with TestClient(app, base_url="https://testserver") as c:
        r = c.post(
            "/api/auth/login",
            json={"username": "ops_user", "password": "ops-pw"},
            headers={"Origin": ORIGIN},
        )
        assert r.status_code == 503, f"OIDC password POST must be 503, got {r.status_code}: {r.text}"
        assert "set-cookie" not in r.headers, "no session may be minted when auth is unavailable"
        # error body must not leak provider internals / secrets
        assert "key" not in r.text.lower()


def test_oidc_login_route_redirects_to_idp(recorder, clock):
    """The real OIDC entry point: GET /api/auth/oidc/login -> 302 to the IdP."""
    app = _oidc_app(recorder, clock)
    with TestClient(app, base_url="https://testserver") as c:
        r = c.get("/api/auth/oidc/login", follow_redirects=False)
        assert r.status_code == 302, f"got {r.status_code}: {r.text}"
        assert r.headers["location"].startswith(mock.AUTHORIZE_ENDPOINT)


def test_local_mode_has_no_oidc_client_and_oidc_login_503(recorder, clock):
    """In local mode the OIDC route exists but is unavailable (no client)."""
    with _client(recorder, clock, auth_mode="local") as c:
        r = c.get("/api/auth/oidc/login", follow_redirects=False)
        assert r.status_code == 503, f"oidc login in local mode must 503, got {r.status_code}"
