"""Per-device measurement PRODUCT facade (PRD-0005 review P2, ADR-025):

    GET /api/devices/{device_id}/measurements
        ?since=<ISO8601>&limit=<1..1000, default 100>&order=<asc|desc, default desc>

The browser speaks product semantics only (since/limit/order) — it NEVER sees
PostgREST operators (eq./gte./order column). The BFF resolves the device's domain
from its device-service record (gateway_id -> electricity|factory view), then
translates the product params into PostgREST query params server-side. No key
channel is spent on the PostgREST read (web_anon view, §9.3); the device-record
lookup uses the OPS channel like any other privileged read.

AUTHZ: the facade is OPS-gated. device->domain resolution requires reading the
device record's gateway_id, and device-service exposes /devices/{id} only on the
OPS channel (§8.1: status/gateway are privileged). READONLY/INGEST have no OPS
channel (§9.1 role->key), so they cannot drive this lookup and are 403 here; the
legacy GET /api/measurements/{domain} (caller supplies the domain, no device
lookup) remains available to every role for the deprecation window.
"""
from __future__ import annotations

import pytest

from tests.conftest import INGEST_KEY, OPS_KEY, login

pytestmark = pytest.mark.integration


def _postgrest_hits(recorder):
    return [r for r in recorder.requests if r.url.host == "postgrest-upstream"]


def _device_lookups(recorder):
    return [
        r for r in recorder.requests
        if r.url.host == "device-upstream" and r.url.path == "/devices/sim-001"
    ]


# --- happy path: electricity device (gateway ems-gateway) -------------------

def test_facade_resolves_electricity_domain_and_translates_params(client, recorder):
    login(client, "ops_user", "ops-pw")
    r = client.get(
        "/api/devices/sim-001/measurements",
        params={"since": "2026-06-11T00:00:00Z", "limit": "50", "order": "asc"},
    )
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"

    # device record resolved first (OPS channel)
    lookups = _device_lookups(recorder)
    assert lookups, "facade must resolve the device record to derive its domain"
    assert lookups[-1].headers.get("x-api-key") == OPS_KEY

    # then the PostgREST electricity view, no key spent
    pg = _postgrest_hits(recorder)
    assert pg, "facade must query a PostgREST measurement view"
    last = pg[-1]
    assert last.url.path == "/electricity_measurements", str(last.url)
    assert "x-api-key" not in last.headers, "PostgREST read must spend no key channel"

    params = dict(last.url.params)
    assert params.get("device_id") == "eq.sim-001", f"device_id must be server-side eq.: {params}"
    assert params.get("time") == "gte.2026-06-11T00:00:00Z", f"since -> time=gte.: {params}"
    assert params.get("order") == "time.asc", f"order=asc -> time.asc: {params}"
    assert params.get("limit") == "50", params


def test_facade_resolves_factory_domain_for_kc_gateway_device(client, recorder):
    login(client, "ops_user", "ops-pw")
    r = client.get("/api/devices/plc-001/measurements")
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"
    last = _postgrest_hits(recorder)[-1]
    assert last.url.path == "/factory_measurements", (
        f"kc-gateway device must resolve to the factory view: {last.url}"
    )
    assert dict(last.url.params).get("device_id") == "eq.plc-001"


# --- defaults: limit=100, order=desc, no since -------------------------------

def test_facade_applies_default_limit_and_order_desc(client, recorder):
    login(client, "ops_user", "ops-pw")
    r = client.get("/api/devices/sim-001/measurements")
    assert r.status_code == 200, r.text
    params = dict(_postgrest_hits(recorder)[-1].url.params)
    assert params.get("limit") == "100", f"default limit must be 100: {params}"
    assert params.get("order") == "time.desc", f"default order must be desc: {params}"
    assert "time" not in params, "no since -> no time filter forwarded"
    assert params.get("device_id") == "eq.sim-001", params


# --- input validation --------------------------------------------------------

@pytest.mark.parametrize(
    ("params", "why"),
    [
        ({"since": "not-a-timestamp"}, "since must be ISO8601"),
        ({"since": "2026-13-99T99:99:99Z"}, "since must be a real ISO8601 instant"),
        ({"limit": "0"}, "limit below 1"),
        ({"limit": "1001"}, "limit above the 1000 cap"),
        ({"limit": "abc"}, "non-numeric limit"),
        ({"order": "sideways"}, "order must be asc|desc"),
        ({"evil": "1"}, "unknown query param"),
    ],
)
def test_facade_invalid_param_rejected_422_before_any_upstream(client, recorder, params, why):
    login(client, "ops_user", "ops-pw")
    n_before = len(recorder.requests)
    r = client.get("/api/devices/sim-001/measurements", params=params)
    assert r.status_code == 422, f"{why}: expected 422, got {r.status_code}"
    assert len(recorder.requests) == n_before, f"{why}: nothing may reach any upstream"


def test_facade_invalid_device_id_rejected_before_upstream(client, recorder):
    login(client, "ops_user", "ops-pw")
    n_before = len(recorder.requests)
    r = client.get(f"/api/devices/{'a' * 65}/measurements")
    assert r.status_code == 422, f"device_id over 64 chars must fail FR-322, got {r.status_code}"
    assert len(recorder.requests) == n_before


def test_facade_unresolvable_domain_maps_to_404(client, recorder):
    """A device whose gateway maps to no known measurement domain cannot be
    served a measurement view — 404, and the PostgREST hop is never made."""
    login(client, "ops_user", "ops-pw")
    r = client.get("/api/devices/orphan-001/measurements")
    assert r.status_code == 404, f"unresolvable domain must be 404, got {r.status_code}: {r.text}"
    assert not _postgrest_hits(recorder), "no measurement view query for an unresolvable domain"


# --- authz: OPS-gated (device-record lookup needs the OPS channel) -----------

def test_facade_blocked_for_readonly_role(client, recorder):
    login(client, "view_user", "view-pw")
    n_before = len(recorder.requests)
    r = client.get("/api/devices/sim-001/measurements")
    assert r.status_code == 403, (
        f"READONLY has no OPS channel for the device-record lookup, got {r.status_code}"
    )
    assert len(recorder.requests) == n_before, "blocked request must not reach any upstream"


def test_facade_blocked_for_ingest_role(client, recorder):
    login(client, "ing_user", "ing-pw")
    n_before = len(recorder.requests)
    r = client.get("/api/devices/sim-001/measurements")
    assert r.status_code == 403, f"INGEST has no OPS channel, got {r.status_code}"
    assert len(recorder.requests) == n_before


def test_facade_requires_a_session(client, recorder):
    r = client.get("/api/devices/sim-001/measurements")
    assert r.status_code == 401, f"unauthenticated read must be 401, got {r.status_code}"
    assert len(recorder.requests) == 0, "no upstream traffic without a session"


def test_facade_never_leaks_key_material(client, recorder):
    login(client, "ops_user", "ops-pw")
    r = client.get("/api/devices/sim-001/measurements")
    haystack = r.text + "|".join(f"{k}:{v}" for k, v in r.headers.items())
    assert OPS_KEY not in haystack and INGEST_KEY not in haystack, "key leaked to client"
