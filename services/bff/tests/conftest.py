"""Shared fixtures for BFF tests (PRD-0005 §9 GATE-1 security baseline).

All tests run against the real ASGI app via TestClient with the upstream
HTTP layer replaced by httpx.MockTransport (no docker, no network) and an
injectable fake clock (session expiry without sleeps, project_rules §11).
"""
from __future__ import annotations

import hashlib

import httpx
import pytest
from fastapi.testclient import TestClient

from bff.config import Settings
from bff.main import create_app

OPS_KEY = "test-ops-key-31337"
INGEST_KEY = "test-ingest-key-42424"
ORIGIN = "https://testserver"

MAX_LIFETIME_S = 28800   # 8 h
IDLE_TIMEOUT_S = 1800    # 30 min


def sha(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


AUTH_USERS = ",".join([
    f"ops_user:{sha('ops-pw')}:ops",
    f"ing_user:{sha('ing-pw')}:ingest",
    f"view_user:{sha('view-pw')}:readonly",
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
            if request.method == "GET" and request.url.path == "/devices":
                return httpx.Response(200, json=[
                    {"device_id": "sim-001", "status": "candidate", "ai_confidence": 0.42},
                ])
            if request.method == "POST" and request.url.path.endswith("/confirm"):
                return httpx.Response(200, json={"device_id": "sim-001", "status": "confirmed"})
            return httpx.Response(404, json={"detail": "not found"})
        if host == "postgrest-upstream":
            return httpx.Response(200, json=[
                {"time": "2026-06-11T00:00:00Z", "device_id": "sim-001", "power_kw": 1.5},
            ])
        return httpx.Response(500, json={"detail": "unexpected upstream host"})


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
