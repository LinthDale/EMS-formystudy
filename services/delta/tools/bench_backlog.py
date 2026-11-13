"""PRD-0020 no-Pi backlog/weak-stream experiment; never a DB-ACK guarantee."""
import argparse
from collections import Counter
from contextlib import ExitStack, closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from delta_device import edge
from delta_device.config import validate
from delta_device.delivery import Outbox, encode_line
from delta_device.poller import Poller
from delta_device.publisher import Publisher
from bench_network import Gate

LOCAL_DEVICE = 'delta-backlog-qa-20261112'


def require_scope(scope, expected, actual, device):
    if scope == 'private' and expected and expected == actual:
        return
    if scope == 'local-ems' and device == LOCAL_DEVICE:
        return
    raise ValueError('explicit private namespace or reserved local QA identity required')


def transport_delay(base, jitter, sequence):
    if base < 0 or jitter < 0 or jitter > base:
        raise ValueError('invalid delay/jitter')
    return max(0, base + jitter * ((sequence % 5) - 2) / 2)


def assess(expected, received, pending, errors, stopped):
    source, actual = Counter(expected), Counter(received)
    missing, unexpected = source - actual, actual.keys() - source.keys()
    duplicates = sum(max(0, n - source[p]) for p, n in actual.items() if p in source)
    valid_source = bool(source) and all(n == 1 for n in source.values())
    complete = valid_source and not missing and not unexpected and pending == 0 and not errors and stopped
    return dict(expected=len(expected), received=len(received),
                missing_count=sum(missing.values()), unexpected_count=sum(actual[p] for p in unexpected),
                duplicate_count=duplicates, pending_end=pending,
                completion_passed=bool(complete), unique_delivery_passed=bool(complete and not duplicates))


def assess_backup(rows, expected, minimum, latest):
    exact = rows == expected[:len(rows)]
    metadata = bool(rows) and latest == rows[-1]['sampled_ns']
    return dict(rows=len(rows), minimum_committed=minimum, exact_prefix=exact,
                metadata_matches=metadata, passed=bool(len(rows) >= minimum and exact and metadata))


class ShapedGate(Gate):
    """Loopback TCP stream shaping, not IP packet-loss emulation."""
    def __init__(self, delay, jitter, rate):
        self.delay, self.jitter, self.rate = delay, jitter, rate
        self.stats_lock = threading.Lock()
        self.stats = dict(chunks=0, bytes=0, delayed_seconds=0.0)
        super().__init__()

    def relay(self, pair):
        sequence = 0
        try:
            while not self.stopped.is_set() and not self.blocked.is_set():
                readable, _, _ = select.select(pair, [], [], .2)
                for source in readable:
                    data = source.recv(4096)
                    if not data:
                        return
                    delay = transport_delay(self.delay, self.jitter, sequence)
                    sequence += 1
                    delay += len(data) / (self.rate * 1024) if self.rate else 0
                    if self.stopped.wait(delay) or self.blocked.is_set():
                        return
                    (pair[1] if source is pair[0] else pair[0]).sendall(data)
                    with self.stats_lock:
                        self.stats['chunks'] += 1
                        self.stats['bytes'] += len(data)
                        self.stats['delayed_seconds'] += delay
        except (OSError, ValueError):
            pass  # set_blocked deliberately closes these private streams.
        finally:
            with self.lock:
                if pair in self.pairs:
                    self.pairs.remove(pair)
            for sock in pair:
                self.drop(sock)


class Sink:
    def __init__(self, path, device):
        import paho.mqtt.client as mqtt
        self.path, self.device = path, device
        self.ready, self.lock = threading.Event(), threading.Lock()
        self.errors, self.arrivals = [], []
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('CREATE TABLE received (payload TEXT NOT NULL, monotonic REAL NOT NULL)')
        self.db.commit()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id='sink-' + path.parent.name, clean_session=True)
        self.client.on_connect = self.connected
        self.client.on_subscribe = lambda *args: self.ready.set()
        self.client.on_message = self.message

    def connected(self, client, userdata, flags, reason, properties):
        if reason == 0:
            client.subscribe(f'ems/devices/{self.device}/measurements', qos=1)

    def message(self, client, userdata, message):
        with self.lock:
            try:
                stamp = time.monotonic()
                with self.db:
                    self.db.execute('INSERT INTO received VALUES (?,?)', (message.payload.decode(), stamp))
                self.arrivals.append(stamp)
            except Exception as exc:
                self.errors.append(type(exc).__name__)

    def start(self):
        self.client.connect('127.0.0.1', 1883, 30)
        self.client.loop_start()
        if not self.ready.wait(8):
            raise TimeoutError('private observer did not subscribe')

    def rows(self):
        with self.lock:
            return self.db.execute('SELECT payload FROM received ORDER BY rowid').fetchall()

    def close(self):
        self.client.disconnect()
        self.client.loop_stop()
        self.db.close()


