"""Complete production samples over COM3/COM4; no MQTT or telemetry writes.

The one-second lifetime is a controlled laboratory fixture contract. It does
not qualify a Delta device, driver combination, or arbitrary delayed replies.
"""
import argparse
import json
from pathlib import Path
import struct
import sys
import threading
import time

from bench_frames import crc

GUARD = 1.0


def frame(address, count, fresh):
    words = {
        (40994, 1): [1],
        (49151, 13): [9360 if fresh else 9000]
            + [2400 if fresh else 2300, 1300, 3000, 6000] * 3,
        (53247, 9): [123, 1, 0, 0, 2, 1, 0, 0, 2],
    }
    if (address, count) not in words:
        raise ValueError('unexpected register block')
    data = struct.pack('>' + 'H' * count, *words[address, count])
    body = bytes((1, 4, len(data))) + data
    return body + crc(body)


def verdict(record):
    common = (not record['errors'] and record['first_failed'] and record['blocked']
        and record['queued_old_bytes'] == 31 and record['requests_before'] == 2
        and record['requests_after_block'] == 2)
    if record['kind'] == 'unknown':
        return bool(common and record['request_count'] == 2 and record['recovered'] is None)
    if record['kind'] != 'bounded':
        return False
    snapshot = record['recovered'] or {}
    return bool(common and record['request_count'] == 5 and record['late_inside_guard']
        and record['guard_respected'] and snapshot.get('voltage') == 240
        and snapshot.get('power_kw') == 9.36)


def case(kind, timeout):
    import serial
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from delta_device.poller import Poller, ReadError, RecoveryPending, SynchronizationUncertain

    config = dict(transport='rtu', serial_port='COM4', baudrate=19200,
                  unit_id=1, address_base=1, timeout=timeout)
    if kind == 'bounded':
        config.update(response_lifetime_seconds=GUARD,
            response_lifetime_source='COM3 controlled lab fixture: no bytes after 1s guard; not Delta qualification')
    record = dict(kind=kind, errors=[], requests=[], first_failed=False, blocked=False,
        queued_old_bytes=0, requests_before=0, requests_after_block=0, request_count=0,
        recovered=None, late_inside_guard=False, guard_respected=False)
    poller = Poller(config)
    stop = threading.Event()
    with serial.Serial('COM3', 19200, timeout=.05, write_timeout=1) as device:
        device.reset_input_buffer()
        def serve():
            pending, round_number = b'', 0
            try:
                while not stop.is_set():
                    pending += device.read(8 - len(pending))
                    if len(pending) < 8:
                        continue
                    packet, pending = pending[:8], pending[8:]
                    if packet[-2:] != crc(packet[:-2]) or packet[:2] != b'\x01\x04':
                        raise ValueError('invalid master request')
                    address, count = struct.unpack('>HH', packet[2:6])
                    record['requests'].append(dict(address=address, count=count,
                                                   monotonic=time.monotonic()))
                    if address == 40994:
                        round_number += 1
                    response = frame(address, count, round_number >= 2)
                    if address == 49151 and round_number == 1:
                        continue  # First complete sample must fail at the AC block.
                    device.write(response)
                    device.flush()
            except Exception as exc:
                record['errors'].append(type(exc).__name__)
        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        try:
            started = time.monotonic()
            try:
                poller.sample()
            except ReadError as exc:
                record['first_failed'] = True
                record['first_error'] = type(exc).__name__
            failed_at = time.monotonic()
            record['failure_seconds'] = failed_at - started
            record['failed_at'] = failed_at
            record['guard_started_at'] = poller._uncertain_since
            guard_deadline = poller._uncertain_since + GUARD
            record['guard_deadline'] = guard_deadline
            record['requests_before'] = len(record['requests'])
            if not record['first_failed']:
                raise RuntimeError('first sample unexpectedly succeeded')
            # Explicitly reopen the poisoned old handle to queue real old bytes.
            # The production lock must survive this reconnect and discard them
            # when qualified recovery builds its new client/framer.
            if not poller.client.connect():
                raise RuntimeError('cannot reopen old fixture handle')
            device.write(frame(49151, 13, False))
            device.flush()
            record['late_sent_at'] = time.monotonic()
            deadline = time.monotonic() + .5
            while poller.client.socket.in_waiting < 31 and time.monotonic() < deadline:
                time.sleep(.005)
            record['queued_old_bytes'] = poller.client.socket.in_waiting
            try:
                poller.sample()
            except (RecoveryPending, SynchronizationUncertain):
                record['blocked'] = True
            time.sleep(.05)
            record['requests_after_block'] = len(record['requests'])
            if kind == 'bounded':
                record['late_inside_guard'] = record['late_sent_at'] < guard_deadline
                time.sleep(max(0, poller.recovery_remaining) + .02)
                record['recovered'] = poller.sample()
                record['guard_respected'] = (len(record['requests']) >= 3
                    and record['requests'][2]['monotonic'] >= guard_deadline)
        finally:
            poller.client.close()
            stop.set()
            worker.join(timeout=2)
            if worker.is_alive():
                record['errors'].append('worker_not_stopped')
    record['request_count'] = len(record['requests'])
    record['passed'] = verdict(record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--count', default=20, type=int)
    parser.add_argument('--timeout', default=3, type=int, choices=range(1, 6))
    args = parser.parse_args()
    if not 1 <= args.count <= 100:
        parser.error('count must be 1..100')
    args.output.mkdir(parents=True, exist_ok=False)
    records = []
    with (args.output / 'cases.jsonl').open('w', encoding='utf-8') as stream:
        for kind in ('unknown', 'bounded'):
            for index in range(args.count):
                record = case(kind, args.timeout)
                record['index'] = index
                records.append(record)
                stream.write(json.dumps(record) + '\n')
                stream.flush()
                print(json.dumps(dict(kind=kind, index=index, passed=record['passed'])), flush=True)
    summary = {kind: dict(count=args.count, passed=sum(r['passed'] for r in records if r['kind'] == kind))
               for kind in ('unknown', 'bounded')}
    summary.update(passed=all(r['passed'] for r in records), timeout=args.timeout,
                   lab_response_lifetime_seconds=GUARD, mqtt_connected=False)
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
