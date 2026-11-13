"""Bounded Windows soak sequence; v1 acquisition acceptance, not DB-ACK acceptance.

Freeze runtime sources, run 1s/1h then 5s/24h only after acceptance, retain raw
strict results, verify DB/API and archive completed files. STOP.txt requests
termination of this tool's owned process tree. Shared EMS services stay running.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from bench_storage import write_json
from bench_job import spawn_owned

SERVICE = Path(__file__).resolve().parents[1]


def stages(mode):
    if mode == 'full':
        return [dict(name='one-second-one-hour', interval=1, count=3600, formal=True),
                dict(name='five-second-twenty-four-hours', interval=5, count=17280, formal=True)]
    if mode == 'smoke':
        return [dict(name='smoke-one-second', interval=1, count=3, formal=False),
                dict(name='smoke-five-seconds', interval=5, count=3, formal=False)]
    raise ValueError('unknown soak plan')


def assess(raw, comparison, origin, closed, count, interval, returncode, classified):
    failed = set(raw['failed_slots'])
    rate = raw['valid'] / count
    passed = (returncode == (0 if raw['pass'] else 1)
        and closed is not None and closed - origin >= count * interval
        and raw['scheduled'] == count and rate >= .999
        and raw['valid'] == raw['committed'] == count - len(failed)
        and failed == set(classified) and comparison.get('passed') is True
        and raw['pending_end'] == 0 and not any(raw[k] for k in (
            'duplicate_attempt_slots', 'duplicate_read_slots', 'duplicate_commit_slots',
            'outside_slots', 'ledger_error', 'control_errors', 'golden_errors')))
    return dict(passed=bool(passed), valid_rate=rate, raw_strict_pass=raw['pass'],
                classified_failed_slots=sorted(failed), measured_seconds=closed-origin if closed is not None else None,
                minimum_measurement_seconds=count*interval)


def runtime():
    # Direct interpreter PID on Windows, preserving the actual pinned venv libs
    # even when this controller itself was launched through the base interpreter.
    executable = sys._base_executable if sys.platform == 'win32' else sys.executable
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'DELTA_SIM_NOISE': '0'}
    env['PYTHONPATH'] = str(importlib.metadata.distribution('pymodbus').locate_file(''))
    return executable, env


def validate_roots(local, archive):
    if local == archive or local in archive.parents or archive in local.parents:
        raise ValueError('local and archive roots must be disjoint')


def verifier_dependencies():
    return [SERVICE/'tools/bench_verify.py', SERVICE/'tools/bench_ledger.py',
            SERVICE.parent.parent/'scripts/simulator_control.py']


def dependency_hashes():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in verifier_dependencies()}


def resources(process, directory):
    pids = [process.pid]
    events = directory / 'events.jsonl'
    # The first event contains the simulator PID. Avoid rescanning long logs.
    if events.exists():
        with events.open(encoding='utf-8') as stream:
            line = stream.readline()
        if line.endswith('\n'):
            first = json.loads(line)
            if first['kind'] == 'sim_started':
                pids.append(int(first['pid']))
    ids = ','.join(str(int(p)) for p in pids)
    script = (f'@(Get-Process -Id {ids} -ErrorAction SilentlyContinue | '
              'Select-Object Id,CPU,WorkingSet64,PrivateMemorySize64) | ConvertTo-Json -Compress')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
        capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError('resource observation failed')
    rows = json.loads(result.stdout) if result.stdout.strip() else []
    if isinstance(rows, dict):
        rows = [rows]
    db = directory / 'state' / 'outbox.db'
    return dict(utc=datetime.now(timezone.utc).isoformat(), monotonic=time.monotonic(),
        processes=rows, cpu_unit='cumulative process seconds',
        free_bytes=shutil.disk_usage(directory).free,
        sqlite_bytes=db.stat().st_size if db.exists() else 0)


def freeze(local, config_path):
    target = local / 'runtime' / 'services' / 'delta'
    (target / 'tools').mkdir(parents=True)
    (target / 'delta_device').mkdir()
    for path in (SERVICE / 'delta_device').glob('*.py'):
        shutil.copyfile(path, target / 'delta_device' / path.name)
    for name in ('bench_run.py', 'bench_ledger.py'):
        shutil.copyfile(SERVICE / 'tools' / name, target / 'tools' / name)
    shutil.copyfile(config_path, local / 'config.json')
    controller = local/'controller-source'
    controller.mkdir()
    for name in ('bench_soak.py', 'bench_job.py', 'bench_storage.py'):
        shutil.copyfile(SERVICE/'tools'/name, controller/name)
    for path in verifier_dependencies():
        shutil.copyfile(path, controller/path.name)
    files = list(target.rglob('*.py')) + list(controller.glob('*.py'))
    write_json(local / 'source-sha256.json', {
        str(p.relative_to(local)) if p.is_relative_to(local) else 'verifier:' + p.name:
        hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    return target


def run(config_path, local, archive, mode):
    from delta_device.config import load_config
    validate_roots(local, archive)
    c = load_config(config_path)
    if (c['mode'] != 'demo' or c['device_id'] != 'delta-rtu-sim-001'
            or c['modbus']['transport'] != 'rtu' or c['modbus']['serial_port'] != 'COM4'
            or c['mqtt']['host'] != '127.0.0.1' or c['mqtt']['tls']):
        raise ValueError('dedicated local COM3/COM4 demo required')
    local.mkdir(parents=True, exist_ok=False)
    archive.mkdir(parents=True, exist_ok=False)
    state = dict(status='STARTING', plan=stages(mode), results=[], controller_pid=os.getpid(),
        local_root=str(local), archive_root=str(archive), stop_file=str(local/'STOP.txt'),
        scope='v1 Windows bench, not Pi/4G/field/central DB ACK', started_utc=datetime.now(timezone.utc).isoformat())
    process = job = None
    def status():
        state['updated_utc'] = datetime.now(timezone.utc).isoformat()
        write_json(local / 'status.json', state)
        write_json(archive / 'status.json', state)
    status()
    try:
        target = freeze(local, config_path)
        shutil.copytree(local/'runtime', archive/'runtime')
        shutil.copytree(local/'controller-source', archive/'controller-source')
        shutil.copyfile(local/'source-sha256.json', archive/'source-sha256.json')
        executable, env = runtime()
        verifier_hashes = dependency_hashes()
        write_json(archive/'verifier-dependencies.json', verifier_hashes)
        for stage in state['plan']:
            if (local/'STOP.txt').exists():
                raise InterruptedError('operator requested stop')
            if shutil.disk_usage(local).free < 1024**3:
                raise OSError('insufficient private test disk reserve')
            name, count, interval = stage['name'], stage['count'], stage['interval']
            directory = local / name
            state.update(status='RUNNING', stage=name, expected_slots=count, interval=interval,
                expected_measurement_seconds=count*interval)
            with (local / (name+'.log')).open('w', encoding='utf-8') as log:
                process, job = spawn_owned(executable, [str(target/'tools/bench_run.py'),
                    '--config', str(local/'config.json'), '--output', str(directory),
                    '--count', str(count), '--interval', str(interval)],
                    local/('.launch-'+name), target, env, log)
                state['bench_pid'] = process.pid
                status()
                deadline = time.monotonic() + count*interval + 120
                while process.poll() is None:
                    if (local/'STOP.txt').exists():
                        raise InterruptedError('operator requested stop')
                    if time.monotonic() > deadline:
                        raise TimeoutError('owned bench exceeded duration allowance')
                    if directory.exists():
                        observation = resources(process, directory)
                        if observation['free_bytes'] < 1024**3:
                            raise OSError('private test disk reserve exhausted')
                        with (local/(name+'-resources.jsonl')).open('a', encoding='utf-8') as stream:
                            stream.write(json.dumps(observation)+'\n')
                            stream.flush()
                        state['last_resource_observation'] = observation
                        status()
                    try:
                        process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        pass
                returncode = process.returncode
                job.close()  # Also reaps descendants if the bench itself exited.
                state['status'] = 'VERIFYING'
                status()
                # Use the repository verifier because it locates private login
                # credentials relative to the real repo. Never copy credentials.
                if dependency_hashes() != verifier_hashes:
                    raise RuntimeError('verifier changed during the sequence')
                checked = subprocess.run([executable, str(SERVICE/'tools/bench_verify.py'),
                    str(directory), '--wait-seconds', '30'], cwd=SERVICE, env=env,
                    stdout=log, stderr=log, timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
            raw = json.loads((directory/'summary.json').read_text())
            comparison = json.loads((directory/'db-comparison.json').read_text())
            events = [json.loads(s) for s in (directory/'events.jsonl').read_text().splitlines()]
            origin = next(e['origin'] for e in events if e['kind']=='window_start')
            closed = next((e['monotonic'] for e in events if e['kind']=='sampling_window_closed'), None)
            classified = set(raw['missing_slots']) | {e['slot'] for e in events
                if e['kind'] in ('read_error', 'storage_error', 'clock_error')}
            result = assess(raw, comparison, origin, closed, count, interval, returncode, classified)
            result.update(name=name, formal=stage['formal'], verifier_exit_code=checked.returncode)
            result['passed'] = result['passed'] and checked.returncode == 0
            write_json(directory/'soak-result.json', result)
            shutil.copytree(directory, archive/name)
            shutil.copyfile(local/(name+'.log'), archive/(name+'.log'))
            resource_file = local/(name+'-resources.jsonl')
            if resource_file.exists():
                shutil.copyfile(resource_file, archive/resource_file.name)
            state['results'].append(result)
            status()
            if not result['passed']:
                raise RuntimeError('stage acceptance failed; next stage not started')
        state['status'] = 'COMPLETED'
        status()
        return True
    except BaseException as exc:
        state.update(status='STOPPED' if isinstance(exc, InterruptedError) else 'FAILED',
                     error_kind=type(exc).__name__)
        status()
        raise
    finally:
        try:
            if job is not None:
                job.close()
            if process is not None:
                process.wait(timeout=10)
        except Exception as cleanup_error:
            state.update(status='FAILED', cleanup_error_kind=type(cleanup_error).__name__)
            status()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--local-root', type=Path, required=True)
    parser.add_argument('--archive-root', type=Path, required=True)
    parser.add_argument('--mode', choices=('smoke', 'full'), default='full')
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('physical soak controller requires Windows')
    run(args.config.resolve(), args.local_root.resolve(), args.archive_root.resolve(), args.mode)


if __name__ == '__main__':
    main()
