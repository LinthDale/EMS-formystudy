"""Shared fixtures for BFF tests (PRD-0005 §9 GATE-1 security baseline).

All tests run against the real ASGI app via TestClient with the upstream
HTTP layer replaced by httpx.MockTransport (no docker, no network) and an
injectable fake clock (session expiry without sleeps, project_rules §11).
"""
from __future__ import annotations

import httpx
import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from bff.config import Settings
from bff.main import create_app

OPS_KEY = "test-ops-key-31337"
INGEST_KEY = "test-ingest-key-42424"
ORIGIN = "https://testserver"

MAX_LIFETIME_S = 28800   # 8 h
IDLE_TIMEOUT_S = 1800    # 30 min

# Fast argon2id params FOR TESTS ONLY (real cost lives in production hashes). The
# PHC string still embeds the algorithm id + params, so credentials.verify treats
# these exactly like any other argon2id hash — only the work factor differs.
_TEST_HASHER = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


def phc(pw: str) -> str:
    """Return a genuine (low-cost) argon2id PHC hash for a test password."""
    return _TEST_HASHER.hash(pw)


AUTH_USERS = ";".join([
    f"ops_user:{phc('ops-pw')}:ops",
    f"ing_user:{phc('ing-pw')}:ingest",
    f"view_user:{phc('view-pw')}:readonly",
])


class FakeClock:
    """Injectable wall clock so expiry tests never sleep."""

    def __init__(self, start: float = 1_000_000.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class UpstreamRecorder:
    """MockTransport handler standing in for device-service + PostgREST."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.fail_connect = False
        self.force_status: int | None = None  # make the upstream answer this status

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.fail_connect:
            raise httpx.ConnectError("upstream down", request=request)
        self.requests.append(request)
        if self.force_status is not None:
            return httpx.Response(self.force_status, json={"detail": "forced upstream status"})
        host = request.url.host
        if host == "device-upstream":
            return self._device_service(request)
        if host == "postgrest-upstream":
            return httpx.Response(200, json=[
                {"time": "2026-06-11T00:00:00Z", "device_id": "sim-001", "power_kw": 1.5},
            ])
        return httpx.Response(500, json={"detail": "unexpected upstream host"})

    def _device_service(self, request: httpx.Request) -> httpx.Response:
        """Stand-in for device-service :8002 (the routes the BFF proxies, openapi 1.3.0).

        GET /devices/{id} returns a record whose `gateway_id` drives the per-device
        measurement facade's device->domain resolution (ems-gateway -> electricity,
        kc-gateway/kc-ingest -> factory)."""
        method, path = request.method, request.url.path
        if method == "GET" and path == "/devices":
            return httpx.Response(200, json=[
                {"device_id": "sim-001", "status": "candidate", "ai_confidence": 0.42},
            ])
        if method == "POST" and path.endswith("/confirm"):
            return httpx.Response(200, json={"device_id": "sim-001", "status": "confirmed"})
        if method == "GET" and path.endswith("/signals"):
            return httpx.Response(200, json=[
                {"id": 1, "device_id": "sim-001", "signal_name": "power", "status": "active"},
            ])
        if method == "GET" and path.endswith("/human-review"):
            return httpx.Response(200, json={
                "device_id": "sim-001", "digest": {"summary": "candidate"},
                "summary_source": "llm",
            })
        if method == "POST" and path.endswith("/override"):
            return httpx.Response(200, json={"device_id": "sim-001", "status": "confirmed",
                                             "classified_by": "manual_override"})
        if method == "POST" and path.endswith("/reject"):
            return httpx.Response(200, json={"device_id": "sim-001", "status": "retired"})
        if method == "POST" and path.endswith("/ai-feedback"):
            return httpx.Response(201, json={"id": 7, "device_id": "sim-001",
                                             "verdict": "wrong_classification"})
        # GET /devices/{id} — the device record (gateway_id selects the domain)
        if method == "GET" and path.startswith("/devices/"):
            gateway = {
                "sim-001": "ems-gateway",      # electricity domain
                "plc-001": "kc-gateway",       # factory domain
                "kc-ing-001": "kc-ingest",     # factory domain
                "orphan-001": None,            # unresolvable domain
            }.get(path.rsplit("/", 1)[-1], "ems-gateway")
            return httpx.Response(200, json={
                "device_id": path.rsplit("/", 1)[-1], "status": "confirmed",
                "device_type": "electricity", "gateway_id": gateway,
            })
        return httpx.Response(404, json={"detail": "not found"})


def make_settings(**overrides) -> Settings:
    base = dict(
        device_service_url="http://device-upstream:8002",
        postgrest_url="http://postgrest-upstream:3000",
        public_origins=ORIGIN,
        ops_api_key=OPS_KEY,
        ingest_api_key=INGEST_KEY,
        auth_users=AUTH_USERS,
        session_max_lifetime_s=MAX_LIFETIME_S,
        session_idle_timeout_s=IDLE_TIMEOUT_S,
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


@pytest.fixture
def recorder() -> UpstreamRecorder:
    return UpstreamRecorder()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def client(recorder, clock):
    app = create_app(
        settings=make_settings(),
        upstream_transport=httpx.MockTransport(recorder.handler),
        clock=clock,
    )
    # https base_url: the Secure cookie must be presented over TLS-equivalent origin
    with TestClient(app, base_url="https://testserver") as c:
        yield c


def login(client: TestClient, username: str, password: str) -> httpx.Response:
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers={"Origin": ORIGIN},
    )
