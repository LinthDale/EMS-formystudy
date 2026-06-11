"""CSRF protection — PRD-0005 §9.4 [必過] (GATE-1 decision: SameSite=Strict cookie
+ Origin-header validation on every mutating /api route)."""
from __future__ import annotations

from tests.conftest import ORIGIN, login


def test_confirm_without_origin_header_rejected_403(client, recorder):
    login(client, "ops_user", "ops-pw")
    n_before = len(recorder.requests)
    r = client.post("/api/devices/sim-001/confirm")  # no Origin header
    assert r.status_code == 403, f"mutating request without Origin must be 403, got {r.status_code}"
    assert len(recorder.requests) == n_before, "request must never reach the upstream"


def test_confirm_with_foreign_origin_rejected_403(client, recorder):
    login(client, "ops_user", "ops-pw")
    n_before = len(recorder.requests)
    r = client.post("/api/devices/sim-001/confirm", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403, f"foreign Origin must be 403, got {r.status_code}"
    assert len(recorder.requests) == n_before, "request must never reach the upstream"


def test_confirm_with_allowed_origin_succeeds(client):
    login(client, "ops_user", "ops-pw")
    r = client.post("/api/devices/sim-001/confirm", headers={"Origin": ORIGIN})
    assert r.status_code == 200, f"allowed Origin should pass CSRF, got {r.status_code}: {r.text}"


def test_get_routes_do_not_require_origin(client):
    login(client, "ops_user", "ops-pw")
    r = client.get("/api/devices")  # no Origin header on a safe method
    assert r.status_code == 200, f"GET must not require Origin, got {r.status_code}"


def test_login_is_mutating_and_requires_allowed_origin(client):
    r = client.post("/api/auth/login", json={"username": "ops_user", "password": "ops-pw"})
    assert r.status_code == 403, f"login without Origin must be 403, got {r.status_code}"
    r = client.post(
        "/api/auth/login",
        json={"username": "ops_user", "password": "ops-pw"},
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403, f"login from foreign Origin must be 403, got {r.status_code}"


def test_api_responses_carry_no_store_and_nosniff_headers(client):
    login(client, "ops_user", "ops-pw")
    r = client.get("/api/devices")
    assert r.headers.get("cache-control") == "no-store", r.headers
    assert r.headers.get("x-content-type-options") == "nosniff", r.headers
