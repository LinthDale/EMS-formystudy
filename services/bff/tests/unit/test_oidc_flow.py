"""OIDC Authorization-Code + PKCE flow end-to-end against an in-process mock IdP
(ADR-024). Covers the happy path and every negative the threat model names:
bad signature, wrong aud/iss, expired, bad/missing nonce, bad/missing state
(CSRF/replay), unmapped claim, and discovery failure -> 502.

No real IdP and no network: the BFF's httpx client talks to the mock issuer over
httpx.MockTransport, and id-tokens are RS256-signed with an in-process key so the
JWKS signature path runs for real (project_rules §11: no sleeps, no real I/O).
"""
from __future__ import annotations

import asyncio
import urllib.parse

import httpx
import pytest
from fastapi.testclient import TestClient

from bff.config import Settings
from bff.main import create_app
from bff.oidc import OidcClient
from tests import oidc_fixtures as mock
from tests.conftest import make_settings


@pytest.fixture
def issuer() -> mock.MockIssuer:
    return mock.MockIssuer()


def _settings(**overrides) -> Settings:
    base = mock.oidc_overrides()
    base.update(overrides)
    return make_settings(**base)


def _build_client(issuer: mock.MockIssuer, settings: Settings) -> OidcClient:
    """Discover against the mock issuer transport (no network), returning a ready
    OidcClient whose own http talks only to the mock IdP."""

    async def _go() -> OidcClient:
        idp_http = httpx.AsyncClient(transport=httpx.MockTransport(issuer.handler))
        return await OidcClient.discover(settings, idp_http)

    return asyncio.run(_go())


def _app(issuer: mock.MockIssuer, recorder, clock, settings: Settings):
    oidc_client = _build_client(issuer, settings)
    return create_app(
        settings=settings,
        upstream_transport=httpx.MockTransport(recorder.handler),
        clock=clock,
        oidc_client=oidc_client,
    )


def _client(issuer, recorder, clock, **overrides) -> TestClient:
    settings = _settings(**overrides)
    app = _app(issuer, recorder, clock, settings)
    return TestClient(app, base_url="https://testserver")


def _start_login(c: TestClient) -> tuple[str, str]:
    """Hit /oidc/login, return (state, nonce) extracted from the redirect URL."""
    r = c.get("/api/auth/oidc/login", follow_redirects=False)
    assert r.status_code == 302, f"login must 302 to the IdP, got {r.status_code}"
    loc = r.headers["location"]
    q = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)
    assert q["code_challenge_method"] == ["S256"], "PKCE must be S256"
    assert "code_challenge" in q and q["code_challenge"][0]
    assert "set-cookie" not in r.headers, "no session cookie before callback"
    return q["state"][0], q["nonce"][0]


# --------------------------------------------------------------------------- #
# happy path
# --------------------------------------------------------------------------- #
def test_oidc_happy_path_valid_token_maps_role_and_mints_session(issuer, recorder, clock):
    with _client(issuer, recorder, clock) as c:
        state, nonce = _start_login(c)
        issuer.queue(issuer.make_id_token(nonce=nonce, groups=("ems-ops",)))
        r = c.get(
            "/api/auth/oidc/callback",
            params={"code": mock.AUTH_CODE, "state": state},
            follow_redirects=False,
        )
        assert r.status_code == 302, f"callback must 302 to the SPA, got {r.status_code}: {r.text}"
        assert r.headers["location"] == "/app", "lands on configured post-login path"
        assert "set-cookie" in r.headers, "a session cookie must be minted"

        # the minted session is the SAME server-side session as local login:
        # /api/auth/session returns the OIDC subject + mapped role.
        info = c.get("/api/auth/session")
        assert info.status_code == 200, info.text
        assert info.json() == {"username": "user-123", "role": "ops"}

        # the PKCE verifier was sent to the token endpoint; it never reached the
        # browser (only the challenge did, asserted in _start_login).
        token_req = next(rq for rq in issuer.requests if rq.url.path == "/token")
        form = mock.token_request_form(token_req)
        assert form["grant_type"] == "authorization_code"
        assert form["code"] == mock.AUTH_CODE
        assert form.get("code_verifier"), "PKCE verifier must be presented at exchange"
        assert form["client_id"] == mock.CLIENT_ID


def test_oidc_role_claim_list_maps_first_known_value(issuer, recorder, clock):
    with _client(issuer, recorder, clock) as c:
        state, nonce = _start_login(c)
        # an unmapped value precedes a mapped one -> the mapped one wins
        issuer.queue(issuer.make_id_token(nonce=nonce, groups=("other", "ems-view")))
        r = c.get(
            "/api/auth/oidc/callback",
            params={"code": mock.AUTH_CODE, "state": state},
            follow_redirects=False,
        )
        assert r.status_code == 302, r.text
        assert c.get("/api/auth/session").json()["role"] == "readonly"


