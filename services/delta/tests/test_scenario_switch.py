"""Scenario transitions integrate only intervals that generated energy."""
from unittest.mock import patch
from delta_device.simulator import DeltaRegisters
from delta_device.protocol import pdu_address


def energy(block):
    values = block.getValues(pdu_address(53252, 1), 2)
    return values[0] + (values[1] << 16)


def test_day_night_day_never_loses_or_backfills_energy():
    with patch("delta_device.simulator.time.monotonic", return_value=0) as clock:
        block = DeltaRegisters()
        clock.return_value = 100
        before = energy(block)
        block.set_scenario("night")
        assert energy(block) == before
        clock.return_value = 1000
        assert energy(block) == before
        block.set_scenario("day")
        assert energy(block) == before
        clock.return_value = 1100
        assert energy(block) > before
        assert energy(block) - before < 300
