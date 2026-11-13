"""Fourth pipeline: typed Delta scenario -> raw Modbus -> edge -> DB."""
import pytest
from .conftest import wait_for
pytestmark = pytest.mark.integration


def test_delta_night_then_day_propagates_without_energy_rollback(db_conn, sim_control):
    original = sim_control.state("delta-sim-001")["settings"]
    def latest():
        with db_conn.cursor() as cur:
            cur.execute("""SELECT power_kw,energy_kwh FROM electricity_measurements
                WHERE device_id='delta-sim-001' AND time>now()-interval '30 seconds'
                ORDER BY time DESC LIMIT 1""")
            return cur.fetchone()
    try:
        sim_control.set("delta-sim-001", {"scenario": "day"})
        assert wait_for(lambda: latest() is not None and latest()[0] > 1, timeout=45)
        energy_before = latest()[1]
        sim_control.set("delta-sim-001", {"scenario": "night"})
        assert wait_for(lambda: latest() is not None and latest()[0] == 0, timeout=45)
        assert latest()[1] >= energy_before
        sim_control.set("delta-sim-001", {"scenario": "day"})
        assert wait_for(lambda: latest() is not None and latest()[0] > 1, timeout=45)
        assert latest()[1] >= energy_before
    finally:
        sim_control.set("delta-sim-001", original)
