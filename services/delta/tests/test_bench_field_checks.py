"""Fail-closed assessment of isolated field checks, not field qualification."""
import sys
import subprocess
from types import SimpleNamespace
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bench_field_checks import assess_junit, require_private_namespace
import bench_field_checks as checks


def test_missing_or_wrong_namespace_rejected():
    for expected, actual in [(None, 'net:[1]'), ('net:[2]', 'net:[1]')]:
        with pytest.raises(ValueError):
            require_private_namespace(expected, actual)
    require_private_namespace('net:[2]', 'net:[2]')


@pytest.mark.parametrize('attributes', [
    'tests="12" failures="1" errors="0" skipped="0"',
    'tests="12" failures="0" errors="1" skipped="0"',
    'tests="12" failures="0" errors="0" skipped="1"',
    'tests="11" failures="0" errors="0" skipped="0"',
])
def test_incomplete_or_failed_suite_never_accepted(attributes):
    xml = '<testsuites><testsuite '+attributes+'>' + '<testcase/>'*12 + '</testsuite></testsuites>'
    assert not assess_junit(xml, 0)['passed']


def test_exit_code_and_real_case_count_required():
    xml = '<testsuites><testsuite tests="12" failures="0" errors="0" skipped="0">'
    assert not assess_junit(xml+'</testsuite></testsuites>', 0)['passed']
    complete = xml + ''.join(f'<testcase name="case-{i}"/>' for i in range(12)) + '</testsuite></testsuites>'
    assert assess_junit(complete, 0)['passed']
    assert not assess_junit(complete, 1)['passed']
    assert not assess_junit(xml+'<testcase name="same"/>'*12+'</testsuite></testsuites>', 0)['passed']


@pytest.mark.parametrize('failure', ['logs_timeout','log_write_error'])
def test_log_failure_never_skips_both_owned_container_removals(tmp_path,monkeypatch,failure):
    removed=[]
    def logs(*args,**kwargs):
        if failure=='logs_timeout':
            raise subprocess.TimeoutExpired('docker logs',10)
        return SimpleNamespace(stdout='fixture log',stderr='',returncode=0)
    monkeypatch.setattr(checks.subprocess,'run',logs)
    monkeypatch.setattr(checks,'call',lambda args,**kwargs:removed.append(args[-1]))
    if failure=='log_write_error':
        (tmp_path/'broker.log').mkdir()
    cleanup,errors=checks.cleanup_owned('worker-owned','broker-owned',tmp_path)
    assert removed==['worker-owned','broker-owned'], 'log failure skipped owned cleanup'
    assert len(cleanup)==2 and all(c['removed'] for c in cleanup)
    assert len(errors)==1, 'log failure was not retained for final FAIL'
