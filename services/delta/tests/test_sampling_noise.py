"""One-second demo readings remain coherent, bounded and physically consistent."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from delta_device import edge
from delta_device.protocol import decode, pdu_address
from delta_device.simulator import DeltaRegisters


def read(block):
    registers = {}
    for address, count in ((49152, 13), (53248, 9)):
        registers.update(enumerate(block.getValues(pdu_address(address), count), address))
    return decode(registers, 1)


def test_same_second_snapshot_is_stable_and_next_second_has_new_noise():
    with patch("delta_device.simulator.time.monotonic", return_value=0) as clock:
        a, b = DeltaRegisters(noise=True, seed=42), DeltaRegisters(noise=True, seed=42)
        clock.return_value = 0.1
        first = read(a)
        assert first == read(b), "fixed seed reproduces the same readings"
        clock.return_value = 0.9
        assert read(a) == first, "separate register reads share one frame"
        clock.return_value = 1.1
        second = read(a)
        assert second == read(b)
        assert second["voltage"] != first["voltage"], "noise changes each second"
        assert second["energy_kwh"] >= first["energy_kwh"]


def test_noise_is_bounded_and_power_matches_each_phase():
    with patch("delta_device.simulator.time.monotonic", return_value=0) as clock:
        block = DeltaRegisters(noise=True, seed=123)
        samples = []
        for second in range(120):
            clock.return_value = second + .1
            sample = read(block)
            samples.append(sample)
            for phase in sample["phases"]:
                assert 225.4 <= phase["voltage"] <= 234.5
                assert 11.7 <= phase["current"] <= 14.4
                assert phase["power_kw"] == pytest.approx(phase["voltage"] * phase["current"] / 1000, abs=.006)
            assert sample["power_kw"] == pytest.approx(sum(p["power_kw"] for p in sample["phases"]), abs=.003)
        assert len({s["voltage"] for s in samples}) > 20
        assert all(b["energy_kwh"] >= a["energy_kwh"] for a, b in zip(samples, samples[1:]))


@pytest.mark.parametrize("scenario", ["night", "alarm"])
def test_noise_does_not_create_generation_while_stopped(scenario):
    with patch("delta_device.simulator.time.monotonic", return_value=0) as clock:
        block = DeltaRegisters(noise=True)
        clock.return_value = 10.2
        before = read(block)
        block.set_scenario(scenario)
        stopped = read(block)
        assert stopped["power_kw"] == stopped["current"] == 0
        assert stopped["energy_kwh"] == before["energy_kwh"]
        clock.return_value = 200
        assert read(block)["energy_kwh"] == stopped["energy_kwh"]
        block.set_scenario("day")
        assert read(block)["power_kw"] > 0
        assert read(block)["energy_kwh"] == stopped["energy_kwh"]


def test_noise_is_opt_in_for_protocol_fixtures_and_compose(monkeypatch):
    monkeypatch.delenv("DELTA_SIM_NOISE", raising=False)
    assert read(DeltaRegisters())["voltage"] == 230
    monkeypatch.setenv("DELTA_SIM_NOISE", "1")
    assert DeltaRegisters().noise is True
    assert DeltaRegisters(noise=False).noise is False
    monkeypatch.setenv("DELTA_SIM_NOISE", "typo")
    with pytest.raises(ValueError):
        DeltaRegisters()


def test_fixed_deadlines_include_read_duration_and_skip_missed_slots():
    deadline = 0
    starts = []
    for _ in range(10):
        starts.append(deadline)
        deadline = edge.next_sample_deadline(deadline, deadline + .25, 1)
    assert starts == list(range(10)), "250 ms reads must not drift to 1.25 seconds"
    assert edge.next_sample_deadline(0, 2.7, 1) == 3
    assert edge.next_sample_deadline(0, 1, 1) == 1


def test_demo_is_one_second_and_field_templates_keep_ten_seconds():
    folder = Path(__file__).resolve().parents[1] / "config"
    assert json.loads((folder / "demo.json").read_text())["poll_interval"] == 1
    for name in ("field-tcp.example.json", "field-rtu.example.json"):
        assert json.loads((folder / name).read_text())["poll_interval"] == 10
