"""PRD-0020: scheduled slot identity must survive an early clock observation."""
import math
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bench_run import slot_observation
from delta_device.edge import next_sample_deadline


ORIGIN = 2544316.218


@pytest.mark.parametrize('offset', [-.015, 0, .015])
def test_original_5109_boundary_uses_scheduled_identity_and_signed_delay(offset):
    due = ORIGIN + 5109 * 5
    slot, delay, closed = slot_observation(ORIGIN, due, due + offset, 5, 17280)
    assert slot == 5109 and not closed, '5109 observation mislabeled as previous slot'
    assert delay == pytest.approx(offset, abs=1e-8), 'signed early/late delay lost'


@pytest.mark.parametrize('interval', [1, 5, 10, 15, 30])
@pytest.mark.parametrize('direction', [-1, 0, 1])
def test_adjacent_representable_times_around_boundary_keep_scheduled_slot(interval, direction):
    due = ORIGIN + 4 * interval
    observed = math.nextafter(due, -math.inf if direction < 0 else math.inf) if direction else due
    slot, delay, closed = slot_observation(ORIGIN, due, observed, interval, 8)
    assert slot == 4 and not closed, 'one ULP moved observation into a different slot'
    assert (delay < 0 if direction < 0 else delay > 0 if direction else delay == 0), 'boundary delay sign incorrect'


def test_real_skip_stays_missing_instead_of_renumbering_successes():
    due = next_sample_deadline(ORIGIN + 5, ORIGIN + 15.3, 5)
    assert due == ORIGIN + 20, 'production scheduler unexpectedly changed'
    slot, delay, closed = slot_observation(ORIGIN, due, due - .015, 5, 10)
    assert slot == 4 and delay < 0 and not closed, 'skipped slots were hidden by a sequential counter'


def test_repeated_same_deadline_still_has_duplicate_slot_identity():
    first = slot_observation(ORIGIN, ORIGIN + 5, ORIGIN + 5, 5, 10)
    second = slot_observation(ORIGIN, ORIGIN + 5, ORIGIN + 5.1, 5, 10)
    assert first[0] == second[0] == 1, 'real duplicate was silently renumbered'


@pytest.mark.parametrize('due,observed', [(15, 14.985), (15, 15), (15, 15.015), (10, 15)])
def test_end_boundary_never_creates_extra_sample(due, observed):
    _, _, closed = slot_observation(ORIGIN, ORIGIN + due, ORIGIN + observed, 5, 3)
    assert closed, 'early final wake or late old deadline admitted a sample beyond the window'


@pytest.mark.parametrize('origin,due,observed,interval,count', [
    (ORIGIN, ORIGIN + 5.015, ORIGIN + 5.015, 5, 10),
    (ORIGIN, ORIGIN - 5, ORIGIN, 5, 10),
    (ORIGIN, ORIGIN, ORIGIN - 1, 5, 10),
    (ORIGIN, ORIGIN, ORIGIN, 0, 10),
    (ORIGIN, ORIGIN, ORIGIN, True, 10),
    (ORIGIN, ORIGIN, ORIGIN, 5, 0),
    (ORIGIN, ORIGIN, ORIGIN, 5, True),
    (ORIGIN, math.inf, ORIGIN, 5, 10),
    (ORIGIN, ORIGIN, math.nan, 5, 10),
])
def test_invalid_or_off_grid_schedule_is_not_rounded_into_success(origin, due, observed, interval, count):
    with pytest.raises(ValueError):
        slot_observation(origin, due, observed, interval, count)


