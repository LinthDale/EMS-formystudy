import ctypes
from pathlib import Path
import sys
import subprocess
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import bench_job


def test_bootstrap_imports_script_local_helper(tmp_path):
    tools = tmp_path/'tools'
    tools.mkdir()
    (tools/'local_probe_helper_do_not_export.py').write_text('VALUE=77')
    script = tools/'script.py'
    script.write_text('from local_probe_helper_do_not_export import VALUE\nprint(VALUE)')
    gate = tmp_path/'gate'
    gate.touch()
    result = subprocess.run([sys.executable, '-c', bench_job.BOOTSTRAP, str(gate), str(script)],
        cwd=tmp_path, capture_output=True, text=True, timeout=5)
    assert result.returncode == 0 and result.stdout.strip() == '77'


class Api:
    def __init__(self, assign=True, close=True):
        self.assign, self.can_close, self.calls = assign, close, []
    def CreateJobObjectW(self, *args): return 17
    def SetInformationJobObject(self, handle, kind, info, size):
        limits = ctypes.cast(info, ctypes.POINTER(bench_job.ExtendedLimits)).contents
        assert kind == 9 and limits.basic.flags == 0x2000
        return True
    def AssignProcessToJobObject(self, *args):
        self.calls.append('assign')
        return self.assign
    def CloseHandle(self, handle):
        self.calls.append('close')
        return self.can_close


def test_job_closes_even_after_parent_exit_and_close_failure_is_visible():
    api = Api()
    job = bench_job.OwnedJob(api)
    job.assign(SimpleNamespace(_handle=99, poll=lambda: 1))
    job.close()
    job.close()
    assert api.calls == ['assign', 'close']
    job = bench_job.OwnedJob(Api(close=False))
    with pytest.raises(OSError): job.close()


@pytest.mark.parametrize('assign', [True, False])
def test_bootstrap_not_released_before_assignment(tmp_path, monkeypatch, assign):
    gate = tmp_path/'start'
    api = Api(assign=assign)
    job = bench_job.OwnedJob(api)
    calls = []
    process = SimpleNamespace(_handle=99, poll=lambda: None,
        terminate=lambda: calls.append('terminate'), wait=lambda **kw: calls.append('wait'))
    def popen(*args, **kwargs):
        assert not gate.exists()
        return process
    real_assign = job.assign
    def checked(child):
        assert not gate.exists()
        real_assign(child)
    monkeypatch.setattr(job, 'assign', checked)
    monkeypatch.setattr(bench_job, 'OwnedJob', lambda: job)
    monkeypatch.setattr(bench_job.subprocess, 'Popen', popen)
    monkeypatch.setattr(bench_job.subprocess, 'CREATE_NO_WINDOW', 0, raising=False)
    if assign:
        assert bench_job.spawn_owned('python', ['bench.py'], gate, tmp_path, {}, None) == (process, job)
        assert gate.exists()
    else:
        with pytest.raises(OSError):
            bench_job.spawn_owned('python', ['bench.py'], gate, tmp_path, {}, None)
        assert not gate.exists() and calls == ['terminate', 'wait']
        assert api.calls == ['assign', 'close']
