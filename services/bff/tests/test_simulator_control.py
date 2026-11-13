"""PRD-0022: durable, authenticated simulator control (ASGI + SQLite integration)."""
from uuid import uuid4
import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from bff.main import create_app
from tests.account_fakes import FakeAccounts
from tests.conftest import AUTH_USERS
from bff.simulator_control.audit import Audit, Conflict, Unavailable
from bff.simulator_control.contracts import Command, validate_changes, command_hash
from .conftest import make_settings, login, ORIGIN

INSTANCE = str(uuid4())


@pytest.fixture
def anyio_backend():
    return "asyncio"


def command(**overrides):
    body = dict(request_id=str(uuid4()), expected_instance_id=INSTANCE,
                expected_revision=0, changes={"scenario": "night"}, reason="integration test")
    body.update(overrides)
    return body


class Target:
    def __init__(self):
        self.state = dict(simulator_id="delta-sim-001", instance_id=INSTANCE,
                          revision=0, settings={"scenario": "day"})
        self.calls = 0
        self.receipt = None
        self.timeout = False

    def handler(self, req):
        assert req.headers["authorization"] == "Bearer " + "s" * 40
        if req.url.path == "/state":
            return httpx.Response(200, json=self.state)
        if req.url.path.startswith("/receipts/"):
            return httpx.Response(200 if self.receipt else 404, json=self.receipt or {})
        body = json.loads(req.content)
        self.calls += 1
        before = json.loads(json.dumps(self.state))
        self.state["settings"].update(body["changes"])
        self.state["revision"] += 1
        self.receipt = dict(request_id=body["request_id"],
                            command_hash=command_hash("delta-sim-001", Command(**{k:v for k,v in body.items() if k != "deadline"})), before=before,
                            after=self.state.copy(), changes=body["changes"])
        if self.timeout:
            raise httpx.ReadTimeout("lost response")
        return httpx.Response(200, json=self.receipt)


@pytest.fixture
def control(tmp_path):
    target = Target()
    settings = make_settings(sim_control_enabled=True, sim_control_token="s" * 40,
                             sim_control_db=str(tmp_path / "audit.sqlite3"))
    app = create_app(account_repository=FakeAccounts(AUTH_USERS), settings=settings, simulator_transport=httpx.MockTransport(target.handler))
    with TestClient(app, base_url=ORIGIN) as client:
        yield client, target, app


def post(client, body):
    return client.post("/api/simulators/delta-sim-001/commands", json=body,
                       headers={"Origin": ORIGIN})


def test_only_ops_with_origin_can_control(control):
    client, target, _ = control
    assert post(client, command()).status_code == 401
    login(client, "view_user", "view-pw")
    assert post(client, command()).status_code == 403
    login(client, "ops_user", "ops-pw")
    assert client.post("/api/simulators/delta-sim-001/commands", json=command()).status_code == 403
    assert target.calls == 0


def test_success_has_actor_before_after_and_persistent_uuid(control):
    client, target, app = control
    login(client, "ops_user", "ops-pw")
    body = command()
    first = post(client, body)
    assert first.status_code == 200, first.text
    op = first.json()
    assert op["status"] == "succeeded"
    assert op["actor"] == "ops_user"
    assert op["before"]["settings"] == {"scenario": "day"}
    assert op["after"]["settings"] == {"scenario": "night"}
    assert post(client, body).json() == op
    assert target.calls == 1
    assert post(client, {**body, "reason": "different"}).status_code == 409
    rows = client.get("/api/simulators/operations").json()["items"]
    assert rows[0]["request_id"] == body["request_id"]
    assert client.get("/api/simulators/operations/" + body["request_id"]).json() == op


def test_timeout_blocks_next_command_and_receipt_reconciles_without_resend(control):
    client, target, _ = control
    login(client, "ops_user", "ops-pw")
    target.timeout = True
    body = command()
    op = post(client, body).json()
    assert op["status"] == "outcome_unknown"
    assert post(client, command(expected_revision=1)).status_code == 409
    result = client.post("/api/simulators/operations/" + body["request_id"] + "/reconcile",
                         json={"reason": "check original receipt"}, headers={"Origin": ORIGIN})
    assert result.json()["status"] == "succeeded", result.text
    assert target.calls == 1
    assert len(result.json()["events"]) >= 2


