"""PRD-0022 authenticated control fixture for real pipeline tests."""
# This module is loaded by integration/conftest.py; synthetic passwords stay in env.
import os
from uuid import uuid4
import httpx
import pytest


class SimulatorControl:
    def __init__(self, client, origin):
        self.client, self.origin = client, origin

    def state(self, simulator_id):
        response = self.client.get("/api/simulators/" + simulator_id)
        response.raise_for_status()
        state = response.json()
        assert state["available"], state
        return state

    def set(self, simulator_id, changes):
        state = self.state(simulator_id)
        response = self.client.post("/api/simulators/" + simulator_id + "/commands",
            headers={"Origin": self.origin},
            json=dict(request_id=str(uuid4()), expected_instance_id=state["instance_id"],
                      expected_revision=state["revision"], changes=changes,
                      reason="automated PRD-0022 pipeline verification"))
        response.raise_for_status()
        result = response.json()
        assert result["status"] == "succeeded", result
        return result


@pytest.fixture(scope="session")
def sim_control():
    url = os.getenv("EMS_BFF_URL", "http://localhost:8003")
    origin = os.getenv("EMS_BFF_ORIGIN", url)
    username, password = os.getenv("EMS_TEST_USERNAME"), os.getenv("EMS_TEST_PASSWORD")
    if not username or not password:
        pytest.skip("EMS_TEST_USERNAME/PASSWORD required for OPS control integration")
    with httpx.Client(base_url=url, timeout=10, trust_env=False) as client:
        response = client.post("/api/auth/login", headers={"Origin": origin},
                               json={"username": username, "password": password})
        assert response.status_code == 200, response.status_code
        yield SimulatorControl(client, origin)
        client.post("/api/auth/logout", headers={"Origin": origin})

@pytest.fixture
def restore_plc(sim_control):
    before = sim_control.state("plc-001")["settings"]
    try:
        yield
    finally:
        sim_control.set("plc-001", before)
