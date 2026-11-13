"""USB reconnect requires evidence, never just re-enumeration."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bench_usb import summarize_usb


def events():
    return [dict(kind='usb_absent', monotonic=10), dict(kind='usb_present', monotonic=40, same_port=True, last_absent_lower=39.5),
            dict(kind='read_error', monotonic=20), dict(kind='read_ok', started=45, monotonic=45.3)]


def test_reenumeration_without_data_is_not_recovery():
    assert not summarize_usb(events()[:-1])['automatic_recovery'], 'no read after replug'
    assert summarize_usb(events())['automatic_recovery'], 'bounded recovery rejected'


def test_changed_port_and_unplugging_wrong_device_fail():
    changed = events()
    changed[1] = {**changed[1], 'same_port':False}
    assert not summarize_usb(changed)['automatic_recovery'], 'port change hidden'
    assert not summarize_usb(events()+[dict(kind='usb_other_missing')])['automatic_recovery'], 'wrong USB ignored'


def test_good_value_during_disconnection_is_not_allowed():
    assert not summarize_usb(events()+[dict(kind='read_ok', started=20, monotonic=20.3)])['automatic_recovery'], 'false value accepted'


def test_read_spanning_replug_is_not_a_value_completed_during_absence():
    assert summarize_usb(events()+[dict(kind='read_ok', started=39, monotonic=41)])['automatic_recovery'], 'spanning read mislabeled fake'


def test_slow_enumeration_must_not_underestimate_recovery():
    slow = events()
    slow[1] = {**slow[1], 'last_absent_lower':39}
    slow[-1] = dict(kind='read_ok', started=54, monotonic=54.4)
    assert not summarize_usb(slow)['automatic_recovery'], 'actual 15.4s recovery counted as 14.9s'
