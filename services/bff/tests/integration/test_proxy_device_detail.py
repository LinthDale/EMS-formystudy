"""FR-50x deferred device proxy routes (PRD-0005 §8.1) through the real ASGI
stack with the upstream mocked at the transport boundary.

Each route mirrors the list/confirm template in routes/devices.py: OPS-gated,
device_id path-validated (FR-322 regex) BEFORE anything goes upstream, X-API-Key
injected server-side, errors mapped per upstream.py, no key/topology leak.
"""
from __future__ import annotations

import pytest

from tests.conftest import INGEST_KEY, OPS_KEY, ORIGIN, login

pytestmark = pytest.mark.integration


# --- FR-501 device detail (GET /api/devices/{id}) ---------------------------

def test_ops_device_detail_proxies_with_key_injected(client, recorder):
    login(client, "ops_user", "ops-pw")
    r = client.get("/api/devices/sim-001")
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"
    assert r.json()["device_id"] == "sim-001", r.text
    upstream = recorder.requests[-1]
    assert upstream.method == "GET"
    assert upstream.url.path == "/devices/sim-001", str(upstream.url)
    assert upstream.headers.get("x-api-key") == OPS_KEY


def test_device_detail_invalid_id_rejected_before_upstream(client, recorder):
    login(client, "ops_user", "ops-pw")
    n_before = len(recorder.requests)
    r = client.get(f"/api/devices/{'a' * 65}")
    assert r.status_code == 422, f"device_id over 64 chars must fail FR-322, got {r.status_code}"
    assert len(recorder.requests) == n_before, "blocked request must never reach upstream"


def test_device_detail_blocked_for_ingest_role(client, recorder):
    login(client, "ing_user", "ing-pw")
    n_before = len(recorder.requests)
    r = client.get("/api/devices/sim-001")
    assert r.status_code == 403, f"INGEST must not read OPS device detail, got {r.status_code}"
    assert len(recorder.requests) == n_before


def test_device_detail_blocked_for_readonly_role(client, recorder):
    login(client, "view_user", "view-pw")
    n_before = len(recorder.requests)
    r = client.get("/api/devices/sim-001")
    assert r.status_code == 403, f"READONLY must not read OPS device detail, got {r.status_code}"
    assert len(recorder.requests) == n_before


# --- FR-501 signals (GET /api/devices/{id}/signals) -------------------------

def test_ops_device_signals_proxies_with_key_injected(client, recorder):
    login(client, "ops_user", "ops-pw")
    r = client.get("/api/devices/sim-001/signals")
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"
    upstream = recorder.requests[-1]
    assert upstream.url.path == "/devices/sim-001/signals", str(upstream.url)
    assert upstream.headers.get("x-api-key") == OPS_KEY


def test_device_signals_blocked_for_ingest_role(client, recorder):
    login(client, "ing_user", "ing-pw")
    n_before = len(recorder.requests)
    r = client.get("/api/devices/sim-001/signals")
    assert r.status_code == 403, f"got {r.status_code}"
    assert len(recorder.requests) == n_before


# --- FR-511 human-review digest (GET /api/devices/{id}/human-review) --------

def test_ops_human_review_digest_proxies_with_key_injected(client, recorder):
    login(client, "ops_user", "ops-pw")
    r = client.get("/api/devices/sim-001/human-review")
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"
    assert r.json()["device_id"] == "sim-001", r.text
    upstream = recorder.requests[-1]
    assert upstream.method == "GET"
    assert upstream.url.path == "/devices/sim-001/human-review", str(upstream.url)
    assert upstream.headers.get("x-api-key") == OPS_KEY


def test_human_review_blocked_for_readonly_role(client, recorder):
    login(client, "view_user", "view-pw")
    n_before = len(recorder.requests)
    r = client.get("/api/devices/sim-001/human-review")
    assert r.status_code == 403, f"got {r.status_code}"
    assert len(recorder.requests) == n_before


# --- FR-512 override (POST /api/devices/{id}/override) ----------------------

def test_ops_override_forwards_body_and_key(client, recorder):
    login(client, "ops_user", "ops-pw")
    body = {"device_type": "electricity", "signals": [{"signal_name": "power"}]}
    r = client.post("/api/devices/sim-001/override", json=body, headers={"Origin": ORIGIN})
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"
    assert r.json()["classified_by"] == "manual_override", r.text
    upstream = recorder.requests[-1]
    assert upstream.method == "POST"
    assert upstream.url.path == "/devices/sim-001/override", str(upstream.url)
    assert upstream.headers.get("x-api-key") == OPS_KEY
    assert b"electricity" in upstream.content, "request body must be forwarded upstream"


