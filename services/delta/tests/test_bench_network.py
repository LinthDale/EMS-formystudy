"""Offline acceptance must prove one publisher reconnects and keeps all slots."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bench_network import offline_result


def events():
    rows = [dict(kind='window_start', origin=100, count=80, interval=5),
            dict(kind='network_off', monotonic=109), dict(kind='network_on', monotonic=409),
            dict(kind='publisher_started'), dict(kind='publisher_connected', monotonic=101),
            dict(kind='publisher_connected', monotonic=420)]
    rows += [dict(kind='committed', slot=i, sampled_ns=i) for i in range(2, 62)]
    return rows


def test_offline_needs_sixty_committed_slots_and_same_publisher():
    assert offline_result(events())['passed'], 'complete outage rejected'
    assert not offline_result(events() + [dict(kind='publisher_started')])['passed'], 'publisher reconstruction accepted'
    assert not offline_result(events()[:-1])['passed'], 'missing offline commit accepted'


def test_ack_during_isolation_or_absent_reconnect_fails():
    assert not offline_result(events() + [dict(kind='broker_ack', monotonic=200)])['passed'], 'nonisolated sender accepted'
    truncated = [e for e in events() if not (e['kind']=='publisher_connected' and e['monotonic']==420)]
    assert not offline_result(truncated)['passed'], 'reconnect without evidence accepted'