# --------------------------------------------------------------------------- #
# negatives — token validation
# --------------------------------------------------------------------------- #
def test_oidc_bad_signature_rejected_401(issuer, recorder, clock):
    with _client(issuer, recorder, clock) as c:
        state, nonce = _start_login(c)
        issuer.queue(issuer.make_id_token(nonce=nonce, sign_with_rogue=True))
        r = c.get(
            "/api/auth/oidc/callback",
            params={"code": mock.AUTH_CODE, "state": state},
            follow_redirects=False,
        )
        assert r.status_code == 401, f"forged signature must 401, got {r.status_code}"
        assert "set-cookie" not in r.headers


def test_oidc_wrong_audience_rejected_401(issuer, recorder, clock):
    with _client(issuer, recorder, clock) as c:
        state, nonce = _start_login(c)
        issuer.queue(issuer.make_id_token(nonce=nonce, aud="some-other-client"))
        r = c.get(
            "/api/auth/oidc/callback",
            params={"code": mock.AUTH_CODE, "state": state},
            follow_redirects=False,
        )
        assert r.status_code == 401, f"wrong aud must 401, got {r.status_code}"


def test_oidc_wrong_issuer_rejected_401(issuer, recorder, clock):
    with _client(issuer, recorder, clock) as c:
        state, nonce = _start_login(c)
        issuer.queue(issuer.make_id_token(nonce=nonce, iss="https://evil.example.test"))
        r = c.get(
            "/api/auth/oidc/callback",
            params={"code": mock.AUTH_CODE, "state": state},
            follow_redirects=False,
        )
        assert r.status_code == 401, f"wrong iss must 401, got {r.status_code}"


def test_oidc_expired_token_rejected_401(issuer, recorder, clock):
    with _client(issuer, recorder, clock) as c:
        state, nonce = _start_login(c)
        # exp well in the past (beyond the 60s leeway)
        issuer.queue(issuer.make_id_token(nonce=nonce, exp_delta=-3600, iat_delta=-7200))
        r = c.get(
            "/api/auth/oidc/callback",
            params={"code": mock.AUTH_CODE, "state": state},
            follow_redirects=False,
        )
        assert r.status_code == 401, f"expired token must 401, got {r.status_code}"


def test_oidc_wrong_nonce_rejected_401(issuer, recorder, clock):
    with _client(issuer, recorder, clock) as c:
        state, _nonce = _start_login(c)
        # token carries a nonce the server never issued -> replay
        issuer.queue(issuer.make_id_token(nonce="attacker-supplied-nonce"))
        r = c.get(
            "/api/auth/oidc/callback",
            params={"code": mock.AUTH_CODE, "state": state},
            follow_redirects=False,
        )
        assert r.status_code == 401, f"nonce mismatch must 401, got {r.status_code}"


def test_oidc_missing_nonce_rejected_401(issuer, recorder, clock):
    with _client(issuer, recorder, clock) as c:
        state, _nonce = _start_login(c)
        issuer.queue(issuer.make_id_token(nonce=None, extra={}))  # no nonce claim
        r = c.get(
            "/api/auth/oidc/callback",
            params={"code": mock.AUTH_CODE, "state": state},
            follow_redirects=False,
        )
        assert r.status_code == 401, f"absent nonce must 401, got {r.status_code}"


# --------------------------------------------------------------------------- #
# negatives — state / CSRF
# --------------------------------------------------------------------------- #
def test_oidc_unknown_state_rejected_401_csrf(issuer, recorder, clock):
    with _client(issuer, recorder, clock) as c:
        _start_login(c)
        issuer.queue(issuer.make_id_token(nonce="whatever"))
        r = c.get(
            "/api/auth/oidc/callback",
            params={"code": mock.AUTH_CODE, "state": "never-issued-state"},
            follow_redirects=False,
        )
        assert r.status_code == 401, f"unknown state must 401, got {r.status_code}"
        assert "set-cookie" not in r.headers


def test_oidc_state_is_single_use(issuer, recorder, clock):
    with _client(issuer, recorder, clock) as c:
        state, nonce = _start_login(c)
        issuer.queue(issuer.make_id_token(nonce=nonce))
        r1 = c.get(
            "/api/auth/oidc/callback",
            params={"code": mock.AUTH_CODE, "state": state},
            follow_redirects=False,
        )
        assert r1.status_code == 302, r1.text
        # replaying the SAME state must fail (entry consumed)
        issuer.queue(issuer.make_id_token(nonce=nonce))
        r2 = c.get(
            "/api/auth/oidc/callback",
            params={"code": mock.AUTH_CODE, "state": state},
            follow_redirects=False,
        )
        assert r2.status_code == 401, f"replayed state must 401, got {r2.status_code}"


