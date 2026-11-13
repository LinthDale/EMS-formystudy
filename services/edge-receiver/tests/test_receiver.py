"""Receiver authority and generation are mandatory, never inferred from payload."""
import sys
from pathlib import Path
from uuid import uuid4
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edge_receiver.receiver import authority, load_generation, Receiver


def test_authority_binds_device_stream_revision_profile_and_effective_window():
    sample = dict(gateway_id='g1', device_id='d1', stream_id=str(uuid4()), config_revision='r1',
                  profile_version='v135', sampled_at_us=100)
    binding = {k: sample[k] for k in ('stream_id', 'config_revision', 'profile_version')}
    binding.update(not_before_us=100, not_after_us=200)
    allowed = {'g1': {'d1': binding}}
    assert authority(sample, allowed), 'registered source rejected'
    for key, bad in [('gateway_id', 'other'), ('device_id', 'other'), ('stream_id', str(uuid4())),
                     ('config_revision', 'r2'), ('profile_version', 'other'), ('sampled_at_us', 200)]:
        assert not authority(dict(sample, **{key: bad}), allowed), f'unregistered {key} accepted'


def test_generation_requires_external_nonempty_uuid_file(tmp_path):
    path = tmp_path / 'generation'
    for value in ('', 'not-uuid'):
        path.write_text(value)
        with pytest.raises(ValueError):
            load_generation(path)
    path.unlink()
    with pytest.raises((OSError, ValueError)):
        load_generation(path)
    generation = str(uuid4())
    path.write_text(generation + '\n')
    assert load_generation(path) == generation, 'external generation changed'


def test_samples_rate_has_independent_40_per_second_and_burst_64(monkeypatch):
    from edge_receiver import receiver
    monkeypatch.setattr(receiver.time, 'monotonic', lambda: 100)
    runtime = Receiver.__new__(Receiver)
    runtime.buckets = {}
    assert runtime.rate_allowed('g1', 'sample', 32), 'first batch rejected'
    assert runtime.rate_allowed('g1', 'sample', 32), 'burst 64 rejected'
    assert not runtime.rate_allowed('g1', 'sample', 1), 'sample burst unbounded'
    monkeypatch.setattr(receiver.time, 'monotonic', lambda: 101)
    assert runtime.rate_allowed('g1', 'sample', 40), '40/s refill incorrect'
    assert not runtime.rate_allowed('g1', 'sample', 1), '40/s limit absent'


def test_cleanup_attempts_all_owned_resources_after_timeout(tmp_path):
    import subprocess
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
    from verify_private import cleanup_owned
    calls = []
    def fake(args, **kwargs):
        calls.append(args)
        if args[:2] == ['docker', 'logs']:
            raise subprocess.TimeoutExpired(args, 15)
        if args[-1] == 'second':
            raise OSError('Docker unavailable')
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    result = cleanup_owned([('a', 'first'), ('b', 'second')], tmp_path, fake)
    assert len(calls) == 4 and len(result) == 2, 'cleanup stopped at first error'
    assert any(x['passed'] for x in result) and any(not x['passed'] for x in result), 'cleanup errors concealed'


def test_startup_failure_logs_only_kind_not_credential_value(tmp_path, monkeypatch, caplog):
    from edge_receiver import receiver
    path = tmp_path / 'bad.json'
    path.write_text('{}')
    monkeypatch.setattr(sys, 'argv', ['receiver', '--config', str(path)])
    def fail(_):
        raise ValueError('secret-value-must-not-be-logged')
    monkeypatch.setattr(receiver, 'Receiver', fail)
    with pytest.raises(SystemExit) as stopped:
        receiver.main()
    assert stopped.value.code == 1 and 'ValueError' in caplog.text, 'startup failure was hidden'
    assert 'secret-value' not in caplog.text, 'credential leaked in startup log'
