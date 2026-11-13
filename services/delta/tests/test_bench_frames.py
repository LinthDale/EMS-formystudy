"""Fault fixtures must distinguish invalid bytes from valid fragmented replies."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from bench_frames import crc, response, chunks, reply_chunks


def test_crc_matches_independent_modbus_reference():
    assert crc(bytes.fromhex('01030000000a')).hex() == 'c5cd', 'CRC implementation invalid'


def test_fragment_reassembles_but_bad_crc_and_truncation_do_not():
    frame = response(2300)
    assert b''.join(part for _, part in chunks('fragment', frame, .5)) == frame, 'fragment altered payload'
    bad = b''.join(part for _, part in chunks('crc', frame, .5))
    assert bad[-2:] != crc(bad[:-2]), 'bad-CRC fixture is accidentally valid'
    short = b''.join(part for _, part in chunks('truncated', frame, .5))
    assert len(short) < 7, 'truncated fixture not short'


def test_wrong_station_is_valid_crc_for_another_station():
    frame = b''.join(part for _, part in chunks('wrong_unit', response(2300), .5))
    assert frame[0] == 2 and frame[-2:] == crc(frame[:-2]), 'fixture not wrong-unit only'


def test_timeout_and_late_fixture_are_distinct():
    assert chunks('silent', response(2300), .5) == [], 'silent fixture sends bytes'
    assert reply_chunks('late', 1, .5) == [], 'old response sent before second request'
    replies = reply_chunks('late', 2, .5)
    assert replies[0][1] == response(2300) and replies[1][1] == response(2400), 'late order invalid'
    assert reply_chunks('silent', 2, .5) == [(0, response(2400))], 'normal recovery includes stale frame'