def vector(index):
    return dict(profile='synthetic-backlog-qa', voltage=220 + (index % 200) / 100,
                current=5 + (index % 100) / 100, power_kw=1 + (index % 50) / 100,
                energy_kwh=1000 + index / 100)


def prepare_backlog(directory, box, args):
    """Back up during writes, then independently verify the whole committed prefix."""
    expected, records, errors = [], [], []
    cancelled = threading.Event()
    thread = None
    started = time.monotonic()

    def backup():
        deadline = time.monotonic() + 15
        def progress(status, remaining, total):
            if cancelled.is_set() or time.monotonic() > deadline:
                raise TimeoutError('private backup deadline')
        try:
            with closing(sqlite3.connect(box.path, timeout=3)) as source_db:
                with closing(sqlite3.connect(directory / 'backup.db', timeout=3)) as target:
                    source_db.backup(target, pages=16, progress=progress, sleep=.01)
        except Exception as exc:
            errors.append(type(exc).__name__)

    try:
        stamp0 = time.time_ns() // 1000 * 1000 - (args.preload * 5 + 3600) * 10**9
        for index in range(args.preload):
            snapshot, stamp = vector(index), stamp0 + index * 5 * 10**9
            payload = encode_line(args.device, snapshot, stamp)
            box.enqueue(stamp, payload, snapshot)
            expected.append(payload)
            records.append(dict(sampled_ns=stamp, payload=payload, snapshot=snapshot))
            if index == min(999, args.preload - 1):
                thread = threading.Thread(target=backup, daemon=True)
                thread.start()
        if thread:
            thread.join(timeout=18)
            if thread.is_alive() or errors:
                raise RuntimeError('private online backup failed')
        result = dict(prefill_seconds=time.monotonic() - started, prefill_rows=args.preload)
        if args.preload:
            with closing(sqlite3.connect(directory / 'backup.db')) as db:
                rows = [dict(sampled_ns=stamp, payload=payload, snapshot=json.loads(snapshot))
                        for stamp, payload, snapshot in db.execute(
                            'SELECT sampled_ns,payload,snapshot FROM outbox ORDER BY id')]
                latest = int(db.execute("SELECT value FROM metadata WHERE key='latest_timestamp'").fetchone()[0])
                check = assess_backup(rows, records, min(1000, args.preload), latest)
                check['integrity'] = db.execute('PRAGMA integrity_check').fetchone()[0]
            try:
                Outbox(directory / 'backup.db', args.preload + 100, 'wrong-identity')
                check['wrong_identity_rejected'] = False
            except ValueError:
                check['wrong_identity_rejected'] = True
            result['backup'] = check
        (directory / 'preloaded-records.json').write_text(json.dumps(records, indent=2))
        return expected, result
    finally:
        cancelled.set()
        if thread:
            thread.join(timeout=5)
            if thread.is_alive():
                raise RuntimeError('backup thread failed to stop')


