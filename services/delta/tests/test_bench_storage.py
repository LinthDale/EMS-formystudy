import sys
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bench_storage import capacity_probe, recovered_exactly, cleanup_owned, private_config, write_json, child_runtime


def test_restart_comparison_rejects_loss_extra_and_uncommitted():
    expected = [(1, 100, 'first'), (2, 200, 'second')]
    assert recovered_exactly(expected, expected, 300)
    assert not recovered_exactly(expected, expected[:1], 300)
    assert not recovered_exactly(expected, expected + [(3, 300, 'uncommitted')], 300)
    assert not recovered_exactly(expected, expected, 200)


def test_capacity_faults_preserve_pending_and_resume(tmp_path):
    result = capacity_probe(tmp_path)
    assert result['queue_full_rejected']
    assert result['sqlite_full_rejected']
    assert result['pending_preserved']
    assert result['recovery_inserted']
    assert result['corrupt_rejected'] and result['corrupt_bytes_preserved']
    assert result['integrity_check'] == 'ok' and result['passed']


def test_cleanup_attempts_every_owned_resource_after_failure():
    calls = []
    def failed():
        calls.append('first')
        raise OSError('fixture')
    first = SimpleNamespace(poll=lambda: None, kill=failed)
    second = SimpleNamespace(poll=lambda: None, kill=lambda: calls.append('second'),
                             wait=lambda **kw: None)
    gate = SimpleNamespace(close=lambda: calls.append('gate'))
    log = SimpleNamespace(close=lambda: calls.append('log'))
    assert cleanup_owned((first, second), gate, log) == ['child:OSError']
    assert calls == ['first', 'second', 'gate', 'log']


def test_marker_only_published_after_complete_file(tmp_path, monkeypatch):
    import bench_storage
    destination = tmp_path / 'marker.json'
    replace = os.replace
    def observed(source, target):
        assert not destination.exists()
        assert json.loads(source.read_text()) == {'committed': True}
        replace(source, target)
    monkeypatch.setattr(bench_storage.os, 'replace', observed)
    write_json(destination, {'committed': True})
    assert json.loads(destination.read_text()) == {'committed': True}


def test_internal_child_rejects_wrong_parent_and_external_outbox(tmp_path):
    from test_delivery import config
    c = config(tmp_path)
    c['device_id'] = 'delta-rtu-sim-001'
    c['modbus'] = {'transport': 'rtu', 'serial_port': 'COM4'}
    c['mqtt'].update(host='127.0.0.1', port=19999, tls=False)
    c['outbox_path'] = str(tmp_path / 'state' / 'outbox.db')
    path = tmp_path / 'config.json'
    manifest = dict(tool='delta-storage-crash-v1', run_id='fixture', parent_pid=os.getppid(), gate_port=19999)
    write_json(path, c)
    write_json(tmp_path / 'run.json', manifest)
    assert private_config(path, 'fixture')['device_id'] == 'delta-rtu-sim-001'
    with pytest.raises(ValueError):
        private_config(path, 'wrong')
    manifest['parent_pid'] = -1
    write_json(tmp_path / 'run.json', manifest)
    with pytest.raises(ValueError):
        private_config(path, 'fixture')
    manifest['parent_pid'] = os.getppid()
    write_json(tmp_path / 'run.json', manifest)
    c['outbox_path'] = str(tmp_path.parent / 'existing.db')
    write_json(path, c)
    with pytest.raises(ValueError):
        private_config(path, 'fixture')


def test_windows_child_bypasses_venv_redirector_and_keeps_dependencies(monkeypatch):
    import bench_storage
    monkeypatch.setattr(bench_storage, 'sys', SimpleNamespace(platform='win32',
        executable='venv-redirector.exe', _base_executable='real-python.exe'))
    monkeypatch.setattr(bench_storage.sysconfig, 'get_paths', lambda: {'purelib': 'private-venv-libs'})
    executable, env = child_runtime()
    assert executable == 'real-python.exe'
    assert env['PYTHONPATH'] == 'private-venv-libs'
    assert env['PYTHONDONTWRITEBYTECODE'] == '1'
