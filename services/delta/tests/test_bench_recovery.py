"""Independent raw register fixture and acceptance criteria for the recovery bench."""
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bench_recovery import frame, verdict
from bench_frames import crc


def test_complete_sample_uses_literal_old_and_fresh_ac_words():
    old, fresh = frame(49151, 13, False), frame(49151, 13, True)
    assert old[:3] == fresh[:3] == bytes((1, 4, 26))
    assert struct.unpack('>13H', old[3:-2]) == (9000, 2300, 1300, 3000, 6000,
        2300, 1300, 3000, 6000, 2300, 1300, 3000, 6000)
    assert struct.unpack('>13H', fresh[3:-2]) == (9360, 2400, 1300, 3000, 6000,
        2400, 1300, 3000, 6000, 2400, 1300, 3000, 6000)
    assert old[-2:] == crc(old[:-2]) and fresh[-2:] == crc(fresh[:-2])
    with pytest.raises(ValueError):
        frame(49151, 1, True)


def record(kind):
    return dict(kind=kind, errors=[], first_failed=True, blocked=True,
        queued_old_bytes=31, requests_before=2, requests_after_block=2,
        request_count=2 if kind == 'unknown' else 5,
        late_inside_guard=True, guard_respected=True,
        recovered=None if kind == 'unknown' else {'voltage': 240, 'power_kw': 9.36})


@pytest.mark.parametrize('kind', ['unknown', 'bounded'])
def test_verdict_requires_actual_block_and_new_sample(kind):
    good = record(kind)
    assert verdict(good)
    for key, value in [('errors', ['slave_failed']), ('first_failed', False),
                       ('blocked', False), ('queued_old_bytes', 0),
                       ('requests_after_block', 3)]:
        assert not verdict(dict(good, **{key: value}))
    if kind == 'bounded':
        for key, value in [('late_inside_guard', False), ('guard_respected', False),
                           ('recovered', {'voltage': 230, 'power_kw': 9})]:
            assert not verdict(dict(good, **{key: value}))
