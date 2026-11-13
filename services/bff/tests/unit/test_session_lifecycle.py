"""Session lifecycle — PRD-0005 §9.2 [必過]: HttpOnly/Secure/SameSite=Strict cookie,
server-side store, max lifetime + idle timeout, per-request validation,
role downgrade invalidates session (§9.1 [必過])."""
from __future__ import annotations

import re

from tests.conftest import IDLE_TIMEOUT_S, MAX_LIFETIME_S, ORIGIN, login

COOKIE_NAME = "ems_bff_session"


def test_login_valid_credentials_sets_secure_httponly_strict_cookie(client):
    r = login(client, "ops_user", "ops-pw")
    assert r.status_code == 200, f"login should succeed, got {r.status_code}: {r.text}"
    set_cookie = r.headers.get("set-cookie", "")
    assert COOKIE_NAME in set_cookie, f"missing session cookie, got: {set_cookie}"
    lowered = set_cookie.lower()
    assert "httponly" in lowered, f"cookie must be HttpOnly: {set_cookie}"
    assert "secure" in lowered, f"cookie must be Secure: {set_cookie}"
    assert "samesite=strict" in lowered, f"cookie must be SameSite=Strict: {set_cookie}"
    assert r.json().get("role") == "ops", f"login response should echo role, got {r.text}"


def test_login_wrong_password_returns_401_without_cookie(client):
    r = login(client, "ops_user", "WRONG")
    assert r.status_code == 401, f"got {r.status_code}"
    assert "set-cookie" not in r.headers, "no session cookie may be issued on failed login"


def test_login_unknown_user_returns_401(client):
    r = login(client, "nobody", "ops-pw")
    assert r.status_code == 401, f"got {r.status_code}"


def test_request_without_session_cookie_is_rejected_401(client):
    r = client.get("/api/devices")
    assert r.status_code == 401, f"unauthenticated request must be 401, got {r.status_code}"


def test_forged_session_cookie_is_rejected_401(client):
    client.cookies.set(COOKIE_NAME, "forged-session-id-000000000000")
    r = client.get("/api/devices")
    assert r.status_code == 401, f"forged session must be 401, got {r.status_code}"


def test_session_cookie_value_is_opaque(client):
    r = login(client, "ops_user", "ops-pw")
    value = client.cookies.get(COOKIE_NAME)
    assert value, "session cookie must be set"
    assert re.fullmatch(r"[A-Za-z0-9_-]{20,}", value), f"cookie must be an opaque token: {value}"
    assert "ops_user" not in value and "ops-pw" not in value, "cookie must not embed identity"
    assert r.status_code == 200


def test_idle_timeout_expires_session_after_inactivity(client, clock):
    login(client, "ops_user", "ops-pw")
    clock.advance(IDLE_TIMEOUT_S + 1)
    r = client.get("/api/devices")
    assert r.status_code == 401, f"idle-expired session must be 401, got {r.status_code}"


def test_activity_keeps_session_alive_until_max_lifetime(client, clock):
    login(client, "ops_user", "ops-pw")
    elapsed = 0
    step = 1000  # < idle timeout, so each request keeps the session warm
    while elapsed + step < MAX_LIFETIME_S:
        clock.advance(step)
        elapsed += step
        r = client.get("/api/devices")
        assert r.status_code == 200, f"active session died early at {elapsed}s: {r.status_code}"
    clock.advance(step)  # cross the absolute max lifetime
    r = client.get("/api/devices")
    assert r.status_code == 401, "session must die at max lifetime even with activity"


def test_logout_revokes_session(client):
    login(client, "ops_user", "ops-pw")
    r = client.post("/api/auth/logout", headers={"Origin": ORIGIN})
    assert r.status_code == 204, f"logout failed: {r.status_code} {r.text}"
    r = client.get("/api/devices")
    assert r.status_code == 401, "session must be unusable after logout"


def test_role_downgrade_invalidates_session(client):
    """§9.1 [必過]: role 降級時 session 失效."""
    login(client, "ops_user", "ops-pw")
    r = client.post("/api/auth/role", json={"role": "readonly"}, headers={"Origin": ORIGIN})
    assert r.status_code == 200, f"role change endpoint failed: {r.status_code} {r.text}"
    assert r.json().get("session_terminated") is True, f"downgrade must terminate session: {r.text}"
    r = client.get("/api/devices")
    assert r.status_code == 401, "downgraded session must be invalid, not re-scoped"


def test_same_role_change_keeps_session(client):
    login(client, "ops_user", "ops-pw")
    r = client.post("/api/auth/role", json={"role": "ops"}, headers={"Origin": ORIGIN})
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"
    assert r.json().get("session_terminated") is False, r.text
    r = client.get("/api/devices")
    assert r.status_code == 200, "no-op role change must not kill the session"


def test_session_endpoint_reports_identity_without_secrets(client):
    from tests.conftest import INGEST_KEY, OPS_KEY

    login(client, "view_user", "view-pw")
    r = client.get("/api/auth/session")
    assert r.status_code == 200, f"got {r.status_code}"
    body = r.json()
    assert body.get("role") == "readonly", body
    assert body.get("username") == "view_user", body
    assert set(body) == {"username", "role"}, f"session info must expose identity only: {body}"
    assert OPS_KEY not in r.text and INGEST_KEY not in r.text, "no key material in session info"
