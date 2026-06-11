"""Boundary input validation (deny-by-default param allowlists, Guideline §4.3)
and the role -> channel-key map's fail-closed behavior (PRD-0005 §9.1).
"""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from bff.config import Settings
from bff.main import create_app
from bff.roles import Role, channel_key_for
from tests.conftest import INGEST_KEY, OPS_KEY, login, make_settings


# --- role -> channel-key map (pure function) ---------------------------------

def test_role_to_channel_key_map_is_at_most_one_channel_per_role():
    settings = make_settings()
    assert channel_key_for(Role.OPS, settings) == OPS_KEY
    assert channel_key_for(Role.INGEST, settings) == INGEST_KEY
    assert channel_key_for(Role.READONLY, settings) is None, "READONLY spends no channel"


def test_unconfigured_channel_key_resolves_to_none_fail_closed():
    settings = make_settings(ops_api_key="", ingest_api_key="")
    assert channel_key_for(Role.OPS, settings) is None
    assert channel_key_for(Role.INGEST, settings) is None


def test_ops_route_returns_503_when_channel_key_not_configured(recorder, clock):
    """Fail closed end-to-end: a valid OPS session must never ride on a missing
    or borrowed key — the route answers 503 and nothing goes upstream."""
    app = create_app(
        settings=make_settings(ops_api_key=""),
        upstream_transport=httpx.MockTransport(recorder.handler),
        clock=clock,
    )
    with TestClient(app, base_url="https://testserver") as c:
        login(c, "ops_user", "ops-pw")
        r = c.get("/api/devices")
        assert r.status_code == 503, f"missing channel key must be 503, got {r.status_code}"
        assert len(recorder.requests) == 0, "nothing may reach the upstream without its key"


# --- device list query params (allowlist mirror of openapi 1.3.0) ------------

@pytest.mark.parametrize(
    ("params", "why"),
    [
        ({"sort": "metadata"}, "sort field outside the 7-field allowlist"),
        ({"order": "sideways"}, "order must be asc|desc"),
        ({"limit": "0"}, "limit below 1"),
        ({"limit": "501"}, "limit above the device-list cap"),
        ({"limit": "abc"}, "non-numeric limit"),
        ({"offset": "-1"}, "negative offset"),
        ({"stale": "maybe"}, "stale must be true|false"),
        ({"status": "bad;DROP"}, "status value failing the FR-322 charset"),
        ({"type": "a" * 65}, "type value over 64 chars"),
    ],
)
def test_invalid_device_list_param_rejected_422_before_upstream(client, recorder, params, why):
    login(client, "ops_user", "ops-pw")
    n_before = len(recorder.requests)
    r = client.get("/api/devices", params=params)
    assert r.status_code == 422, f"{why}: expected 422, got {r.status_code}"
    assert len(recorder.requests) == n_before, f"{why}: must never reach the upstream"


def test_duplicate_device_list_param_rejected_422(client, recorder):
    login(client, "ops_user", "ops-pw")
    n_before = len(recorder.requests)
    r = client.get("/api/devices?status=candidate&status=confirmed")
    assert r.status_code == 422, f"duplicate param must be 422, got {r.status_code}"
    assert len(recorder.requests) == n_before


# --- measurement query params (PostgREST hop, §9.3) ---------------------------

@pytest.mark.parametrize(
    ("params", "why"),
    [
        ({"select": "*"}, "select is not allowlisted (no column projection control)"),
        ({"limit": "abc"}, "non-numeric limit"),
        ({"offset": "x"}, "non-numeric offset"),
        ({"device_id": "eq.sim 001;delete"}, "value failing the PostgREST-operator charset"),
        ({"order": "time.desc," + "a" * 130}, "value over the 128-char bound"),
    ],
)
def test_invalid_measurement_param_rejected_422_before_upstream(client, recorder, params, why):
    login(client, "view_user", "view-pw")
    n_before = len(recorder.requests)
    r = client.get("/api/measurements/electricity", params=params)
    assert r.status_code == 422, f"{why}: expected 422, got {r.status_code}"
    assert len(recorder.requests) == n_before, f"{why}: must never reach the upstream"


def test_settings_rejects_default_limit_above_max():
    with pytest.raises(Exception):
        Settings(
            _env_file=None,
            measurements_default_limit=2000,
            measurements_max_limit=1000,
        )