@pytest.mark.parametrize("changes", [{"scenario": "explode"}, {"host": "example.com"},
                                     {"scenario": None}, {}, {"scenario": 1}])
def test_invalid_changes_never_dispatch(control, changes):
    client, target, _ = control
    login(client, "ops_user", "ops-pw")
    assert post(client, command(changes=changes)).status_code == 422
    assert target.calls == 0


def test_stale_revision_records_failure_without_dispatch(control):
    client, target, _ = control
    login(client, "ops_user", "ops-pw")
    result = post(client, command(expected_revision=99))
    assert result.json()["status"] == "failed"
    assert result.json()["error"] == "state_conflict"
    assert target.calls == 0


def test_disk_failure_fails_closed(control, monkeypatch):
    client, target, app = control
    login(client, "ops_user", "ops-pw")
    def full(*args, **kwargs):
        raise sqlite3.OperationalError("disk full")
    monkeypatch.setattr(app.state.simulators.audit, "reserve", full)
    assert post(client, command()).status_code == 503
    assert target.calls == 0


def test_audit_restart_recovers_pending_and_forbids_mutation(tmp_path):
    path = str(tmp_path / "audit.sqlite3")
    body = Command(**command())
    audit = Audit(path)
    audit.reserve("ops", "delta-sim-001", body)
    with pytest.raises(Unavailable):
        Audit(path)
    audit.close()
    audit = Audit(path)
    assert audit.get(str(body.request_id))["status"] == "outcome_unknown"
    assert audit.reserve("ops", "delta-sim-001", body)["request_id"] == str(body.request_id)
    with pytest.raises(Conflict):
        audit.reserve("other", "delta-sim-001", body)
    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM operations")
    audit.close()


@pytest.mark.parametrize("sim,changes", [
    ("sim-001", {"period_seconds": 0}), ("sim-001", {"power_factor": float("nan")}),
    ("plc-001", {"motor_speed": -1}), ("plc-001", {"pump_on": 1}),
    ("sensor-001", {"interval_seconds": 0}), ("sensor-001", {"enabled": "yes"}),
])
def test_control_values_are_typed_and_bounded(sim, changes):
    with pytest.raises(ValueError):
        validate_changes(sim, changes)

def test_unknown_missing_receipt_stays_blocked_until_new_instance(control):
    client, target, _ = control
    login(client, "ops_user", "ops-pw")
    target.timeout = True
    body = command()
    assert post(client, body).json()["status"] == "outcome_unknown"
    target.receipt = None
    url = "/api/simulators/operations/" + body["request_id"] + "/reconcile"
    kwargs = dict(json={"reason": "verify restart"}, headers={"Origin": ORIGIN})
    still_unknown = client.post(url, **kwargs).json()
    assert still_unknown["resolved"] is False
    target.state["instance_id"] = str(uuid4())
    resolved = client.post(url, **kwargs).json()
    assert resolved["status"] == "outcome_unknown"
    assert resolved["resolved"] is True
    assert resolved["reconciled_by"] == "ops_user"
    assert target.calls == 1


def test_invalid_receipt_cannot_claim_success(control):
    client, target, _ = control
    login(client, "ops_user", "ops-pw")
    real = target.handler
    def handler(req):
        response = real(req)
        if req.url.path == "/apply":
            data = response.json()
            data["command_hash"] = "0" * 64
            return httpx.Response(200, json=data)
        return response
    # MockTransport retains its callable; modify it explicitly in this test seam.
    _.state.simulators.client._transport.handler = handler
    assert post(client, command()).json()["status"] == "outcome_unknown"


def test_invalid_routes_query_and_large_body_are_rejected(control):
    client, target, _ = control
    login(client, "ops_user", "ops-pw")
    assert client.get("/api/simulators/not-real").status_code == 422
    assert client.get("/api/simulators?host=evil").status_code == 422
    assert client.get("/api/simulators/operations?limit=101").status_code == 422
    assert client.get("/api/simulators/operations?unknown=1").status_code == 422
    assert client.get("/api/simulators/operations/" + str(uuid4())).status_code == 404
    assert client.post("/api/simulators/delta-sim-001/commands", content=b"x" * 4097,
                       headers={"Origin": ORIGIN}).status_code == 413
    assert target.calls == 0


