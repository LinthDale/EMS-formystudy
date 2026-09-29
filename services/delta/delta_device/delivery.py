"""Durable bounded spool. Acknowledgments mean broker receipt, not DB commit."""
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import sqlite3
import time
from .config import ID

METRICS = ("voltage", "current", "power_kw", "energy_kwh")


def encode_line(device_id, snapshot, sampled_ns):
    if not ID.fullmatch(device_id):
        raise ValueError("invalid device_id")
    values = [float(snapshot[name]) for name in METRICS]
    if not all(math.isfinite(v) and v >= 0 for v in values):
        raise ValueError("non-finite or negative telemetry")
    fields = ",".join(name + "=" + repr(v) for name, v in zip(METRICS, values))
    payload = f"electricity_measurements,device_id={device_id} {fields} {sampled_ns}"
    if len(payload.encode()) > 1024:
        raise ValueError("payload exceeds limit")
    return payload


class ClockGuard:
    def __init__(self, mode, sync_file=None, previous=0):
        self.mode, self.sync_file, self.previous = mode, sync_file, previous

    def timestamp(self, now=None):
        # Pi without RTC must synchronize before field acquisition.
        if self.mode == "field" and not Path(self.sync_file).exists():
            raise ValueError("clock unsynchronized")
        value = (time.time_ns() if now is None else now) // 1000 * 1000
        if value < 1735689600000000000 or value <= self.previous:
            raise ValueError("clock invalid or moved backwards")
        self.previous = value
        return value


class Outbox:
    def __init__(self, path, limit, device_id=None):
        self.path, self.limit = Path(path), limit
        # Use a dedicated state directory; never point this at a shared directory.
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise ValueError("outbox must not use symlinks")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path.parent.chmod(0o700)
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
        os.close(fd)
        self.path.chmod(0o600)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY, "
                       "sampled_ns INTEGER NOT NULL, payload TEXT NOT NULL, snapshot TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            if device_id is not None:
                old = db.execute("SELECT value FROM metadata WHERE key='device_id'").fetchone()
                if old and old[0] != device_id:
                    raise ValueError("outbox belongs to another device")
                db.execute("INSERT OR IGNORE INTO metadata VALUES ('device_id', ?)", (device_id,))

    @contextmanager
    def connect(self):
        # A connection per operation allows independent acquisition/sender threads.
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def enqueue(self, sampled_ns, payload, snapshot):
        encoded = json.dumps(snapshot, allow_nan=False, separators=(",", ":"))
        if len(encoded.encode()) > 16384 or len(payload.encode()) > 1024:
            raise ValueError("sample exceeds spool limits")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] >= self.limit:
                raise OverflowError("outbox full; sample rejected")
            db.execute("INSERT INTO outbox(sampled_ns,payload,snapshot) VALUES (?,?,?)",
                       (sampled_ns, payload, encoded))
            db.execute("INSERT OR REPLACE INTO metadata VALUES ('latest_timestamp', ?)",
                       (str(sampled_ns),))

    def latest_timestamp(self):
        with self.connect() as db:
            row = db.execute("SELECT value FROM metadata WHERE key='latest_timestamp'").fetchone()
            return int(row[0]) if row else 0

    def pending(self, limit):
        with self.connect() as db:
            return db.execute("SELECT id,sampled_ns,payload FROM outbox ORDER BY id LIMIT ?",
                              (limit,)).fetchall()

    def pending_count(self):
        with self.connect() as db:
            return db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]

    def ack(self, row_id):
        with self.connect() as db:
            db.execute("DELETE FROM outbox WHERE id=?", (row_id,))


def drain(box, publish, batch_size, stop):
    sent = 0
    for row_id, _, payload in box.pending(batch_size):
        if stop.is_set() or not publish(payload):
            break
        box.ack(row_id)
        sent += 1
    return sent
