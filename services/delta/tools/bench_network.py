"""Five-minute outage of only this bench publisher, using a loopback TCP gate."""
import argparse
from collections import Counter
import json
from pathlib import Path
import select
import socket
import threading
import time
from unittest.mock import patch


def offline_result(events):
    starts = [e for e in events if e['kind'] == 'window_start']
    offs = [e for e in events if e['kind'] == 'network_off']
    ons = [e for e in events if e['kind'] == 'network_on']
    if len(starts) != 1 or len(offs) != 1 or len(ons) != 1:
        return dict(passed=False, reason='missing_or_duplicate_window')
    start, off, on = starts[0], offs[0]['monotonic'], ons[0]['monotonic']
    slots = {i for i in range(start['count'])
             if off <= start['origin'] + i * start['interval'] < on}
    commits = Counter(e['slot'] for e in events if e['kind'] == 'committed')
    acknowledgments = [e for e in events if e['kind'] == 'broker_ack' and off <= e['monotonic'] < on]
    connections = [e['monotonic'] for e in events if e['kind'] == 'publisher_connected']
    instance_count = sum(e['kind'] == 'publisher_started' for e in events)
    errors = [e for e in events if e['kind'] == 'network_control_error']
    passed = (on - off >= 300 and len(slots) == 60 and all(commits[i] == 1 for i in slots)
              and not acknowledgments and instance_count == 1
              and any(t < off for t in connections) and any(t >= on for t in connections)
              and not errors)
    return dict(passed=bool(passed), offline_seconds=on-off, slots=sorted(slots),
                committed=sum(commits[i] for i in slots), publisher_instances=instance_count,
                acks_during_outage=len(acknowledgments), connections=connections, errors=errors)


class Gate:
    """Private localhost listener; no firewall changes and no shared broker stop."""
    def __init__(self):
        self.stopped = threading.Event()
        self.blocked = threading.Event()
        self.lock = threading.Lock()
        self.pairs = []
        self.workers = []
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(4)
        self.listener.settimeout(.2)
        self.port = self.listener.getsockname()[1]
        self.acceptor = threading.Thread(target=self.accept, daemon=True)
        self.acceptor.start()

    @staticmethod
    def drop(sock):
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()

    def set_blocked(self, blocked):
        with self.lock:
            if blocked:
                self.blocked.set()
                for pair in self.pairs:
                    for sock in pair:
                        self.drop(sock)
            else:
                self.blocked.clear()

    def relay(self, pair):
        try:
            while not self.stopped.is_set() and not self.blocked.is_set():
                readable, _, _ = select.select(pair, [], [], .2)
                for source in readable:
                    data = source.recv(65536)
                    if not data:
                        return
                    target = pair[1] if source is pair[0] else pair[0]
                    target.sendall(data)
        except (OSError, ValueError):
            pass  # Closing the gate intentionally breaks both sockets.
        finally:
            with self.lock:
                if pair in self.pairs:
                    self.pairs.remove(pair)
            for sock in pair:
                self.drop(sock)

    def accept(self):
        while not self.stopped.is_set():
            try:
                client, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            upstream = None
            try:
                if self.blocked.is_set():
                    self.drop(client)
                    continue
                upstream = socket.create_connection(('127.0.0.1', 1883), timeout=2)
                client.settimeout(2)
                with self.lock:
                    if self.blocked.is_set() or self.stopped.is_set():
                        self.drop(client)
                        self.drop(upstream)
                        continue
                    pair = (client, upstream)
                    self.pairs.append(pair)
                worker = threading.Thread(target=self.relay, args=(pair,), daemon=True)
                self.workers.append(worker)
                worker.start()
            except OSError:
                self.drop(client)
                if upstream:
                    self.drop(upstream)

    def close(self):
        self.stopped.set()
        self.set_blocked(True)
        self.listener.close()
        self.acceptor.join(timeout=3)
        for worker in self.workers:
            worker.join(timeout=3)
        if self.acceptor.is_alive() or any(w.is_alive() for w in self.workers):
            raise RuntimeError('gate workers did not stop')


def run(config_path, directory):
    import bench_run
    from bench_verify import verify
    from delta_device.config import load_config
    config = load_config(config_path)
    config['poll_interval'] = 5
    ledger_ready = threading.Event()
    controller_stop = threading.Event()
    state = {}
    gate = Gate()
    config['mqtt']['port'] = gate.port

    class ObservedLedger(bench_run.Ledger):
        def __init__(self, path):
            super().__init__(path)
            state['ledger'] = self

        def add(self, kind, **data):
            super().add(kind, **data)
            if kind == 'window_start':
                state['origin'] = data['origin']
                ledger_ready.set()

    class ObservedPublisher(bench_run.Publisher):
        def start(self):
            state['ledger'].add('publisher_started')
            super().start()

        def on_connect(self, client, userdata, flags, reason_code, properties):
            super().on_connect(client, userdata, flags, reason_code, properties)
            if reason_code == 0:
                state['ledger'].add('publisher_connected')

        def on_disconnect(self, *args):
            super().on_disconnect(*args)
            state['ledger'].add('publisher_disconnected')

    def control():
        try:
            while not ledger_ready.wait(.1):
                if controller_stop.is_set():
                    return
            # Nine seconds leaves a one-second margin before slot 2; exactly
            # sixty scheduled slots (2..61) fall into the 300-second outage.
            if controller_stop.wait(max(0, state['origin'] + 9 - time.monotonic())):
                return
            gate.set_blocked(True)
            state['ledger'].add('network_off')
            if controller_stop.wait(300):
                return
            state['restored'] = time.monotonic()
            state['ledger'].add('network_on')
            gate.set_blocked(False)
        except Exception as exc:
            state['ledger'].add('network_control_error', error=type(exc).__name__)

    controller = threading.Thread(target=control, daemon=True)
    try:
        controller.start()
        with patch.multiple(bench_run, Ledger=ObservedLedger, Publisher=ObservedPublisher):
            summary = bench_run.run_bench(config, directory, 80, 'day', 'COM3', [])
        delivery = verify(directory, 15)
        result = offline_result(state['ledger'].events)
        result['database_verified_after_restore_seconds'] = time.monotonic() - state.get('restored', 0)
        result['passed'] = bool(result['passed'] and summary['pass'] and delivery['passed']
                                and result['database_verified_after_restore_seconds'] <= 120)
        (directory / 'network-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result), flush=True)
        return result
    finally:
        controller_stop.set()
        controller.join(timeout=5)
        gate.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.config, args.output.resolve())
    raise SystemExit(0 if result['passed'] else 1)