def test_oidc_missing_state_param_is_422(issuer, recorder, clock):
    with _client(issuer, recorder, clock) as c:
        _start_login(c)
        r = c.get(
            "/api/auth/oidc/callback",
            params={"code": mock.AUTH_CODE},
            follow_redirects=False,
        )
        assert r.status_code == 422, f"missing state must be 422, got {r.status_code}"


# --------------------------------------------------------------------------- #
# negatives — claim mapping
# --------------------------------------------------------------------------- #
def test_oidc_unmapped_claim_rejected_401_fail_closed(issuer, recorder, clock):
    with _client(issuer, recorder, clock) as c:
        state, nonce = _start_login(c)
        issuer.queue(issuer.make_id_token(nonce=nonce, groups=("unprivileged-group",)))
        r = c.get(
            "/api/auth/oidc/callback",
            params={"code": mock.AUTH_CODE, "state": state},
            follow_redirects=False,
        )
        assert r.status_code == 401, f"unmapped claim must 401 (fail closed), got {r.status_code}"
        assert "set-cookie" not in r.headers


def test_oidc_empty_role_claim_rejected_401(issuer, recorder, clock):
    with _client(issuer, recorder, clock) as c:
        state, nonce = _start_login(c)
        issuer.queue(issuer.make_id_token(nonce=nonce, groups=None))  # no groups claim
        r = c.get(
            "/api/auth/oidc/callback",
            params={"code": mock.AUTH_CODE, "state": state},
            follow_redirects=False,
        )
        assert r.status_code == 401, f"empty role claim must 401, got {r.status_code}"


# --------------------------------------------------------------------------- #
# negatives — token endpoint / discovery transport
# --------------------------------------------------------------------------- #
def test_oidc_token_endpoint_failure_maps_to_502(issuer, recorder, clock):
    with _client(issuer, recorder, clock) as c:
        state, nonce = _start_login(c)
        issuer.token_status = 400  # token endpoint rejects the exchange
        issuer.queue(issuer.make_id_token(nonce=nonce))
        r = c.get(
            "/api/auth/oidc/callback",
            params={"code": mock.AUTH_CODE, "state": state},
            follow_redirects=False,
        )
        assert r.status_code == 502, f"token-endpoint failure must 502, got {r.status_code}"


def test_oidc_discovery_failure_maps_to_502():
    """Discovery happens at OidcClient.discover; a failing IdP must raise an
    OidcError('discovery') which the route would surface as 502."""
    from bff.oidc import OidcError

    issuer = mock.MockIssuer()
    issuer.discovery_status = 503
    settings = _settings()

    async def _go() -> bool:
        idp_http = httpx.AsyncClient(transport=httpx.MockTransport(issuer.handler))
        try:
            await OidcClient.discover(settings, idp_http)
        except OidcError as exc:
            assert exc.kind == "discovery", exc.kind
            return True
        finally:
            await idp_http.aclose()
        return False

    assert asyncio.run(_go()), (
        "discovery against a failing IdP must raise OidcError('discovery')"
    )


# --------------------------------------------------------------------------- #
# JWKS rotation: a token signed by a freshly-rotated key still validates after a
# transparent JWKS refresh (the cached set is re-fetched once).
# --------------------------------------------------------------------------- #
def test_oidc_jwks_rotation_triggers_refresh_and_succeeds(issuer, recorder, clock):
    with _client(issuer, recorder, clock) as c:
        state, nonce = _start_login(c)
        # IdP rotates its signing key AFTER the BFF cached the old JWKS at startup
        issuer.rotate_signing_key()
        issuer.queue(issuer.make_id_token(nonce=nonce, groups=("ems-ops",)))
        r = c.get(
            "/api/auth/oidc/callback",
            params={"code": mock.AUTH_CODE, "state": state},
            follow_redirects=False,
        )
        assert r.status_code == 302, (
            f"rotated-key token must validate after a JWKS refresh, got {r.status_code}: {r.text}"
        )
        # the BFF fetched the JWKS a second time (initial discovery + the refresh)
        jwks_fetches = [rq for rq in issuer.requests if rq.url.path == "/jwks"]
        assert len(jwks_fetches) >= 2, "a JWKS refresh must have been attempted"


# --------------------------------------------------------------------------- #
# no token / secret ever leaks to the browser
# --------------------------------------------------------------------------- #
def test_oidc_error_bodies_never_leak_token_or_secret(issuer, recorder, clock):
    with _client(issuer, recorder, clock) as c:
        state, nonce = _start_login(c)
        issuer.queue(issuer.make_id_token(nonce=nonce, sign_with_rogue=True))
        r = c.get(
            "/api/auth/oidc/callback",
            params={"code": mock.AUTH_CODE, "state": state},
            follow_redirects=False,
        )
        assert mock.CLIENT_SECRET not in r.text
        assert "id_token" not in r.text.lower()
        assert "verifier" not in r.text.lower()