def test_override_blocked_for_ingest_role_no_upstream(client, recorder):
    login(client, "ing_user", "ing-pw")
    n_before = len(recorder.requests)
    r = client.post("/api/devices/sim-001/override",
                    json={"device_type": "electricity"}, headers={"Origin": ORIGIN})
    assert r.status_code == 403, f"INGEST must not drive OPS override, got {r.status_code}"
    assert len(recorder.requests) == n_before, "blocked mutating request must not be forwarded"


def test_override_without_origin_blocked_by_csrf(client, recorder):
    login(client, "ops_user", "ops-pw")
    n_before = len(recorder.requests)
    r = client.post("/api/devices/sim-001/override", json={"device_type": "electricity"})
    assert r.status_code == 403, f"missing Origin must fail CSRF, got {r.status_code}"
    assert len(recorder.requests) == n_before


def test_override_invalid_device_id_rejected_before_upstream(client, recorder):
    login(client, "ops_user", "ops-pw")
    n_before = len(recorder.requests)
    r = client.post(f"/api/devices/{'a' * 65}/override",
                    json={"device_type": "electricity"}, headers={"Origin": ORIGIN})
    assert r.status_code == 422, f"got {r.status_code}"
    assert len(recorder.requests) == n_before


# --- FR-512 reject (POST /api/devices/{id}/reject) --------------------------

def test_ops_reject_proxies_with_key_injected(client, recorder):
    login(client, "ops_user", "ops-pw")
    r = client.post("/api/devices/sim-001/reject", headers={"Origin": ORIGIN})
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"
    assert r.json()["status"] == "retired", r.text
    upstream = recorder.requests[-1]
    assert upstream.method == "POST"
    assert upstream.url.path == "/devices/sim-001/reject", str(upstream.url)
    assert upstream.headers.get("x-api-key") == OPS_KEY


def test_reject_blocked_for_readonly_role(client, recorder):
    login(client, "view_user", "view-pw")
    n_before = len(recorder.requests)
    r = client.post("/api/devices/sim-001/reject", headers={"Origin": ORIGIN})
    assert r.status_code == 403, f"got {r.status_code}"
    assert len(recorder.requests) == n_before


# --- FR-513 corrections (POST /api/devices/{id}/corrections -> /ai-feedback) -

def test_ops_corrections_forwards_to_ai_feedback_with_body_and_key(client, recorder):
    login(client, "ops_user", "ops-pw")
    body = {"verdict": "wrong_classification", "human_explanation": "should be electricity"}
    r = client.post("/api/devices/sim-001/corrections", json=body, headers={"Origin": ORIGIN})
    assert r.status_code == 201, f"got {r.status_code}: {r.text}"
    upstream = recorder.requests[-1]
    assert upstream.method == "POST"
    assert upstream.url.path == "/devices/sim-001/ai-feedback", (
        f"FR-513 corrections must map to the device-service /ai-feedback endpoint: {upstream.url}"
    )
    assert upstream.headers.get("x-api-key") == OPS_KEY
    assert b"wrong_classification" in upstream.content, "correction body must be forwarded"


def test_corrections_blocked_for_ingest_role_no_upstream(client, recorder):
    login(client, "ing_user", "ing-pw")
    n_before = len(recorder.requests)
    r = client.post("/api/devices/sim-001/corrections",
                    json={"verdict": "wrong_classification", "human_explanation": "x"},
                    headers={"Origin": ORIGIN})
    assert r.status_code == 403, f"got {r.status_code}"
    assert len(recorder.requests) == n_before


def test_corrections_does_not_leak_key_on_error(client, recorder):
    login(client, "ops_user", "ops-pw")
    recorder.force_status = 401  # upstream auth failure -> BFF misconfig -> 502
    r = client.post("/api/devices/sim-001/corrections",
                    json={"verdict": "wrong_classification", "human_explanation": "x"},
                    headers={"Origin": ORIGIN})
    assert r.status_code == 502, f"got {r.status_code}"
    assert OPS_KEY not in r.text and INGEST_KEY not in r.text, "no key material in error body"
