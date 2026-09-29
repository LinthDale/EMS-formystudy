"""PRD-0018: bounded historical reads, no network."""
import pytest
from tests.conftest import login
pytestmark = pytest.mark.integration
BASE = "/api/devices/sim-001/"
RANGE = {"since": "2026-09-23T00:00:00Z", "until": "2026-09-24T00:00:00Z"}

@pytest.mark.parametrize("route", ["history", "records"])
def test_history_needs_ops(client, recorder, route):
    assert client.get(BASE + route, params=RANGE).status_code == 401
    login(client, "view_user", "view-pw")
    assert client.get(BASE + route, params=RANGE).status_code == 403
    assert not recorder.requests

@pytest.mark.parametrize("changes", [
    {"since": "bad"}, {"since": "2026-09-23"},
    {"until": "2026-09-23T00:00:00Z"}, {"until": "2026-10-24T00:00:00Z"},
    {"points": 59}, {"points": 1201}, {"domain": "factory"},
    {"since": "infinity"}, {"until": "2026-09-24T00:00:00"},
])
def test_history_rejects_before_upstream(client, recorder, changes):
    login(client, "ops_user", "ops-pw")
    r = client.get(BASE + "history", params=RANGE | changes)
    assert r.status_code == 422, r.text
    assert not recorder.requests

def test_history_translates_bounded_rpc(client, recorder):
    login(client, "ops_user", "ops-pw")
    r = client.get(BASE + "history", params=RANGE | {"points": 600})
    assert r.status_code == 200, r.text
    q = recorder.requests[-1]
    assert q.url.path == "/rpc/measurement_history"
    assert q.url.params["p_domain"] == "electricity"
    assert q.url.params["p_step_seconds"] == "144"
    assert "x-api-key" not in q.headers

def test_factory_history_uses_gateway(client, recorder):
    login(client, "ops_user", "ops-pw")
    assert client.get("/api/devices/plc-001/history", params=RANGE).status_code == 200
    assert recorder.requests[-1].url.params["p_domain"] == "factory"

def test_records_translates_page(client, recorder):
    login(client, "ops_user", "ops-pw")
    assert client.get(BASE + "records", params=RANGE | {"offset": 100, "limit": 100}).status_code == 200
    q = recorder.requests[-1]
    assert q.url.path == "/rpc/measurement_records"
    assert q.url.params["p_offset"] == "100"

@pytest.mark.parametrize("changes", [{"offset": -1}, {"offset": 1000001}, {"limit": 1001}, {"evil": 1}])
def test_records_bad_page(client, recorder, changes):
    login(client, "ops_user", "ops-pw")
    assert client.get(BASE + "records", params=RANGE | changes).status_code == 422
    assert not recorder.requests

def test_history_rejects_duplicates_and_unknown_domain(client, recorder):
    login(client, "ops_user", "ops-pw")
    assert client.get(BASE + "history", params=list(RANGE.items()) + [("since", RANGE["since"])]).status_code == 422
    assert not recorder.requests
    assert client.get("/api/devices/orphan-001/history", params=RANGE).status_code == 404
    assert len(recorder.requests) == 1
