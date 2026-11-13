"""Bounded Windows physical bench: observe the real edge.run, never change its loop.

PRD-0020 FR-2003/2005 acceptance tool. Local demo only. Each run needs a new
output directory and uses its own SQLite file. No shared services are stopped.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import logging
import math
import os
import queue
import shutil
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from delta_device import edge
from delta_device.config import load_config
from delta_device.delivery import Outbox, ClockGuard
from delta_device.poller import Poller
from delta_device.publisher import Publisher
from bench_ledger import FIELDS, summarize_slots, validate_outages, summarize_outages, golden_errors


class BenchWindowComplete(BaseException):
    """End instrumentation without recording a fictitious production read error."""


def slot_observation(origin, deadline, observed, interval, count):
    """Label the scheduled poll, not the clock bucket in which it woke up.

    Only the scheduler's on-grid deadline is converted to an integer slot.
    Actual early/late wake time is preserved as a signed delay; no timing
    tolerance rounds observations forward or hides genuine skipped slots.
    """
    values = (origin, deadline, observed, interval)
    try:
        valid = all(type(value) in (int, float) and math.isfinite(value) for value in values)
    except OverflowError:
        valid = False
    if (not valid or interval <= 0 or type(count) is not int or count < 1
            or deadline < origin or observed < origin):
        raise ValueError('invalid bench schedule')
    slot = round((deadline - origin) / interval)
    # This bound covers floating-point representation only, not clock jitter.
    precision = 4 * max(math.ulp(origin), math.ulp(deadline))
    if precision >= interval / 4 or not math.isclose(
            deadline, origin + slot * interval, rel_tol=0, abs_tol=precision):
        raise ValueError('bench deadline is not on the schedule grid')
    return slot, observed - deadline, slot >= count or observed >= origin + count * interval


class Ledger:
    def __init__(self, directory):
        self.directory = directory
        self.lock = threading.Lock()
        self.events = []
        self.queue = queue.Queue(maxsize=10000)
        self.error = None
        self.writer = threading.Thread(target=self.write, daemon=True)
        self.writer.start()

    def write(self):
        try:
            with (self.directory / "events.jsonl").open("a", encoding="utf-8") as stream:
                last_sync = time.monotonic()
                while True:
                    event = self.queue.get()
                    if event is None:
                        break
                    stream.write(json.dumps(event, allow_nan=False) + "\n")
                    stream.flush()
                    if time.monotonic() - last_sync >= 1:
                        os.fsync(stream.fileno())
                        last_sync = time.monotonic()
                stream.flush()
                os.fsync(stream.fileno())
        except Exception as exc:
            self.error = type(exc).__name__

    def close(self):
        try:
            self.queue.put(None, timeout=5)
        except queue.Full:
            self.error = "queue_full_at_close"
        self.writer.join(timeout=10)
        if self.writer.is_alive():
            self.error = "writer_did_not_finish"

    def add(self, kind, **data):
        event = dict(kind=kind, utc=datetime.now(timezone.utc).isoformat(),
                     monotonic=time.monotonic(), **data)
        with self.lock:
            self.events.append(event)
            try:
                self.queue.put_nowait(event)
            except queue.Full:
                self.error = "queue_full"


def run_bench(config, directory, count, scenario, sim_port, outages):
    """Only subclasses add observations; production parsing/scheduling/sending stay real."""
    if config["mode"] != "demo" or config["device_id"] != "delta-rtu-sim-001":
        raise ValueError("bench requires the dedicated demo identity")
    if config["mqtt"]["host"] != "127.0.0.1" or config["modbus"]["transport"] != "rtu":
        raise ValueError("bench requires loopback MQTT and local RTU")
    if (sim_port == config["modbus"]["serial_port"] or count < 1
            or count * config["poll_interval"] > 86400):
        raise ValueError("invalid bench ports/count")
    validate_outages(outages, count * config["poll_interval"])
    if any(offset + duration >= (count - 1) * config["poll_interval"]
           for offset, duration in outages):
        raise ValueError("outage needs a scheduled sample after restart")
    directory.mkdir(parents=True, exist_ok=False)
    config["outbox_path"] = str(directory / "state" / "outbox.db")
    config["mqtt"]["client_id"] = "bench-" + directory.name[-40:]
    (directory / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    ledger = Ledger(directory)
    interval = config["poll_interval"]
    state = {"origin": None, "deadline": None, "slot": None, "timestamp": None}
    production_next_deadline = edge.next_sample_deadline
    timer = None
    control_stop = threading.Event()
    sim = None
    sim_log = (directory / "simulator.log").open("a", encoding="utf-8")

    def start_sim():
        nonlocal sim
        process = subprocess.Popen(
            [sys.executable, "-m", "delta_device", "simulator", "--transport", "rtu",
             "--serial-port", sim_port, "--baudrate", str(config["modbus"]["baudrate"]),
             "--unit-id", str(config["modbus"]["unit_id"]), "--scenario", scenario],
            cwd=Path(__file__).resolve().parents[1], stdout=sim_log, stderr=sim_log,
            env={**os.environ, "DELTA_SIM_NOISE": "0", "PYTHONDONTWRITEBYTECODE": "1"},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        sim = process  # Register ownership before fallible observation/return.
        state["sim_origin"] = time.monotonic()
        ledger.add("sim_started", pid=process.pid)
        return process

    def stop_sim():
        if sim and sim.poll() is None:
            sim.terminate()
            sim.wait(timeout=10)
            ledger.add("sim_stopped", pid=sim.pid)

    def stop_runtime():
        handler = signal.getsignal(signal.SIGINT)
        if callable(handler):
            handler(signal.SIGINT, None)  # Existing edge handler only sets its Event.

    def monotonic():
        nonlocal timer
        now = time.monotonic()
        if state["origin"] is None:
            state["origin"] = now
            state["deadline"] = now
            ledger.add("window_start", origin=now, count=count, interval=interval,
                       slot_basis="scheduled_deadline")
            # Measurement window ends at count*interval; allow the existing sender
            # five seconds to settle its last batch before stopping the process.
            timer = threading.Timer(count * interval + 5, stop_runtime)
            timer.daemon = True
            timer.start()
        return now

    def observe_next_deadline(previous, now, spacing):
        deadline = production_next_deadline(previous, now, spacing)
        state["deadline"] = deadline
        return deadline  # Scheduling itself is unchanged.

    class ObservedClock(ClockGuard):
        def timestamp(self, now=None):
            observed = time.monotonic()
            elapsed = observed - state["origin"]
            state["slot"], start_delay, closed = slot_observation(
                state["origin"], state["deadline"], observed, interval, count)
            if closed:
                ledger.add("sampling_window_closed")
                time.sleep(max(0, count * interval + 5 - elapsed))
                stop_runtime()
                raise BenchWindowComplete()
            ledger.add("attempt", slot=state["slot"], start_delay=start_delay,
                       scheduled_monotonic=state["deadline"])
            try:
                state["timestamp"] = super().timestamp(now)
                return state["timestamp"]
            except Exception as exc:
                ledger.add("clock_error", slot=state["slot"], error=type(exc).__name__)
                raise

    class ObservedPoller(Poller):
        def sample(self):
            started = time.monotonic()
            try:
                result = super().sample()
            except Exception as exc:
                ledger.add("read_error", slot=state["slot"], error=type(exc).__name__,
                           duration=time.monotonic() - started)
                raise
            ledger.add("read_ok", slot=state["slot"], sampled_ns=state["timestamp"],
                       started=started, duration=time.monotonic() - started, snapshot=result)
            errors = golden_errors(result, scenario, time.monotonic() - state["sim_origin"])
            if errors:
                ledger.add("golden_error", slot=state["slot"], fields=errors)
            return result

    class ObservedBox(Outbox):
        def enqueue(self, sampled_ns, payload, snapshot):
            try:
                super().enqueue(sampled_ns, payload, snapshot)
            except Exception as exc:
                ledger.add("storage_error", slot=state["slot"], error=type(exc).__name__)
                raise
            ledger.add("committed", slot=state["slot"], sampled_ns=sampled_ns,
                       snapshot=snapshot, pending=self.pending_count())

    class ObservedPublisher(Publisher):
        def publish(self, payload):
            result = super().publish(payload)
            if result:
                ledger.add("broker_ack", sampled_ns=int(payload.rsplit(" ", 1)[1]))
            return result

    def control():
        nonlocal sim
        try:
            for index, (offset, duration) in enumerate(outages):
                while state["origin"] is None:
                    if control_stop.wait(.05):
                        return
                if control_stop.wait(max(0, state["origin"] + offset - time.monotonic())):
                    return
                stop_sim()
                ledger.add("outage_started", index=index)
                if control_stop.wait(duration):
                    return
                sim = start_sim()
                ledger.add("outage_restarted", index=index)
        except Exception as exc:
            ledger.add("control_error", error=type(exc).__name__)

    import serial.tools.list_ports
    sources = [*Path(__file__).parent.glob("bench_*.py"),
               *(Path(__file__).resolve().parents[1] / "delta_device").glob("*.py")]
    source_dir = directory / "source"
    source_dir.mkdir()
    for source in sources:
        shutil.copyfile(source, source_dir / source.name)
    manifest = {"python": sys.version, "device_id": config["device_id"],
                "ports": [{"port": p.device, "serial_number": p.serial_number}
                          for p in serial.tools.list_ports.comports()
                          if p.device in (sim_port, config["modbus"]["serial_port"])],
                "cable_length": "not_measured", "observer": "async ledger; CPU/RAM not sampled",
                "scenario": scenario, "outages": outages, "count": count, "interval": interval,
                "sender_settle_seconds": 5,
                "packages": {p: importlib.metadata.version(p) for p in
                             ("pymodbus", "pyserial", "paho-mqtt")},
                "source_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    controller = threading.Thread(target=control, daemon=True)
    try:
        sim = start_sim()
        time.sleep(2)
        if sim.poll() is not None:
            raise RuntimeError("simulator startup failed")
        controller.start()
        with patch.multiple(edge, ClockGuard=ObservedClock, Poller=ObservedPoller,
                            Outbox=ObservedBox, Publisher=ObservedPublisher,
                            next_sample_deadline=observe_next_deadline,
                            time=SimpleNamespace(monotonic=monotonic)):
            try:
                edge.run(config)
            except BenchWindowComplete:
                pass
    finally:
        control_stop.set()
        if controller.is_alive():
            controller.join(timeout=12)
        if timer:
            timer.cancel()
        stop_sim()
        sim_log.close()
        ledger.add("window_end")
        ledger.close()
        result = summarize_slots(ledger.events, count, interval)
        result["ledger_error"] = ledger.error
        result["outages_restarted"] = sum(e["kind"] == "outage_restarted" for e in ledger.events)
        result["control_errors"] = [e for e in ledger.events if e["kind"] == "control_error"]
        result["golden_errors"] = [e for e in ledger.events if e["kind"] == "golden_error"]
        result["normal_sampling_pass"] = result["pass"]
        if outages:
            result["recovery"] = summarize_outages(ledger.events, len(outages), 15)
            # Failure slots during deliberate outages are expected, but unclassified
            # failures elsewhere must not disappear into an aggregate percentage.
            windows = []
            for e in ledger.events:
                if e["kind"] == "outage_started":
                    restart = next((r for r in ledger.events if r["kind"] == "outage_restarted"
                                    and r["index"] == e["index"]), None)
                    if restart:
                        windows.append((e["monotonic"] - config["modbus"]["timeout"],
                                        restart["monotonic"] + 15))
            failures = [e for e in ledger.events if e["kind"] in
                        ("read_error", "storage_error", "clock_error")]
            unexpected = [e for e in failures if e["kind"] != "read_error" or not any(
                          lo <= e["monotonic"] <= hi for lo, hi in windows)]
            unclassified_slots = [slot for slot in result["missing_slots"] if not any(
                lo <= state["origin"] + slot * interval <= hi for lo, hi in windows)]
            result["unexpected_errors"] = unexpected
            result["unclassified_slots"] = unclassified_slots
            result["pass"] = bool(result["recovery"]["pass"] and not unexpected
                                  and not unclassified_slots and result["valid"] == result["committed"]
                                  and not result["duplicate_attempt_slots"]
                                  and not result["duplicate_commit_slots"])
        box_path = Path(config["outbox_path"])
        if box_path.exists():
            box = Outbox(box_path, config["queue_limit"], config["device_id"])
            result["pending_end"] = box.pending_count()
            result["sqlite_bytes"] = box_path.stat().st_size
        result["pass"] = bool(result["pass"] and result.get("pending_end") == 0
                              and not ledger.error and not result["control_errors"]
                              and not result["golden_errors"]
                              and result["outages_restarted"] == len(outages))
        (directory / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        samples = [dict(sampled_ns=e["sampled_ns"], **{k: e["snapshot"][k] for k in FIELDS})
                   for e in ledger.events if e["kind"] == "committed"]
        (directory / "samples.json").write_text(json.dumps(samples, indent=2), encoding="utf-8")
        print(json.dumps(result), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--interval", type=int, choices=(1, 5, 10, 15, 30), required=True)
    parser.add_argument("--scenario", choices=("day", "night", "alarm"), default="day")
    parser.add_argument("--sim-port", default="COM3")
    parser.add_argument("--outage", action="append", default=[], help="offset:duration seconds")
    args = parser.parse_args()
    config = load_config(args.config)
    config["poll_interval"] = args.interval
    outages = [tuple(map(int, entry.split(":"))) for entry in args.outage]
    if any(len(x) != 2 or min(x) < 0 for x in outages):
        parser.error("invalid outage")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = run_bench(config, args.output.resolve(), args.count, args.scenario,
                       args.sim_port, outages)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
