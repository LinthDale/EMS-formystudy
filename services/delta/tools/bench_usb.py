"""Observe ONE user-operated USB unplug/replug during a five-minute bench run.

Never disables or unplugs a device programmatically. Starts only the owned sim;
the operator must identify the specified adapter before any physical action.
"""
import argparse
import json
from pathlib import Path
import threading
import time
from unittest.mock import patch

SERIALS = {'COM3':'BG04PB77A', 'COM4':'BG04PB7RA'}
PROBE_SECONDS = .5


def summarize_usb(events):
    offs = [e for e in events if e['kind']=='usb_absent']
    ons = [e for e in events if e['kind']=='usb_present']
    if len(offs) != 1 or len(ons) != 1:
        return dict(automatic_recovery=False, reason='require_exactly_one_unplug_replug')
    off, on = offs[0]['monotonic'], ons[0]['monotonic']
    last_absent_lower = ons[0].get('last_absent_lower')
    if last_absent_lower is None or not off <= last_absent_lower <= on:
        return dict(automatic_recovery=False, reason='missing_absent_probe_bound')
    reads = [e for e in events if e['kind']=='read_ok' and e['started'] >= on]
    delay = min([e['monotonic']-last_absent_lower for e in reads] or [float('inf')])
    false_values = [e for e in events if e['kind']=='read_ok'
                    and off <= e['started'] and e['monotonic'] < last_absent_lower]
    failures = [e for e in events if e['kind']=='read_error' and off <= e['monotonic'] < on]
    wrong_usb = [e for e in events if e['kind']=='usb_other_missing']
    return dict(automatic_recovery=bool(28 <= on-off <= 60 and ons[0]['same_port']
                and delay <= 15 and failures and not false_values and not wrong_usb),
                absent_seconds=on-off, recovery_seconds_upper=delay if reads else None,
                spanning_reads=sum(e['kind']=='read_ok' and e.get('started',on)<on<=e['monotonic'] for e in events),
                same_port=ons[0]['same_port'], false_values=len(false_values), read_errors=len(failures),
                wrong_usb_events=len(wrong_usb))


def run(config_path, directory, target):
    import serial.tools.list_ports
    import bench_run
    from bench_verify import verify
    from delta_device.config import load_config

    config = load_config(config_path)
    if config['modbus']['serial_port'] != 'COM4':
        raise ValueError('fixed verified bench requires COM4 master')
    initial = {p.device:p.serial_number for p in serial.tools.list_ports.comports()}
    if any(initial.get(p) != serial for p,serial in SERIALS.items()):
        raise ValueError('USB identity changed; inventory before testing')
    config['poll_interval'] = 5
    stopped = threading.Event()
    other = 'COM4' if target == 'COM3' else 'COM3'
    state = {'ledger':None}
    monitor = None

    def observe():
        absent = False
        last_absent_lower = None
        other_missing = False
        try:
            while not stopped.is_set():
                probe_started = time.monotonic()
                ports = {p.serial_number:p.device for p in serial.tools.list_ports.comports()}
                present = SERIALS[target] in ports
                if not present and not absent:
                    state['ledger'].add('usb_absent', port=target, serial=SERIALS[target])
                    print('USB_ABSENT '+target, flush=True)
                elif present and absent:
                    state['ledger'].add('usb_present', port=ports[SERIALS[target]],
                                        same_port=ports[SERIALS[target]] == target,
                                        last_absent_lower=last_absent_lower)
                    print('USB_PRESENT '+ports[SERIALS[target]], flush=True)
                absent = not present
                if absent:
                    # Enumeration duration is unknown: its start is a conservative
                    # lower bound on the last observation of absence.
                    last_absent_lower = probe_started
                if SERIALS[other] not in ports and not other_missing:
                    state['ledger'].add('usb_other_missing', port=other)
                other_missing = SERIALS[other] not in ports
                stopped.wait(PROBE_SECONDS)
        except Exception as exc:
            state['ledger'].add('usb_monitor_error', error=type(exc).__name__)

    class UsbLedger(bench_run.Ledger):
        def __init__(self, path):
            super().__init__(path)
            state['ledger'] = self

        def add(self, kind, **data):
            nonlocal monitor
            if kind == 'window_end':
                stopped.set()
                if monitor:
                    monitor.join(timeout=3)
                    if monitor.is_alive():
                        super().add('usb_monitor_error', error='monitor_did_not_stop')
            super().add(kind, **data)
            if kind == 'window_start':
                monitor = threading.Thread(target=observe, daemon=True)
                monitor.start()
                print('USB_TEST_READY target='+target+' serial='+SERIALS[target], flush=True)

    try:
        with patch.object(bench_run, 'Ledger', UsbLedger):
            summary = bench_run.run_bench(config, directory, 60, 'day', 'COM3', [])
        events = state['ledger'].events
        result = summarize_usb(events)
        result['target'] = target
        result['monitor_errors'] = [e for e in events if e['kind']=='usb_monitor_error']
        result['unexpected_errors'] = []
        offs = [e for e in events if e['kind']=='usb_absent']
        ons = [e for e in events if e['kind']=='usb_present']
        if len(offs)==len(ons)==1:
            lower = offs[0]['monotonic'] - config['modbus']['timeout']
            upper = ons[0]['monotonic'] + 15
            result['unexpected_errors'] = [e for e in events if e['kind'] in
                ('read_error','storage_error','clock_error') and
                (e['kind'] != 'read_error' or not lower <= e['monotonic'] <= upper)]
            origin = next(e['origin'] for e in events if e['kind']=='window_start')
            result['unclassified_slots'] = [i for i in summary['missing_slots']
                                             if not lower <= origin+i*5 <= upper]
        else:
            result['unclassified_slots'] = summary['missing_slots']
        verification = verify(directory, 30)
        result['passed'] = bool(result['automatic_recovery'] and verification['passed']
            and not result['monitor_errors'] and not result['unexpected_errors']
            and not result['unclassified_slots'] and not summary['ledger_error']
            and not summary['golden_errors'] and summary['pending_end']==0
            and summary['valid']==summary['committed'] and not summary['duplicate_attempt_slots']
            and not summary['duplicate_read_slots'] and not summary['duplicate_commit_slots'])
        (directory/'usb-result.json').write_text(json.dumps(result,indent=2), encoding='utf-8')
        print(json.dumps(result), flush=True)
        return result
    finally:
        stopped.set()
        if monitor:
            monitor.join(timeout=3)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target', choices=('COM3','COM4'), required=True)
    args = parser.parse_args()
    result = run(args.config, args.output.resolve(), args.target)
    raise SystemExit(0 if result['passed'] else 1)