@pytest.mark.integration
@pytest.mark.parametrize('observed_offsets,after_poll_offsets,expected_slots,missing', [
    ([0, 4.985, 10], [.3, 5.285, 10.3], [0, 1, 2], []),
    ([0, 10], [6.3, 10.3], [0, 2], [1]),
])
def test_observer_wiring_keeps_deadline_values_and_real_gaps(
        tmp_path, monkeypatch, observed_offsets, after_poll_offsets, expected_slots, missing):
    """Exercise run_bench instrumentation with virtual time and NO live I/O."""
    from types import SimpleNamespace
    import serial.tools.list_ports
    import bench_run
    from delta_device import edge

    tick = [ORIGIN]
    ledgers, deadlines = [], []
    snapshot = dict(voltage=230, current=13, power_kw=9, energy_kwh=1234.56,
                    state=2, temperature_c=35, phases=[dict(voltage=230, frequency_hz=60)] * 3)

    class MemoryLedger:
        def __init__(self, directory):
            self.events, self.error = [], None
            ledgers.append(self)
        def add(self, kind, **data):
            self.events.append(dict(kind=kind, monotonic=tick[0], **data))
        def close(self):
            pass

    class FakePoller:
        def __init__(self, *args, **kwargs):
            pass
        def sample(self):
            return snapshot

    class FakeBox:
        def __init__(self, path, *args):
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        def enqueue(self, *args):
            pass
        def pending_count(self):
            return 0

    class FakeProcess:
        pid = 123456
        ended = False
        def poll(self):
            return 0 if self.ended else None
        def terminate(self):
            self.ended = True
        def wait(self, **kwargs):
            return 0

    def virtual_edge(config):
        deadline = edge.time.monotonic()
        clock = edge.ClockGuard('demo')
        poller = edge.Poller({})
        box = edge.Outbox(config['outbox_path'], 10)
        for ordinal, (offset, after) in enumerate(zip(observed_offsets, after_poll_offsets)):
            tick[0] = ORIGIN + offset
            stamp = clock.timestamp(now=1794491700000000000 + ordinal * 5000000000)
            box.enqueue(stamp, 'not-published', poller.sample())
            actual = edge.next_sample_deadline(deadline, ORIGIN + after, 5)
            expected = next_sample_deadline(deadline, ORIGIN + after, 5)
            deadlines.append((actual, expected))
            deadline = actual
        tick[0] = ORIGIN + 14.985  # Scheduled slot3 must close even on early wake.
        clock.timestamp(now=1794491800000000000)
        pytest.fail('closed sampling window admitted another read')

    monkeypatch.setattr(bench_run, 'Ledger', MemoryLedger)
    monkeypatch.setattr(bench_run, 'Poller', FakePoller)
    monkeypatch.setattr(bench_run, 'Outbox', FakeBox)
    monkeypatch.setattr(bench_run, 'time', SimpleNamespace(monotonic=lambda: tick[0], sleep=lambda _: None))
    monkeypatch.setattr(bench_run.subprocess, 'Popen', lambda *a, **k: FakeProcess())
    monkeypatch.setattr(bench_run.threading, 'Timer', lambda *a, **k: SimpleNamespace(start=lambda: None, cancel=lambda: None))
    monkeypatch.setattr(bench_run.signal, 'getsignal', lambda _: lambda *a: None)
    monkeypatch.setattr(serial.tools.list_ports, 'comports', lambda: [])
    monkeypatch.setattr(edge, 'run', virtual_edge)
    config = dict(mode='demo', device_id='delta-rtu-sim-001', queue_limit=10, poll_interval=5,
                  mqtt=dict(host='127.0.0.1'), modbus=dict(transport='rtu', serial_port='FAKE4',
                      baudrate=19200, unit_id=1, timeout=1))
    result = bench_run.run_bench(config, tmp_path/'virtual-observer', 3, 'day', 'FAKE3', [])
    attempts = [e for e in ledgers[0].events if e['kind'] == 'attempt']
    assert [e['slot'] for e in attempts] == expected_slots, 'wrapper used actual wake bucket instead of scheduled deadline'
    assert result['missing_slots'] == missing, 'observer concealed a real skipped slot'
    assert all(a == b for a, b in deadlines), 'observer altered production scheduling'
    assert sum(e['kind'] == 'sampling_window_closed' for e in ledgers[0].events) == 1, 'window did not close'
    if not missing:
        assert attempts[1]['start_delay'] == pytest.approx(-.015, abs=1e-8), 'early wake delay was wrapped positive'
