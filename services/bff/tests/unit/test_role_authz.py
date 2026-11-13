"""role -> channel-key authz — PRD-0005 §9.1 [必過].

Key invariants:
- each session carries exactly one role; the BFF maps it to AT MOST one X-API-Key
- endpoint-level authz: an INGEST session must NOT reach an OPS route even though
  the BFF process itself holds the OPS key (the canonical negative case)
- key material never leaks into client-visible responses
"""
from __future__ import annotations

from tests.conftest import INGEST_KEY, OPS_KEY, ORIGIN, login


def test_ingest_session_blocked_from_ops_confirm_route(client, recorder):
    """THE negative case: BFF holds the OPS key, but an INGEST-role session
    must not be able to drive an OPS mutating endpoint through it."""
    login(client, "ing_user", "ing-pw")
    n_before = len(recorder.requests)
    r = client.post("/api/devices/sim-001/confirm", headers={"Origin": ORIGIN})
    assert r.status_code == 403, f"INGEST role must be blocked from OPS route, got {r.status_code}"
    assert len(recorder.requests) == n_before, "blocked request must never be forwarded upstream"


def test_ingest_session_blocked_from_privileged_device_list(client, recorder):
    login(client, "ing_user", "ing-pw")
    n_before = len(recorder.requests)
    r = client.get("/api/devices")
    assert r.status_code == 403, f"got {r.status_code}"
    assert len(recorder.requests) == n_before, "blocked request must never be forwarded upstream"


def test_readonly_session_blocked_from_confirm(client, recorder):
    login(client, "view_user", "view-pw")
    n_before = len(recorder.requests)
    r = client.post("/api/devices/sim-001/confirm", headers={"Origin": ORIGIN})
    assert r.status_code == 403, f"got {r.status_code}"
    assert len(recorder.requests) == n_before


def test_readonly_session_blocked_from_device_list(client):
    login(client, "view_user", "view-pw")
    r = client.get("/api/devices")
    assert r.status_code == 403, f"got {r.status_code}"


def test_ops_session_list_devices_injects_ops_key_upstream(client, recorder):
    login(client, "ops_user", "ops-pw")
    r = client.get("/api/devices")
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"
    upstream = recorder.requests[-1]
    assert upstream.url.host == "device-upstream", f"wrong upstream: {upstream.url}"
    assert upstream.headers.get("x-api-key") == OPS_KEY, "OPS key must be injected server-side"


def test_measurements_allowed_for_every_role_without_key_injection(client, recorder):
    for username, password in (("view_user", "view-pw"), ("ing_user", "ing-pw"), ("ops_user", "ops-pw")):
        r = login(client, username, password)
        assert r.status_code == 200, f"{username} login failed: {r.text}"
        r = client.get("/api/measurements/electricity")
        assert r.status_code == 200, f"{username} should read measurements, got {r.status_code}"
        upstream = recorder.requests[-1]
        assert upstream.url.host == "postgrest-upstream", f"wrong upstream: {upstream.url}"
        assert "x-api-key" not in upstream.headers, "no key channel may be spent on PostgREST reads"


def test_session_cookie_is_not_forwarded_upstream(client, recorder):
    login(client, "ops_user", "ops-pw")
    client.get("/api/devices")
    upstream = recorder.requests[-1]
    assert "cookie" not in upstream.headers, "browser cookies must not leak past the BFF"


def test_api_key_never_leaks_into_client_response(client):
    login(client, "ops_user", "ops-pw")
    r = client.get("/api/devices")
    haystack = r.text + "|".join(f"{k}:{v}" for k, v in r.headers.items())
    assert OPS_KEY not in haystack, "OPS key leaked to the client"
    assert INGEST_KEY not in haystack, "INGEST key leaked to the client"


def test_unknown_measurement_domain_rejected_404(client, recorder):
    login(client, "view_user", "view-pw")
    n_before = len(recorder.requests)
    r = client.get("/api/measurements/secrets")
    assert r.status_code == 404, f"got {r.status_code}"
    assert len(recorder.requests) == n_before, "invalid domain must not reach any upstream"


def test_invalid_device_id_rejected_before_upstream(client, recorder):
    login(client, "ops_user", "ops-pw")
    n_before = len(recorder.requests)
    r = client.post(f"/api/devices/{'a' * 65}/confirm", headers={"Origin": ORIGIN})
    assert r.status_code == 422, f"device_id over 64 chars must fail FR-322 regex, got {r.status_code}"
    assert len(recorder.requests) == n_before


def test_unknown_query_param_rejected_before_upstream(client, recorder):
    login(client, "ops_user", "ops-pw")
    n_before = len(recorder.requests)
    r = client.get("/api/devices", params={"status": "candidate", "evil": "1"})
    assert r.status_code == 422, f"non-allowlisted query param must be rejected, got {r.status_code}"
    assert len(recorder.requests) == n_before
