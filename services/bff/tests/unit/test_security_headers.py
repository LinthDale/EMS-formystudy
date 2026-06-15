"""Defensive response headers on /api responses — PRD-0005 §9.5 [必過]
(sec review M-1: extend the API-side header set beyond Cache-Control + nosniff).

These are the headers appropriate for a JSON API surface. The full HTML-page
header set (notably HSTS / Strict-Transport-Security and the script-src/connect-src
CSP for the SPA) lives on the TLS terminator / nginx in front of the static
bundle — see _stamp() in bff/security.py and threat-model T-22/§9.5.
"""
from __future__ import annotations

import pytest

from tests.conftest import login

# The exact header set _stamp() must put on every /api response.
EXPECTED_HEADERS = {
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
}


@pytest.mark.parametrize("header,value", sorted(EXPECTED_HEADERS.items()))
def test_api_get_response_carries_security_header(client, header, value):
    """Every defensive header is present (and exact) on a normal /api response."""
    login(client, "ops_user", "ops-pw")
    r = client.get("/api/devices")
    assert r.status_code == 200, f"sanity: GET /api/devices should be 200, got {r.status_code}"
    assert r.headers.get(header) == value, (
        f"missing/incorrect {header!r} on /api response: got {r.headers.get(header)!r}, "
        f"want {value!r}"
    )


@pytest.mark.parametrize("header,value", sorted(EXPECTED_HEADERS.items()))
def test_csrf_denied_response_carries_security_header(client, header, value):
    """The 403 CSRF-deny path also runs through _stamp() — same headers apply
    so an attacker-triggered error response is equally locked down."""
    login(client, "ops_user", "ops-pw")
    r = client.post("/api/devices/sim-001/confirm")  # no Origin -> 403 origin check
    assert r.status_code == 403, f"sanity: missing Origin should be 403, got {r.status_code}"
    assert r.headers.get(header) == value, (
        f"missing/incorrect {header!r} on CSRF-deny response: got {r.headers.get(header)!r}, "
        f"want {value!r}"
    )


def test_hsts_is_not_set_on_api_responses(client):
    """HSTS is deliberately NOT a BFF concern — it belongs on the TLS terminator /
    nginx. Asserting its absence keeps the boundary explicit (§9.5)."""
    login(client, "ops_user", "ops-pw")
    r = client.get("/api/devices")
    assert "strict-transport-security" not in {k.lower() for k in r.headers}, (
        "HSTS must be set by the TLS terminator/nginx, not the BFF"
    )
