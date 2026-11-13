import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bench_soak import assess, stages, validate_roots, dependency_hashes


def summary(missing=0):
    return dict(scheduled=3600, valid=3600-missing, committed=3600-missing,
        failed_slots=list(range(missing)), missing_slots=list(range(missing)),
        duplicate_attempt_slots=[], duplicate_read_slots=[], duplicate_commit_slots=[],
        outside_slots=[], ledger_error=None, control_errors=[], golden_errors=[], pending_end=0,
        poll_seconds={'p99': .4}, **{'pass': missing == 0})


def test_formal_plan_keeps_real_one_hour_and_twenty_four_hours():
    assert [(s['interval'], s['count']) for s in stages('full')] == [(1, 3600), (5, 17280)]
    assert all(s['formal'] for s in stages('full'))
    assert not any(s['formal'] for s in stages('smoke'))


def test_soak_threshold_does_not_rewrite_original_strict_result():
    raw = summary(3)
    result = assess(raw, {'passed': True}, 0, 3605, 3600, 1, 1, [0, 1, 2])
    assert result['passed'] and result['valid_rate'] >= .999
    assert result['raw_strict_pass'] is False and raw['pass'] is False
    assert not assess(summary(4), {'passed': True}, 0, 3605, 3600, 1, 1, list(range(4)))['passed']


@pytest.mark.parametrize('key,value', [('pending_end', 1), ('ledger_error', 'writer_failed'),
    ('golden_errors', ['wrong_voltage']), ('duplicate_commit_slots', [1]), ('outside_slots', [3600])])
def test_bad_values_or_unsettled_delivery_fail(key, value):
    raw = summary()
    raw[key] = value
    assert not assess(raw, {'passed': True}, 0, 3605, 3600, 1, 0, [])['passed']


def test_missing_db_confirmation_short_window_or_unclassified_gap_fails():
    assert not assess(summary(), {'passed': False}, 0, 3605, 3600, 1, 0, [])['passed']
    assert not assess(summary(), {'passed': True}, 0, 100, 3600, 1, 0, [])['passed']
    assert not assess(summary(1), {'passed': True}, 0, 3605, 3600, 1, 1, [])['passed']
    assert not assess(summary(), {'passed': True}, 0, 3605, 3600, 1, 2, [])['passed']


def test_cleanup_duration_cannot_complete_early_sampling_or_hide_exit_failure():
    assert not assess(summary(3), {'passed': True}, 0, 3597, 3600, 1, 1, [0, 1, 2])['passed']
    assert not assess(summary(), {'passed': True}, 0, None, 3600, 1, 0, [])['passed']
    assert not assess(summary(), {'passed': True}, 0, 3600, 3600, 1, 1, [])['passed']


def test_archive_cannot_overlap_source_tree(tmp_path):
    local = tmp_path/'local'
    for archive in (local, local/'runtime/archive', tmp_path):
        with pytest.raises(ValueError):
            validate_roots(local, archive)
    validate_roots(local, tmp_path/'separate')


def test_verifier_hash_covers_imported_dependencies(tmp_path, monkeypatch):
    import bench_soak
    paths = [tmp_path/name for name in ('verify.py', 'ledger.py', 'control.py')]
    for path in paths:
        path.write_text('original')
    monkeypatch.setattr(bench_soak, 'verifier_dependencies', lambda: paths)
    before = dependency_hashes()
    paths[1].write_text('changed imported ledger')
    assert dependency_hashes() != before
