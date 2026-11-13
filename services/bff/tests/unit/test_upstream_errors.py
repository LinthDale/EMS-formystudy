"""Upstream error mapping across the BFF trust boundary (bff/upstream.py).

Invariants: upstream auth failures are the BFF's OWN misconfiguration (502, never
relayed as 401/403 to the browser); 5xx and unexpected statuses map to a generic
502; legitimate client errors (4xx contract answers) pass through; nothing about
keys or internal topology ever reaches the client.
"""
from __future__ import annotations

from tests.conftest import INGEST_KEY, OPS_KEY, login


def _ops_client(client):
    r = login(client, "ops_user", "ops-pw")
    assert r.status_code == 200, f"login failed: {r.text}"
    return client


def test_upstream_401_means_bff_key_misconfig_maps_to_502(client, recorder):
    _ops_client(client)
    recorder.force_status = 401
    r = client.get("/api/devices")
    assert r.status_code == 502, f"upstream 401 must become 502, got {r.status_code}"
    assert "401" not in r.text, "upstream auth detail must not be relayed"
    assert OPS_KEY not in r.text and INGEST_KEY not in r.text, "no key material in error body"


def test_upstream_403_means_bff_key_misconfig_maps_to_502(client, recorder):
    _ops_client(client)
    recorder.force_status = 403
    r = client.get("/api/devices")
    assert r.status_code == 502, f"upstream 403 must become 502, got {r.status_code}"


def test_upstream_5xx_maps_to_generic_502(client, recorder):
    _ops_client(client)
    recorder.force_status = 503
    r = client.get("/api/devices")
    assert r.status_code == 502, f"upstream 503 must become 502, got {r.status_code}"
    assert "device-upstream" not in r.text, "internal topology must not leak"


def test_unexpected_upstream_status_maps_to_502(client, recorder):
    _ops_client(client)
    recorder.force_status = 302  # a proxy must never relay a redirect off-origin
    r = client.get("/api/devices")
    assert r.status_code == 502, f"unexpected upstream 302 must become 502, got {r.status_code}"
    assert "location" not in r.headers, "redirect headers must not pass through"


def test_contract_4xx_passes_through_unchanged(client, recorder):
    _ops_client(client)
    recorder.force_status = 429  # e.g. device-service per-key rate limit (AC-7)
    r = client.get("/api/devices")
    assert r.status_code == 429, f"contract 429 must pass through, got {r.status_code}"


def test_healthz_is_public_and_session_free(client, recorder):
    r = client.get("/healthz")
    assert r.status_code == 200, f"got {r.status_code}"
    assert r.json() == {"status": "ok"}, r.text
    assert len(recorder.requests) == 0, "healthz must not fan out to upstreams"