def test_capacity_stops_new_commands_but_keeps_replays(tmp_path):
    audit = Audit(str(tmp_path / "audit.db"), max_commands=1)
    body = Command(**command())
    audit.reserve("ops", "delta-sim-001", body)
    assert audit.reserve("ops", "delta-sim-001", body)["status"] == "pending"
    with pytest.raises(Unavailable):
        audit.reserve("ops", "delta-sim-001", Command(**command()))
    audit.close()


def test_disabled_feature_and_short_token_fail_closed(client):
    login(client, "ops_user", "ops-pw")
    assert client.get("/api/simulators").status_code == 503
    with pytest.raises(ValueError):
        make_settings(sim_control_enabled=True, sim_control_token="short")


@pytest.mark.anyio
async def test_concurrent_replay_and_new_command_never_dispatch_twice():
    import asyncio
    from bff.simulator_control.manager import Controller
    entered, release = asyncio.Event(), asyncio.Event()
    target = Target()

    async def handler(req):
        if req.url.path == "/apply":
            entered.set()
            await release.wait()
        return target.handler(req)

    audit = Audit(":memory:")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                 headers={"Authorization": "Bearer " + "s" * 40}) as http:
        manager = Controller(audit, http)
        body = Command(**command())
        running = asyncio.create_task(manager.execute("ops", "delta-sim-001", body))
        await entered.wait()
        assert (await manager.execute("ops", "delta-sim-001", body))["status"] == "pending"
        with pytest.raises(Conflict):
            await manager.execute("ops", "delta-sim-001", Command(**command()))
        with pytest.raises(Conflict):
            await manager.reconcile(str(body.request_id), "ops", "still running")
        release.set()
        assert (await running)["status"] == "succeeded"
        assert target.calls == 1
    audit.close()


@pytest.mark.anyio
@pytest.mark.parametrize("cancel_path,expected", [("/state", "failed"), ("/apply", "outcome_unknown")])
async def test_cancel_before_and_after_dispatch_are_distinguished(cancel_path, expected):
    import asyncio
    from bff.simulator_control.manager import Controller
    target = Target()
    async def handler(req):
        if req.url.path == cancel_path:
            raise asyncio.CancelledError()
        return target.handler(req)
    audit = Audit(":memory:")
    body = Command(**command())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                 headers={"Authorization": "Bearer " + "s" * 40}) as http:
        manager = Controller(audit, http)
        with pytest.raises(asyncio.CancelledError):
            await manager.execute("ops", "delta-sim-001", body)
        assert audit.get(str(body.request_id))["status"] == expected
        assert audit.blocked("delta-sim-001") is (expected == "outcome_unknown")
    audit.close()


@pytest.mark.anyio
@pytest.mark.parametrize("path,expected", [("/state", "failed"), ("/apply", "outcome_unknown")])
@pytest.mark.parametrize("mode", ["oversized", "slow", "encoded"])
async def test_unbounded_target_response_stops_at_limit_or_total_timeout(path, expected, mode, monkeypatch):
    import asyncio
    from bff.simulator_control import manager as module
    monkeypatch.setattr(module, "HOP_TIMEOUT_S", .04)
    target = Target()
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(10):
                if mode == "slow":
                    await asyncio.sleep(.02)
                yield b" " * 4096
    async def handler(req):
        if req.url.path == path:
            return httpx.Response(200, stream=Stream(),
                                  headers={"Content-Encoding": "gzip"} if mode == "encoded" else {})
        return target.handler(req)
    audit = Audit(":memory:")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                 headers={"Authorization": "Bearer " + "s" * 40}) as client:
        manager = module.Controller(audit, client)
        result = await manager.execute("ops", "delta-sim-001", Command(**command()))
        assert result["status"] == expected
    audit.close()


def test_startup_error_releases_audit_lock(tmp_path, monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError("discovery failed")
    from bff.oidc import OidcClient
    monkeypatch.setattr(OidcClient, "discover", fail)
    path = str(tmp_path / "audit.db")
    settings = make_settings(sim_control_enabled=True, sim_control_token="s" * 40,
                             sim_control_db=path, auth_mode="oidc",
                             oidc_issuer="https://idp.example", oidc_client_id="test",
                             oidc_redirect_uri="https://testserver/callback",
                             oidc_role_map="admin:ops")
    with pytest.raises(RuntimeError, match="discovery failed"):
        with TestClient(create_app(account_repository=FakeAccounts(AUTH_USERS), settings=settings)):
            pass
    recovered = Audit(path)
    recovered.close()
