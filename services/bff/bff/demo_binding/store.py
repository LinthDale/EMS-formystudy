"""Durable booth state: one current binding + today's keyed visitor numbers (PRD-0024 §7).

Single process (flock, ADR-033 pattern), fail closed. Raw chat ids live only in `binding`
(deleted at expiry/replacement/stop); visitors are HMAC'd with a random per-day key that is
replaced at Taipei midnight, so earlier days become unlinkable. secure_delete zeroes freed pages.
"""
from __future__ import annotations

import fcntl
import hashlib
import hmac
import os
import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS visitors(
    hash TEXT PRIMARY KEY,
    number INTEGER NOT NULL UNIQUE CHECK(number > 0));
CREATE TABLE IF NOT EXISTS binding(
    id INTEGER PRIMARY KEY CHECK(id = 1),
    chat_id INTEGER NOT NULL,
    display TEXT NOT NULL,
    bound_at REAL NOT NULL,
    expires_at REAL NOT NULL);
"""


class StoreUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Binding:
    chat_id: int
    display: str
    bound_at: float
    expires_at: float


class BindingStore:
    def __init__(self, path: str, new_key: Callable[[], str] = lambda: secrets.token_hex(32)):
        self._new_key = new_key
        self._lock_fd: int | None = None
        self.db: sqlite3.Connection | None = None
        try:
            if path != ":memory:":
                self._prepare_files(Path(path))
            self.db = sqlite3.connect(path, timeout=1, check_same_thread=False)
            self.db.execute("PRAGMA journal_mode=DELETE")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA secure_delete=ON")
            self.db.executescript(_SCHEMA)
            self.db.commit()
            if path != ":memory:":
                os.chmod(path, 0o600)
        except (OSError, sqlite3.Error):
            self.close()
            raise StoreUnavailable("demo binding store unavailable or already in use") from None

    def _prepare_files(self, path: Path) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
        self._lock_fd = os.open(str(path) + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def close(self) -> None:
        if self.db is not None:
            self.db.close()
            self.db = None
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

    # --- meta -------------------------------------------------------------------------
    def _meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def _put_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT INTO meta(key,value) VALUES(?,?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def ensure_day(self, day: str) -> None:
        """Start a new Taipei day: forget every visitor hash and replace the hash key."""
        if self._meta("day") == day and self._meta("day_key"):
            return
        with self.db:
            self.db.execute("DELETE FROM visitors")
            self._put_meta("day_key", self._new_key())
            self._put_meta("day", day)

    def get_offset(self) -> int | None:
        value = self._meta("tg_offset")
        return int(value) if value is not None else None

    def set_offset(self, update_id: int) -> None:
        with self.db:
            self._put_meta("tg_offset", str(int(update_id)))

    # --- visitors (today only) --------------------------------------------------------
    def visitor_hash(self, user_id: int) -> str:
        key = bytes.fromhex(self._meta("day_key"))
        return hmac.new(key, str(int(user_id)).encode(), hashlib.sha256).hexdigest()[:32]

    def visitor_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM visitors").fetchone()[0]

    def number_for(self, visitor_hash: str) -> int | None:
        row = self.db.execute("SELECT number FROM visitors WHERE hash=?", (visitor_hash,)).fetchone()
        return row[0] if row else None

    def commit_number(self, day: str, visitor_hash: str, number: int) -> int | None:
        """Persist a delivered number; a stale day (rolled over meanwhile) is ignored."""
        if self._meta("day") != day:
            return None
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO visitors(hash,number) VALUES(?,?)",
                            (visitor_hash, number))
        return self.number_for(visitor_hash)

    # --- the single current binding ---------------------------------------------------
    def get_binding(self, now: float) -> Binding | None:
        row = self.db.execute(
            "SELECT chat_id, display, bound_at, expires_at FROM binding WHERE id=1").fetchone()
        if row is None:
            return None
        if row[3] <= now:
            with self.db:
                self.db.execute("DELETE FROM binding WHERE id=1")
            return None
        return Binding(*row)

    def set_binding(self, chat_id: int, display: str, now: float, ttl_s: int) -> Binding:
        binding = Binding(int(chat_id), display, now, now + ttl_s)
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO binding(id,chat_id,display,bound_at,expires_at) "
                            "VALUES(1,?,?,?,?)", (binding.chat_id, binding.display,
                                                  binding.bound_at, binding.expires_at))
        return binding

    def clear_binding(self, chat_id: int) -> bool:
        with self.db:
            cursor = self.db.execute("DELETE FROM binding WHERE id=1 AND chat_id=?", (int(chat_id),))
        return cursor.rowcount > 0
