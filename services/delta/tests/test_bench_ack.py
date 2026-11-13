import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bench_ack import counterexample, isolated_namespace


def test_loss_requires_ack_and_actual_receiver_observation():
    good = dict(kind='ack-before-commit', ack=True, observed=1, committed=0, pending=0)
    assert counterexample(good)
    for key, value in [('ack', False), ('observed', 0), ('committed', 1), ('pending', 1)]:
        assert not counterexample(dict(good, **{key: value}))


@pytest.mark.parametrize('kind', ['sender-confirmation-suppressed', 'duplicate-delivery'])
def test_duplicate_requires_two_commits_and_retain_before_retry(kind):
    good = dict(kind=kind, ack=True, observed=2, committed=2, pending=0,
                pending_before_retry=1, first_committed=1)
    assert counterexample(good)
    assert not counterexample(dict(good, committed=1))
    assert not counterexample(dict(good, observed=0))
    if kind == 'sender-confirmation-suppressed':
        assert not counterexample(dict(good, pending_before_retry=0))


def test_probe_refuses_wrong_network_namespace(monkeypatch):
    monkeypatch.setattr('os.readlink', lambda _: 'net:[123]')
    monkeypatch.setenv('DELTA_ACK_PROBE_NETNS', 'net:[123]')
    isolated_namespace()
    monkeypatch.setenv('DELTA_ACK_PROBE_NETNS', 'net:[456]')
    with pytest.raises(ValueError): isolated_namespace()
