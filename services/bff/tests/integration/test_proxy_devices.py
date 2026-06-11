"""Proxied-call integration (upstream mocked at the transport boundary):
full login -> privileged list -> mutating confirm flow through the real ASGI
stack, asserting exactly what crosses the BFF -> upstream trust boundary."""
from __future__ import annotations

import pytest

from tests.conftest import OPS_KEY, ORIGIN, login

pytestmark = pytest.mark.integration


def test_full_proxy_flow_login_list_confirm(client, recorder):
    # login (no upstream traffic)
    r = login(client, "ops_user", "ops-pw")
    assert r.status_code == 200, r.text
    assert len(recorder.requests) == 0, "login must not touch any upstream"

    # privileged device list via device-service with OPS key injected
    r = client.get("/api/devices", params={"status": "candidate", "limit": "5"})
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"
    assert r.json()[0]["device_id"] == "sim-001", "upstream JSON must pass through"
    upstream = recorder.requests[-1]
    assert upstream.method == "GET", upstream.method
    assert str(upstream.url).startswith("http://device-upstream:8002/devices"), str(upstream.url)
    assert dict(upstream.url.params) == {"status": "candidate", "limit": "5"}, (
        f"only allowlisted, validated params may be forwarded: {dict(upstream.url.params)}"
    )
    assert upstream.headers.get("x-api-key") == OPS_KEY

    # mutating OPS route (CSRF satisfied by allowed Origin)
    r = client.post("/api/devices/sim-001/confirm", headers={"Origin": ORIGIN})
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"
    assert r.json()["status"] == "confirmed", r.text
    upstream = recorder.requests[-1]
    assert upstream.method == "POST", upstream.method
    assert upstream.url.path == "/devices/sim-001/confirm", str(upstream.url)
    assert upstream.headers.get("x-api-key") == OPS_KEY


def test_measurement_proxy_forwards_allowlisted_params_only(client, recorder):
    login(client, "view_user", "view-pw")
    r = client.get(
        "/api/measurements/electricity",
        params={"device_id": "eq.sim-001", "order": "time.desc", "limit": "50"},
    )
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"
    upstream = recorder.requests[-1]
    assert upstream.url.path == "/electricity_measurements", str(upstream.url)
    params = dict(upstream.url.params)
    assert params.get("device_id") == "eq.sim-001", params
    assert params.get("order") == "time.desc", params
    assert params.get("limit") == "50", params


def test_measurement_limit_is_capped_and_defaulted(client, recorder):
    login(client, "view_user", "view-pw")
    # over the cap -> rejected at the boundary
    r = client.get("/api/measurements/factory", params={"limit": "999999"})
    assert r.status_code == 422, f"limit above cap must be rejected, got {r.status_code}"
    # absent -> server-side default appended (deny unbounded reads)
    r = client.get("/api/measurements/factory")
    assert r.status_code == 200, r.text
    upstream = recorder.requests[-1]
    assert "limit" in dict(upstream.url.params), "a default limit must always be enforced"


def test_upstream_unreachable_maps_to_502_without_leaking(client, recorder):
    login(client, "ops_user", "ops-pw")
    recorder.fail_connect = True
    r = client.get("/api/devices")
    assert r.status_code == 502, f"got {r.status_code}"
    assert OPS_KEY not in r.text, "error path must not leak key material"
    assert "device-upstream" not in r.text, "error path should not leak internal topology"
