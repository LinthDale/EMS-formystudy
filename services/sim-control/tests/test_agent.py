"""Shared agent: authenticated CAS, immutable receipt and bounded bodies."""
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sim_control.agent import ControlAgent, make_app

TOKEN = "t" * 40


@pytest.fixture
def setup():
    state = {"scenario": "day"}
    agent = ControlAgent("delta-sim-001", lambda: dict(state), state.update, TOKEN, clock=lambda: 100)
    with TestClient(make_app(agent)) as client:
        client.headers["Authorization"] = "Bearer " + TOKEN
        yield client, agent, state


def command(client, **overrides):
    state = client.get("/state").json()
    body = dict(request_id=str(uuid4()), expected_instance_id=state["instance_id"],
                expected_revision=state["revision"], changes={"scenario": "night"},
                reason="test", deadline=110.0)
    body.update(overrides)
    return body


def test_authorization_required_and_receipt_replays_once(setup):
    client, agent, state = setup
    assert client.get("/state", headers={"Authorization": "Bearer wrong"}).status_code == 401
    body = command(client)
    receipt = client.post("/apply", json=body)
    assert receipt.status_code == 200, receipt.text
    assert state["scenario"] == "night"
    assert receipt.json()["after"]["revision"] == 1
    assert client.post("/apply", json=body).json() == receipt.json()
    assert agent.revision == 1
    assert client.post("/apply", json={**body, "changes": {"scenario": "day"}}).status_code == 409
    assert client.get("/receipts/" + body["request_id"]).json() == receipt.json()


@pytest.mark.parametrize("override", [
    {"expected_instance_id": str(uuid4())}, {"expected_revision": 1},
    {"deadline": 99.0}, {"deadline": 1000.0},
])
def test_stale_or_expired_command_never_applies(setup, override):
    client, _, state = setup
    assert client.post("/apply", json=command(client, **override)).status_code in (409, 410)
    assert state["scenario"] == "day"


def test_bounds_receipt_capacity_and_body_size(setup):
    client, agent, state = setup
    assert client.post("/apply", json=command(client, changes={"scenario": "bad"})).status_code == 422
    assert client.post("/apply", content=b"x" * 4097).status_code == 413
    agent.max_receipts = 0
    assert client.post("/apply", json=command(client)).status_code == 429
    assert state["scenario"] == "day"


def test_blank_credential_refuses_control():
    agent = ControlAgent("delta-sim-001", lambda: {}, lambda _: None, "")
    with TestClient(make_app(agent)) as client:
        assert client.get("/state").status_code == 503
