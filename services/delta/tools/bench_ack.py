"""Isolated v1 counterexamples using a real private MQTT broker and SQLite sink.

This is not the production Telegraf/Timescale receiver or a v2 implementation.
Exit zero means counterexamples were reproduced, NOT that delivery is reliable.
The caller must provide the private network-none broker namespace identifier.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from delta_device.delivery import Outbox, drain, encode_line
from delta_device.publisher import Publisher
import paho.mqtt.client as mqtt

DEVICE = 'delta-ack-probe'
TOPIC = f'ems/devices/{DEVICE}/measurements'


def isolated_namespace():
    expected = os.environ.get('DELTA_ACK_PROBE_NETNS')
    if not expected or os.readlink('/proc/self/ns/net') != expected:
        raise ValueError('private broker network namespace required')


def counterexample(record):
    if not record['ack'] or record['pending'] != 0:
        return False
    if record['kind'] == 'ack-before-commit':
        return record['observed'] == 1 and record['committed'] == 0
    if record['kind'] == 'sender-confirmation-suppressed':
        return (record['observed'] == record['committed'] == 2
            and record['pending_before_retry'] == record['first_committed'] == 1)
    if record['kind'] == 'duplicate-delivery':
        return record['observed'] == record['committed'] == 2
    return False


class Receiver:
    def __init__(self, path):
        self.path, self.drop = path, False
        self.condition, self.observed = threading.Condition(), Counter()
        self.ready, self.errors = threading.Event(), []
        db = sqlite3.connect(path)
        try:
            with db:
                db.execute('CREATE TABLE measurements(payload TEXT NOT NULL)')
        finally:
            db.close()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='isolated-v1-receiver')
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = lambda *args: self.ready.set()
        self.client.on_message = self.message

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe(TOPIC, qos=1)

    def message(self, client, userdata, message):
        payload = message.payload.decode('utf-8')
        with self.condition:
            try:
                if not self.drop:
                    db = sqlite3.connect(self.path)
                    try:
                        with db:
                            db.execute('INSERT INTO measurements(payload) VALUES (?)', (payload,))
                    finally:
                        db.close()
            except Exception as exc:
                self.errors.append(type(exc).__name__)
            finally:
                self.observed[payload] += 1
                self.condition.notify_all()

    def wait(self, payload, count):
        with self.condition:
            if not self.condition.wait_for(lambda: self.observed[payload] >= count, timeout=5):
                raise TimeoutError('private receiver did not observe message')

    def committed(self, payload):
        db = sqlite3.connect(self.path)
        try:
            return db.execute('SELECT COUNT(*) FROM measurements WHERE payload=?', (payload,)).fetchone()[0]
        finally:
            db.close()

    def start(self):
        self.client.connect('127.0.0.1', 1883)
        self.client.loop_start()
        if not self.ready.wait(5):
            raise TimeoutError('private receiver subscription failed')

    def close(self):
        self.client.disconnect()
        self.client.loop_stop()


def run(directory):
    isolated_namespace()
    directory.mkdir(parents=True, exist_ok=False)
    receiver = Receiver(directory/'receiver.db')
    publisher = Publisher(dict(host='127.0.0.1', port=1883, client_id='isolated-v1-sender', tls=False), DEVICE)
    records, result = [], None
    try:
        receiver.start()
        publisher.start()
        if not publisher.ready.wait(5):
            raise TimeoutError('private publisher did not connect')
        for index, kind in enumerate(('ack-before-commit', 'sender-confirmation-suppressed', 'duplicate-delivery')):
            box = Outbox(directory/kind/'outbox.db', 10, DEVICE)
            snapshot = dict(voltage=230+index, current=13, power_kw=9, energy_kwh=655.38)
            stamp = (time.time_ns()//1000)*1000
            payload = encode_line(DEVICE, snapshot, stamp)
            box.enqueue(stamp, payload, snapshot)
            receiver.drop = kind == 'ack-before-commit'
            if kind == 'sender-confirmation-suppressed':
                acknowledged = []
                def suppress_local_confirmation(data):
                    acknowledged.append(publisher.publish(data))
                    return False  # After actual PUBACK, inject lost local confirmation.
                sent = drain(box, suppress_local_confirmation, 10, threading.Event())
                receiver.wait(payload, 1)
                record = dict(kind=kind, actual_first_puback=acknowledged == [True],
                    first_drain_sent=sent, pending_before_retry=box.pending_count(),
                    first_committed=receiver.committed(payload))
                ack = drain(box, publisher.publish, 10, threading.Event()) == 1
                receiver.wait(payload, 2)
                ack = ack and record['actual_first_puback'] and sent == 0
            else:
                ack = drain(box, publisher.publish, 10, threading.Event()) == 1
                receiver.wait(payload, 1)
                record = dict(kind=kind)
                if kind == 'duplicate-delivery':
                    ack = publisher.publish(payload) and ack
                    receiver.wait(payload, 2)
            record.update(ack=ack, observed=receiver.observed[payload],
                committed=receiver.committed(payload), pending=box.pending_count())
            record.update(counterexample_reproduced=counterexample(record),
                          desired_delivery_invariant_met=False)
            records.append(record)
        result = dict(cases=records, receiver_errors=receiver.errors,
            reproduction_passed=all(r['counterexample_reproduced'] for r in records) and not receiver.errors,
            system_acceptance_passed=False,
            scope='Real isolated MQTT broker + production Publisher/Outbox/drain + controlled SQLite sink; not production receiver',
            fault_injection='DB unavailability is controlled no-commit; local confirmation is suppressed after actual PUBACK; no v2 ACK exists')
        (directory/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        return result
    finally:
        errors = []
        for client in (publisher, receiver):
            try:
                client.close()
            except Exception as exc:
                errors.append(type(exc).__name__)
        if errors:
            if result is not None:
                result.update(reproduction_passed=False, cleanup_errors=errors)
                (directory/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            raise RuntimeError('private MQTT clients failed cleanup')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps(result))
    return 0 if result['reproduction_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
