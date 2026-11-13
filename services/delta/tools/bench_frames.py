"""Bounded physical RTU fault injector; only run after both bench COM ports are free.

Uses independent literal register values, real USB wires and the production
Poller.read path. Does not write telemetry or connect to MQTT.
"""
import argparse
import json
from pathlib import Path
import struct
import sys
import threading
import time

KINDS = ('fragment', 'truncated', 'crc', 'wrong_unit', 'silent', 'late')


def crc(data):
    value = 0xffff
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0xa001 if value & 1 else 0)
    return struct.pack('<H', value)


def response(value, unit=1):
    body = struct.pack('>BBBH', unit, 4, 2, value)
    return body + crc(body)


def chunks(kind, frame, timeout):
    if kind == 'fragment':
        return [(0, frame[:2]), (.03, frame[2:4]), (.03, frame[4:])]
    if kind == 'truncated':
        return [(0, frame[:-2])]
    if kind == 'crc':
        return [(0, frame[:-1] + bytes([frame[-1] ^ 1]))]
    if kind == 'wrong_unit':
        body = bytes([2]) + frame[1:-2]
        return [(0, body + crc(body))]
    if kind in ('silent', 'late'):
        return []
    raise ValueError('unknown fault')


def reply_chunks(kind, index, timeout):
    if index == 1:
        return chunks(kind, response(2300), timeout)
    if index == 2:
        # The main thread sends request 2 only after read 1 has returned.
        # Synchronize on that request rather than guessing pymodbus's deadline.
        if kind == 'late':
            return [(0, response(2300)), (.1, response(2400))]
        return [(0, response(2400))]
    raise ValueError('only two transactions per case')


def case(kind, sim_port, master_port, timeout):
    import serial
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from delta_device.poller import Poller, ReadError

    config = dict(transport='rtu', serial_port=master_port, baudrate=19200,
                  unit_id=1, address_base=1, timeout=timeout)
    record = dict(kind=kind, requests=[], request_times=[], sends=[], errors=[])
    stop = threading.Event()
    poller = Poller(config)
    with serial.Serial(sim_port, 19200, timeout=.05, write_timeout=1) as device:
        device.reset_input_buffer()

        def serve():
            pending = b''
            try:
                while not stop.is_set():
                    pending += device.read(8 - len(pending))
                    if len(pending) < 8:
                        continue
                    request, pending = pending[:8], pending[8:]
                    record['requests'].append(request.hex())
                    record['request_times'].append(time.monotonic())
                    if request[-2:] != crc(request[:-2]) or request[:2] != b'\x01\x04':
                        raise ValueError('invalid request')
                    index = len(record['requests'])
                    expected_address = 49152 if index == 1 else 49153
                    if struct.unpack('>HH', request[2:6]) != (expected_address, 1) or index > 2:
                        raise ValueError('unexpected request address/count')
                    pieces = reply_chunks(kind, index, timeout)
                    for delay, data in pieces:
                        if stop.wait(delay):
                            return
                        device.write(data)
                        device.flush()
                        record['sends'].append(dict(monotonic=time.monotonic(), hex=data.hex()))
            except Exception as exc:
                record['errors'].append(type(exc).__name__)

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        try:
            if not poller.client.connect():
                raise RuntimeError('master connection failed')
            for key, reference in (('first', 49153), ('recovery', 49154)):
                start = time.monotonic()
                try:
                    values = poller.read(reference, 1)
                    record[key] = dict(accepted=True, values=values)
                except ReadError:
                    record[key] = dict(accepted=False, values=None)
                record[key]['seconds'] = time.monotonic() - start
                record[key]['finished'] = time.monotonic()
        finally:
            poller.client.close()
            stop.set()
            worker.join(timeout=timeout + 2)
            if worker.is_alive():
                record['errors'].append('worker_not_stopped')
    first, recovery = record['first'], record['recovery']
    expected = (first['accepted'] and first['values'] == [2300]
                and first['seconds'] < timeout) if kind == 'fragment' else not first['accepted']
    record['passed'] = bool(expected and recovery['values'] == [2400]
                            and len(record['requests']) == 2 and not record['errors'])
    if kind == 'late':
        record['late_order_verified'] = bool(len(record['request_times']) == 2 and record['sends']
            and first['finished'] <= record['request_times'][1] <= record['sends'][0]['monotonic'])
        record['passed'] = record['passed'] and record['late_order_verified']
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sim-port', default='COM3')
    parser.add_argument('--master-port', default='COM4')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--count', type=int, default=20)
    parser.add_argument('--timeout', type=float, default=3)
    args = parser.parse_args()
    if args.sim_port != 'COM3' or args.master_port != 'COM4':
        parser.error('this isolated bench requires the verified COM3/COM4 pair')
    if not 1 <= args.count <= 100 or not .5 <= args.timeout <= 5:
        parser.error('count 1..100; timeout .5..5')
    args.output.mkdir(parents=True, exist_ok=False)
    records = []
    with (args.output / 'cases.jsonl').open('w', encoding='utf-8') as stream:
        for kind in KINDS:
            for index in range(args.count):
                result = case(kind, args.sim_port, args.master_port, args.timeout)
                result['index'] = index
                records.append(result)
                stream.write(json.dumps(result) + '\n')
                stream.flush()
            print(json.dumps(dict(kind=kind, passed=sum(r['passed'] for r in records if r['kind'] == kind),
                                  count=args.count)), flush=True)
    summary = {k: dict(count=args.count, passed=sum(r['passed'] for r in records if r['kind'] == k))
               for k in KINDS}
    summary['passed'] = all(r['passed'] for r in records)
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
