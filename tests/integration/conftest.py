"""Integration test fixtures — all tests here need `docker compose up -d`."""
import os
import time

import httpx
import psycopg2
import pytest

SIMULATOR_URL = os.getenv("EMS_SIMULATOR_URL", "http://localhost:8001")
POSTGREST_URL = os.getenv("EMS_POSTGREST_URL", "http://localhost:3001")
DB_DSN = os.getenv(
    "EMS_DB_DSN",
    "host=localhost port=5432 dbname=ems user=postgres password=postgres sslmode=disable",
)
PLC_HOST = os.getenv("EMS_PLC_HOST", "localhost")
PLC_PORT = int(os.getenv("EMS_PLC_PORT", "5021"))


def _http_reachable(url: str) -> bool:
    try:
        return httpx.get(url, timeout=3.0).status_code < 500
    except Exception:
        return False


def _db_reachable(dsn: str) -> bool:
    try:
        conn = psycopg2.connect(dsn)
        conn.close()
        return True
    except Exception:
        return False


# ── session-scoped "skip if not up" fixtures ─────────────────────────────────

@pytest.fixture(scope="session")
def db_conn():
    if not _db_reachable(DB_DSN):
        pytest.skip("TimescaleDB not reachable — run: docker compose up -d")
    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def simulator_client():
    if not _http_reachable(f"{SIMULATOR_URL}/health"):
        pytest.skip("Simulator not reachable — run: docker compose up -d")
    return httpx.Client(base_url=SIMULATOR_URL, timeout=10.0)


@pytest.fixture(scope="session")
def postgrest_client():
    if not _http_reachable(POSTGREST_URL):
        pytest.skip("PostgREST not reachable — run: docker compose up -d")
    return httpx.Client(
        base_url=POSTGREST_URL,
        headers={"Accept": "application/json"},
        timeout=10.0,
    )


@pytest.fixture(scope="session")
def plc_client():
    from pymodbus.client import ModbusTcpClient
    c = ModbusTcpClient(PLC_HOST, port=PLC_PORT)
    if not c.connect():
        pytest.skip(f"kc-modbus-sim not reachable at {PLC_HOST}:{PLC_PORT}")
    yield c
    c.close()


# ── helpers ───────────────────────────────────────────────────────────────────

def wait_for(condition_fn, *, timeout: float = 30.0, interval: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition_fn():
            return True
        time.sleep(interval)
    return False


@pytest.fixture
def reset_fault_mode(simulator_client):
    """Ensure fault_mode is cleared after any test that injects a fault."""
    yield
    simulator_client.post("/inject-fault", params={"mode": "none"})
