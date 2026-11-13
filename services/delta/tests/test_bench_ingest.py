"""Actual v1 ingest experiment verdicts must distinguish reproduction from acceptance."""
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bench_ingest import case_verdict, suite_verdict


def record(kind, received):
    row = dict(sampled_ns=1000, voltage=230, current=5, power_kw=1, energy_kwh=10)
    return dict(kind=kind, expected=[row], actual=[dict(row) for _ in range(received)],
                broker_ack=True, pending_end=0, checks={'setup': True}, errors=[])


def test_normal_ingest_requires_exact_values_and_membership():
    item = record('baseline', 1)
    assert case_verdict(item)['experiment_passed'], 'valid baseline rejected'
    item['actual'][0]['voltage'] = 240
    assert not case_verdict(item)['experiment_passed'], 'equal count concealed wrong value'


def test_missing_and_duplicate_baseline_never_pass():
    for count in (0, 2):
        assert not case_verdict(record('baseline', count))['experiment_passed'], 'invalid baseline accepted'


def test_duplicate_counterexample_does_not_mean_delivery_acceptance():
    result = case_verdict(record('duplicate', 2))
    assert result['experiment_passed'], 'duplicate counterexample not detected'
    assert not result['system_delivery_acceptance_passed'], 'duplicate incorrectly called reliable delivery'


def test_receiver_down_requires_real_stop_restart_and_observation_window():
    item = record('receiver-down', 0)
    assert not case_verdict(item)['experiment_passed'], 'missing outage/restart evidence accepted'
    item['checks'].update(receiver_down_at_send=True, receiver_restarted=True, settled_seconds=10)
    result = case_verdict(item)
    assert result['experiment_passed'] and not result['system_delivery_acceptance_passed']


@pytest.mark.parametrize('field,value', [('broker_ack', False), ('pending_end', 1), ('errors', ['failure'])])
def test_failed_sender_or_receiver_never_counts_as_counterexample(field, value):
    item = record('duplicate', 2)
    item[field] = value
    assert not case_verdict(item)['experiment_passed'], 'failed observation accepted'


def test_suite_requires_all_four_unique_cases_and_clean_teardown():
    cases = [dict(kind=k, experiment_passed=True) for k in ('baseline', 'duplicate', 'receiver-down', 'db-pause')]
    assert suite_verdict(cases, True)['verification_passed'], 'complete experiment rejected'
    assert not suite_verdict(cases[:-1], True)['verification_passed'], 'missing case accepted'
    assert not suite_verdict(cases + cases[:1], True)['verification_passed'], 'duplicate case accepted'
    assert not suite_verdict(cases, False)['verification_passed'], 'cleanup failure ignored'
