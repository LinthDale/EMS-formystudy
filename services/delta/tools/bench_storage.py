"""Isolated crash/restart and bounded SQLite capacity acceptance tools.

Crash mode uses the real COM3 simulator, COM4 edge process, SQLite and Publisher.
Only this tool's child is killed; shared broker and EMS services stay running.
Capacity mode injects SQLITE_FULL through a private database page limit. It
does not fill the OS disk or corrupt an actual outbox.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import sysconfig
import threading
import time
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from delta_device.delivery import Outbox, drain, encode_line

DEVICE = 'delta-rtu-sim-001'
FIELDS = ('voltage', 'current', 'power_kw', 'energy_kwh')


def write_json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def recovered_exactly(expected, recovered, uncommitted_ns):
    return (bool(expected) and [tuple(r) for r in recovered] == [tuple(r) for r in expected]
            and all(r[1] != uncommitted_ns for r in recovered))


def local_bench(config):
    return (config['mode'] == 'demo' and config['device_id'] == DEVICE
        and config['modbus']['transport'] == 'rtu' and config['modbus']['serial_port'] == 'COM4'
        and config['mqtt']['host'] == '127.0.0.1' and not config['mqtt']['tls'])


def private_config(config_path, run_id, worker_directory=None):
    """Prevent accidental standalone use of the internal destructive fixture."""
    from delta_device.config import load_config
    path = Path(config_path).resolve()
    root = path.parent
    manifest = json.loads((root / 'run.json').read_text())
    config = load_config(path)
    expected = root / 'state' / 'outbox.db'
    if (path.name != 'config.json' or not local_bench(config)
            or manifest.get('tool') != 'delta-storage-crash-v1'
            or manifest.get('run_id') != run_id
            or manifest.get('parent_pid') != os.getppid()
            or config['mqtt']['port'] != manifest.get('gate_port')
            or Path(config['outbox_path']).resolve() != expected
            or any(p.is_symlink() for p in (expected, expected.parent, root))):
        raise ValueError('internal child requires its live parent and private run configuration')
    if worker_directory is not None:
        folder = Path(worker_directory)
        if folder.is_symlink() or folder.resolve().parent != root:
            raise ValueError('worker output must be an owned cycle directory')
    return config


def cleanup_owned(children, gate, log):
    errors = []
    for child in children:
        try:
            if child is not None and child.poll() is None:
                child.kill()
                child.wait(timeout=5)
        except Exception as exc:
            errors.append('child:' + type(exc).__name__)
    for label, resource in (('gate', gate), ('log', log)):
        try:
            if resource is not None:
                resource.close()
        except Exception as exc:
            errors.append(label + ':' + type(exc).__name__)
    return errors


def child_runtime():
    env = {**os.environ, 'DELTA_SIM_NOISE': '0', 'PYTHONDONTWRITEBYTECODE': '1'}
    executable = sys.executable
    if sys.platform == 'win32':
        # A Windows venv executable is a redirector: Popen.pid is not the actual
        # interpreter PID. Bypass it so parent checks and kill target the real
        # owned child, while explicitly retaining this venv's dependencies.
        executable = sys._base_executable
        env['PYTHONPATH'] = sysconfig.get_paths()['purelib']
    return executable, env


def capacity_probe(directory):
    snapshot = dict(voltage=230, current=13, power_kw=9, energy_kwh=655.38)
    path = directory / 'capacity' / 'outbox.db'
    box = Outbox(path, 3, DEVICE)
    for i in range(3):
        box.enqueue(i + 1, encode_line(DEVICE, snapshot, i + 1), snapshot)
    before = box.pending(100)
    result = dict(queue_full_rejected=False, sqlite_full_rejected=False)
    try:
        box.enqueue(4, 'extra', snapshot)
    except OverflowError:
        result['queue_full_rejected'] = True
    queue_preserved = box.pending(100) == before
    box.limit = 100
    connect = box.connect
    @contextmanager
    def limited_pages():
        with connect() as db:
            pages = db.execute('PRAGMA page_count').fetchone()[0]
            db.execute(f'PRAGMA max_page_count={int(pages)}')
            yield db
    box.connect = limited_pages
    try:
        # Snapshot size is within the production 16 KiB bound, but exceeds the
        # deliberately frozen private DB page count.
        box.enqueue(4, 'extra', dict(snapshot, filler='x' * 12000))
    except sqlite3.OperationalError as exc:
        result['sqlite_full_rejected'] = exc.sqlite_errorcode == sqlite3.SQLITE_FULL
    finally:
        box.connect = connect
    result['pending_preserved'] = queue_preserved and box.pending(100) == before
    box.enqueue(5, 'recovery', snapshot)
    result['recovery_inserted'] = box.pending(100)[:-1] == before and box.pending_count() == 4
    with box.connect() as db:
        result['integrity_check'] = db.execute('PRAGMA integrity_check').fetchone()[0]
    corrupt = directory / 'corrupt-copy' / 'outbox.db'
    corrupt.parent.mkdir()
    shutil.copyfile(path, corrupt)
    original_bytes = corrupt.read_bytes()
    corrupt.write_bytes(b'CORRUPTED_HEADER' + original_bytes[16:])
    old_hash = hashlib.sha256(corrupt.read_bytes()).hexdigest()
    result['corrupt_rejected'] = False
    try:
        Outbox(corrupt, 3, DEVICE)
    except sqlite3.DatabaseError:
        result['corrupt_rejected'] = True
    result['corrupt_bytes_preserved'] = hashlib.sha256(corrupt.read_bytes()).hexdigest() == old_hash
    result['passed'] = all(result[k] for k in ('queue_full_rejected', 'sqlite_full_rejected',
        'pending_preserved', 'recovery_inserted', 'corrupt_rejected', 'corrupt_bytes_preserved')) \
        and result['integrity_check'] == 'ok'
    write_json(directory / 'capacity-result.json', result)
    return result


def worker(config_path, directory, run_id):
    from delta_device import edge
    config = private_config(config_path, run_id, directory)
    committed = []
    class ObservedBox(Outbox):
        def enqueue(self, sampled_ns, payload, snapshot):
            if len(committed) == 3:
                with self.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    db.execute('INSERT INTO outbox(sampled_ns,payload,snapshot) VALUES (?,?,?)',
                               (sampled_ns, payload, json.dumps(snapshot)))
                    write_json(directory / 'uncommitted.json', dict(sampled_ns=sampled_ns))
                    # Parent must force-terminate this exact child while the
                    # fourth transaction remains open, not gracefully stop it.
                    threading.Event().wait()
                raise RuntimeError('crash fixture was not terminated')
            super().enqueue(sampled_ns, payload, snapshot)
            row = self.pending(10000)[-1]
            committed.append(dict(row=list(row), sampled_ns=sampled_ns, **{k: snapshot[k] for k in FIELDS}))
            write_json(directory / 'commits.json', committed)
    with patch.object(edge, 'Outbox', ObservedBox):
        edge.run(config)


def replay(config_path, run_id):
    from delta_device.publisher import Publisher
    config = private_config(config_path, run_id)
    box = Outbox(config['outbox_path'], config['queue_limit'], DEVICE)
    publisher = Publisher(config['mqtt'], DEVICE)
    publisher.start()
    try:
        deadline = time.monotonic() + 30
        while box.pending_count() and time.monotonic() < deadline:
            drain(box, publisher.publish, 100, threading.Event())
            time.sleep(.1)
        if box.pending_count():
            raise RuntimeError('replay did not drain')
    finally:
        publisher.close()


def crash_run(config_path, directory, count):
    from bench_network import Gate
    from bench_verify import db_rows, api_rows
    from bench_ledger import reconcile
    from delta_device.config import load_config
    config = load_config(config_path)
    if not local_bench(config):
        raise ValueError('only dedicated local COM3/COM4 demo bench allowed')
    directory.mkdir(parents=True, exist_ok=False)
    gate = Gate()
    process = sim = log = None
    final_result = None
    samples, expected, cycles = [], [], []
    try:
        gate.set_blocked(True)
        config['mqtt']['port'] = gate.port
        config['mqtt']['client_id'] = 'bench-crash-' + directory.name[-30:]
        config['outbox_path'] = str(directory / 'state' / 'outbox.db')
        config['poll_interval'] = 1
        config_file = directory / 'config.json'
        write_json(config_file, config)
        run_id = uuid.uuid4().hex
        write_json(directory / 'run.json', dict(tool='delta-storage-crash-v1',
            run_id=run_id, parent_pid=os.getpid(), gate_port=gate.port))
        log = (directory / 'children.log').open('w', encoding='utf-8')
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        executable, env = child_runtime()
        cwd = Path(__file__).resolve().parents[1]
        command = [executable, str(Path(__file__).resolve())]
        sim = subprocess.Popen([executable, '-m', 'delta_device', 'simulator', '--transport',
            'rtu', '--serial-port', 'COM3'], cwd=cwd, env=env, stdout=log, stderr=log, creationflags=flags)
        time.sleep(2)
        if sim.poll() is not None:
            raise RuntimeError('owned simulator failed startup')
        for index in range(count):
            cycle = directory / f'cycle-{index:02d}'
            cycle.mkdir()
            process = subprocess.Popen(command + ['worker', '--config', str(config_file),
                '--output', str(cycle), '--run-id', run_id], cwd=cwd, env=env,
                stdout=log, stderr=log, creationflags=flags)
            deadline = time.monotonic() + 20
            marker = cycle / 'uncommitted.json'
            while not marker.exists() and time.monotonic() < deadline and process.poll() is None:
                time.sleep(.01)
            if not marker.exists():
                raise RuntimeError('child failed before crash marker')
            process.kill()
            process.wait(timeout=5)
            committed = json.loads((cycle / 'commits.json').read_text())
            uncommitted = json.loads(marker.read_text())['sampled_ns']
            expected.extend(tuple(s['row']) for s in committed)
            samples.extend({k: s[k] for k in ('sampled_ns', *FIELDS)} for s in committed)
            # Preserve DB and any journal sidecars before reopening; this alone
            # does not prove a particular hot-journal rollback path.
            for path in (directory / 'state').glob('outbox.db*'):
                shutil.copyfile(path, cycle / path.name)
            box = Outbox(config['outbox_path'], config['queue_limit'], DEVICE)
            recovered = box.pending(10000)
            with box.connect() as db:
                integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
            result = dict(index=index, killed_pid=process.pid, exit_code=process.returncode,
                committed=len(committed), pending=len(recovered), uncommitted_ns=uncommitted,
                integrity_check=integrity, recovered_exactly=recovered_exactly(expected, recovered, uncommitted))
            result['passed'] = result['committed'] == 3 and result['recovered_exactly'] and integrity == 'ok'
            cycles.append(result)
            write_json(directory / 'cycles.json', cycles)
            print(json.dumps(result), flush=True)
            if not result['passed']:
                raise RuntimeError('committed set did not survive crash')
        gate.set_blocked(False)
        process = subprocess.Popen(command + ['replay', '--config', str(config_file), '--run-id', run_id], cwd=cwd,
            env=env, stdout=log, stderr=log, creationflags=flags)
        if process.wait(timeout=40) != 0:
            raise RuntimeError('new replay process failed')
        box = Outbox(config['outbox_path'], config['queue_limit'], DEVICE)
        start, end = samples[0]['sampled_ns'], time.time_ns() // 1000 * 1000
        deadline = time.monotonic() + 30
        observations = []
        while True:
            database = reconcile(samples, db_rows(start, end))
            observations.append(dict(monotonic=time.monotonic(), received=database['received'],
                                     missing=len(database['missing'])))
            if database['pass'] or time.monotonic() >= deadline:
                break
            time.sleep(.5)
        api = reconcile(samples, api_rows(start, end))
        result = dict(cycles=cycles, database=database, api=api, observations=observations,
            pending_end=box.pending_count(),
            crash_type='forced child termination with uncommitted fourth transaction; not host power loss')
        result['passed'] = all(c['passed'] for c in cycles) and database['pass'] and api['pass'] and result['pending_end'] == 0
        final_result = result
        write_json(directory / 'samples.json', samples)
        write_json(directory / 'crash-result.json', result)
        return result
    finally:
        errors = cleanup_owned((process, sim), gate, log)
        if errors:
            write_json(directory / 'cleanup-errors.json', errors)
            if final_result is not None:
                final_result.update(passed=False, cleanup_errors=errors)
                write_json(directory / 'crash-result.json', final_result)
            raise RuntimeError('owned resource cleanup failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    for name in ('crash', 'worker', 'capacity'):
        p = sub.add_parser(name)
        p.add_argument('--output', type=Path, required=True)
        if name != 'capacity': p.add_argument('--config', required=True)
        if name == 'worker': p.add_argument('--run-id', required=True)
        if name == 'crash': p.add_argument('--count', default=10, type=int, choices=range(1, 21))
    p = sub.add_parser('replay')
    p.add_argument('--config', required=True)
    p.add_argument('--run-id', required=True)
    args = parser.parse_args()
    if args.mode == 'worker':
        worker(args.config, args.output, args.run_id)
        return 0
    if args.mode == 'replay':
        replay(args.config, args.run_id)
        return 0
    if args.mode == 'capacity':
        args.output.mkdir(parents=True, exist_ok=False)
        result = capacity_probe(args.output)
    else:
        result = crash_run(args.config, args.output.resolve(), args.count)
    print(json.dumps(result), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
