"""Fail-closed acceptance checks for no-Pi backlog experiments (PRD-0020)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bench_backlog import assess, assess_backup, require_scope, transport_delay


def test_same_count_wrong_payload_never_passes():
    result = assess(['a', 'b'], ['a', 'c'], 0, [], True)
    assert not result['completion_passed'], 'equal counts concealed lost/wrong payload'
    assert result['missing_count'] == result['unexpected_count'] == 1


def test_duplicate_delivery_preserves_completion_but_fails_uniqueness():
    result = assess(['a', 'b'], ['a', 'b', 'b'], 0, [], True)
    assert result['completion_passed'], 'all originals were delivered'
    assert not result['unique_delivery_passed'], 'duplicate was hidden'
    assert result['duplicate_count'] == 1


@pytest.mark.parametrize('pending,errors,stopped', [(1, [], True), (0, ['error'], True), (0, [], False)])
def test_unfinished_or_failed_run_never_passes(pending, errors, stopped):
    result = assess(['a'], ['a'], pending, errors, stopped)
    assert not result['completion_passed'], 'unfinished run accepted'


def test_duplicate_source_or_empty_source_rejected():
    for expected in ([], ['a', 'a']):
        assert not assess(expected, expected, 0, [], True)['completion_passed'], 'invalid source ledger accepted'


def test_exact_payload_set_and_clean_shutdown_passes():
    result = assess(['a', 'b'], ['b', 'a'], 0, [], True)
    assert result['unique_delivery_passed'], 'valid out-of-order delivery rejected'


@pytest.mark.parametrize('expected,actual', [(None, 'net:[1]'), ('net:[1]', 'net:[2]')])
def test_private_namespace_must_match(expected, actual):
    with pytest.raises(ValueError):
        require_scope('private', expected, actual, 'delta-private-qa')


def test_local_ems_scope_only_accepts_reserved_test_identity():
    require_scope('local-ems', None, None, 'delta-backlog-qa-20261112')
    with pytest.raises(ValueError):
        require_scope('local-ems', None, None, 'delta-rtu-sim-001')
    with pytest.raises(ValueError):
        require_scope('invalid', None, None, 'delta-backlog-qa-20261112')


def test_transport_delay_is_deterministic_and_bounded():
    values = [transport_delay(0.1, 0.025, i) for i in range(100)]
    assert min(values) >= .075 and max(values) <= .125, 'jitter outside declared bounds'
    assert values == [transport_delay(.1, .025, i) for i in range(100)], 'jitter not reproducible'
    with pytest.raises(ValueError):
        transport_delay(-1, 0, 0)


def test_backup_must_contain_complete_committed_prefix_and_metadata():
    expected = [dict(sampled_ns=i, payload=str(i), snapshot={'v': i}) for i in range(1, 5)]
    assert assess_backup(expected[:3], expected, 3, 3)['passed'], 'valid backup prefix rejected'
    assert not assess_backup(expected[:1], expected, 3, 1)['passed'], 'truncated backup accepted'
    assert not assess_backup(expected[1:], expected, 3, 4)['passed'], 'missing prefix accepted'
    assert not assess_backup(expected[:3], expected, 3, 4)['passed'], 'wrong metadata accepted'
    damaged = [dict(row) for row in expected[:3]]
    damaged[1]['snapshot'] = {'v': -1}
    assert not assess_backup(damaged, expected, 3, 3)['passed'], 'changed snapshot accepted'