def run(args):
    actual_ns = os.readlink('/proc/self/ns/net') if sys.platform == 'linux' else None
    require_scope(args.scope, os.environ.get('BACKLOG_QA_NETNS'), actual_ns, args.device)
    if not (0 <= args.preload <= 100000 and 0 <= args.live_count <= 300
            and 0 < args.deadline <= 600 and args.preload + args.live_count > 0):
        raise ValueError('bounded preload/live/deadline required')
    transport_delay(args.rtt_ms / 2000, args.jitter_ms / 2000, 0)
    if not 0 <= args.rate_kib <= 1024 or not 0 <= args.initial_offline <= 60:
        raise ValueError('invalid rate/offline duration')
    flaps = []
    for item in filter(None, args.flaps.split(',')):
        offset, duration = map(float, item.split(':'))
        if offset < 0 or duration <= 0 or offset + duration >= args.deadline:
            raise ValueError('invalid flap bounds')
        if flaps and offset < sum(flaps[-1]):
            raise ValueError('overlapping flaps')
        flaps.append((offset, duration))
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    result = dict(scope=args.scope, device_id=args.device, started_utc=datetime.now(timezone.utc).isoformat(),
                  production_db_ack=False, passed=False, configured=vars(args) | {'output': str(directory)})
    lock = threading.Lock()
    expected, commits, network, resources, errors, shutdown, connections = [], [], [], [], [], {}, []
    finished, control_stop = threading.Event(), threading.Event()
    simulator = gate = sink = worker = control = None
    log = None
    source_root = Path(__file__).resolve().parents[1]
    source = {str(p.relative_to(source_root)): hashlib.sha256(p.read_bytes()).hexdigest()
              for base in ('delta_device', 'tools') for p in (source_root / base).glob('*.py')}
    (directory / 'source-sha256.json').write_text(json.dumps(source, indent=2))
    box_path = directory / 'state/outbox.db'
    box = Outbox(box_path, args.preload + args.live_count + 100, args.device)
    try:
        expected, preparation = prepare_backlog(directory, box, args)
        result.update(preparation)
    except Exception as exc:
        result.update(error_kind=type(exc).__name__, finished_utc=datetime.now(timezone.utc).isoformat())
        (directory / 'result.json').write_text(json.dumps(result, indent=2))
        raise
    (directory / 'preloaded-payloads.json').write_text(json.dumps(expected, indent=2))

    class ObservedBox(Outbox):
        def enqueue(self, stamp, payload, snapshot):
            super().enqueue(stamp, payload, snapshot)
            with lock:
                expected.append(payload)
                commits.append(dict(monotonic=time.monotonic(), sampled_ns=stamp, snapshot=snapshot, payload=payload))

    class WindowComplete(ValueError):
        pass

    class ObservedPoller(Poller):
        def sample(self):
            with lock:
                if len(commits) >= args.live_count:
                    raise WindowComplete('controlled measurement count reached')
            return super().sample()

    class ObservedPublisher(Publisher):
        def on_connect(self, *values):
            super().on_connect(*values)
            if self.ready.is_set():
                connections.append(time.monotonic())

    def runtime(config):
        try:
            edge.run(config)
        except Exception as exc:
            errors.append(type(exc).__name__)
        finally:
            finished.set()

    def controls(origin):
        if args.initial_offline:
            if control_stop.wait(args.initial_offline):
                return
            gate.set_blocked(False)
            network.append(dict(kind='online', monotonic=time.monotonic()))
        for offset, duration in flaps:
            if control_stop.wait(max(0, origin + offset - time.monotonic())):
                return
            gate.set_blocked(True)
            network.append(dict(kind='offline', monotonic=time.monotonic(), live_committed=len(commits)))
            if control_stop.wait(duration):
                return
            gate.set_blocked(False)
            network.append(dict(kind='online', monotonic=time.monotonic()))

    try:
        sink = Sink(directory / 'received.db', args.device)
        sink.start()
        gate = ShapedGate(args.rtt_ms / 2000, args.jitter_ms / 2000, args.rate_kib)
        if args.initial_offline:
            gate.set_blocked(True)
            network.append(dict(kind='offline', monotonic=time.monotonic()))
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        log = (directory / 'simulator.log').open('w')
        simulator = subprocess.Popen([sys.executable, '-m', 'delta_device', 'simulator', '--port', str(port)],
                                     stdout=log, stderr=log)
        until = time.monotonic() + 8
        while True:
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                if simulator.poll() is not None or time.monotonic() > until:
                    raise RuntimeError('private simulator failed startup')
                time.sleep(.05)
        config = validate(dict(mode='demo', device_id=args.device, poll_interval=1,
            queue_limit=args.preload + args.live_count + 100, batch_size=100, outbox_path=str(box_path),
            modbus=dict(transport='tcp', host='127.0.0.1', port=port, timeout=1, unit_id=1, address_base=1),
            mqtt=dict(host='127.0.0.1', port=gate.port, client_id='sender-' + directory.name, tls=False)))
        origin, cpu_start = time.monotonic(), time.process_time()
        with ExitStack() as stack:
            for name, value in [('Outbox', ObservedBox), ('Poller', ObservedPoller), ('Publisher', ObservedPublisher)]:
                stack.enter_context(patch.object(edge, name, value))
            stack.enter_context(patch.object(edge.signal, 'signal', lambda sig, fn: shutdown.__setitem__(sig, fn)))
            worker = threading.Thread(target=runtime, args=(config,))
            worker.start()
            control = threading.Thread(target=controls, args=(origin,))
            control.start()
            deadline = origin + args.deadline
            while time.monotonic() < deadline:
                pending = box.pending_count()
                resources.append(dict(elapsed=time.monotonic() - origin, pending=pending,
                    live_committed=len(commits), received=len(sink.arrivals),
                    sqlite_bytes=box_path.stat().st_size, process_cpu_seconds=time.process_time() - cpu_start))
                if (len(commits) == args.live_count and pending == 0
                        and len(sink.arrivals) >= len(expected) and not control.is_alive()):
                    break
                if finished.is_set():
                    raise RuntimeError('edge stopped before measurement completed')
                time.sleep(.2)
            else:
                errors.append('measurement_deadline_exceeded')
            if signal.SIGTERM in shutdown:
                shutdown[signal.SIGTERM](None, None)
            worker.join(timeout=15)
        rows = [r[0] for r in sink.rows()]
        result.update(assess(expected, rows, box.pending_count(), errors + sink.errors, not worker.is_alive()))
        result.update(live_committed=len(commits), runtime_seconds=time.monotonic() - origin,
                      publisher_connections=connections, network_events=network, gate_stats=gate.stats,
                      max_pending=max(r['pending'] for r in resources), errors=errors + sink.errors)
        if sink.arrivals:
            result['observed_receive_per_second'] = (len(rows) - 1) / max(.001, sink.arrivals[-1] - sink.arrivals[0])
        result['passed'] = result['completion_passed'] and len(commits) == args.live_count
        if flaps:
            result['flap_contract_passed'] = (len(connections) >= len(flaps) + 1
                and sum(e['kind'] == 'offline' for e in network) == len(flaps) + bool(args.initial_offline))
            result['passed'] = result['passed'] and result['flap_contract_passed']
        if args.preload:
            result['passed'] = result['passed'] and all((result['backup']['passed'],
                result['backup']['integrity'] == 'ok', result['backup']['wrong_identity_rejected']))
        (directory / 'expected-payloads.json').write_text(json.dumps(expected, indent=2))
        (directory / 'received-payloads.json').write_text(json.dumps(rows, indent=2))
        (directory / 'live-commits.json').write_text(json.dumps(commits, indent=2))
        (directory / 'resources.json').write_text(json.dumps(resources, indent=2))
    except Exception as exc:
        result.update(passed=False, error_kind=type(exc).__name__)
        raise
    finally:
        control_stop.set()
        cleanup_errors = []
        if control:
            control.join(timeout=3)
        if worker and worker.is_alive() and signal.SIGTERM in shutdown:
            shutdown[signal.SIGTERM](None, None)
            worker.join(timeout=15)
        if worker and worker.is_alive():
            cleanup_errors.append('edge_thread_alive')
        for obj in (gate, sink):
            if obj:
                try:
                    obj.close()
                except Exception as exc:
                    cleanup_errors.append(type(exc).__name__)
        if simulator:
            simulator.terminate()
            try:
                simulator.wait(timeout=5)
            except subprocess.TimeoutExpired:
                simulator.kill()
                simulator.wait(timeout=5)
        if log:
            log.close()
        result['sources_unchanged'] = all(hashlib.sha256((source_root / p).read_bytes()).hexdigest() == h
                                          for p, h in source.items())
        result.update(cleanup_errors=cleanup_errors, finished_utc=datetime.now(timezone.utc).isoformat())
        result['passed'] = bool(result.get('passed') and not cleanup_errors and result['sources_unchanged'])
        (directory / 'result.json').write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scope', choices=['private', 'local-ems'], required=True)
    parser.add_argument('--device', default='delta-private-qa')
    parser.add_argument('--preload', type=int, default=0)
    parser.add_argument('--live-count', type=int, default=60)
    parser.add_argument('--deadline', type=float, default=240)
    parser.add_argument('--rtt-ms', type=float, default=0)
    parser.add_argument('--jitter-ms', type=float, default=0)
    parser.add_argument('--rate-kib', type=float, default=0)
    parser.add_argument('--initial-offline', type=float, default=0)
    parser.add_argument('--flaps', default='')
    values = parser.parse_args()
    outcome = run(values)
    print(json.dumps(outcome))
    raise SystemExit(0 if outcome['passed'] else 1)
