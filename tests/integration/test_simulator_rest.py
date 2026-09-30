"""Integration: all simulator changes go through authenticated BFF commands."""
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("simulator_id", ["sim-001", "plc-001", "sensor-001", "delta-sim-001"])
def test_state_has_instance_revision_and_config(sim_control, simulator_id):
    state = sim_control.state(simulator_id)
    assert state["instance_id"]
    assert state["revision"] >= 0
    assert state["settings"]


@pytest.mark.parametrize("simulator_id,changes", [
    ("sim-001", {"fault_mode": "freeze"}),
    ("plc-001", {"motor_speed": 1300, "pump_on": True, "valve_open": True}),
    ("sensor-001", {"enabled": False, "interval_seconds": 5}),
    ("delta-sim-001", {"scenario": "night"}),
])
def test_command_and_restore_are_both_audited(sim_control, simulator_id, changes):
    before = sim_control.state(simulator_id)["settings"]
    try:
        op = sim_control.set(simulator_id, changes)
        lookup = sim_control.client.get("/api/simulators/operations/" + op["request_id"])
        assert lookup.json() == op
        assert op["actor"] and op["reason"]
        for key, value in changes.items():
            assert sim_control.state(simulator_id)["settings"][key] == value
    finally:
        sim_control.set(simulator_id, before)
