"""Durable intent and append-only events; single active process, fail closed."""
from __future__ import annotations

import fcntl
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .contracts import Command, canonical


class Conflict(Exception):
    pass


class Unavailable(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Audit:
    def __init__(self, path: str, max_commands: int = 100000):
        self._lock_file = None
        self.db = None
        self.max_commands = max_commands
        try:
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                self._lock_file = open(path + ".lock", "a")
                fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.db = sqlite3.connect(path, timeout=1, check_same_thread=False)
            self.db.row_factory = sqlite3.Row
            # Low-volume command audit: rollback journal avoids concurrent WAL/checkpoint issues.
            self.db.execute("PRAGMA journal_mode=DELETE")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS operations(
                    sequence INTEGER PRIMARY KEY,
                    request_id TEXT NOT NULL UNIQUE,
                    simulator_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    command_json TEXT NOT NULL,
                    created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(
                    event_id INTEGER PRIMARY KEY,
                    request_id TEXT NOT NULL REFERENCES operations(request_id),
                    status TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS events_request ON events(request_id,event_id);
                CREATE INDEX IF NOT EXISTS operations_sim ON operations(simulator_id,sequence);
            """)
            for table in ("operations", "events"):
                for action in ("UPDATE", "DELETE"):
                    self.db.execute(f"""
                        CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()}
                        BEFORE {action} ON {table}
                        BEGIN SELECT RAISE(ABORT, 'append-only audit'); END
                    """)
            self.db.commit()
            pending = self.db.execute("""
                SELECT request_id FROM operations o WHERE NOT EXISTS
                (SELECT 1 FROM events e WHERE e.request_id=o.request_id)
            """).fetchall()
            for row in pending:
                self.append(row["request_id"], "outcome_unknown",
                            {"error": "controller_restarted", "resolved": False})
        except (OSError, sqlite3.Error):
            self.close()
            raise Unavailable("audit unavailable or already in use") from None

    def close(self) -> None:
        if self.db is not None:
            self.db.close()
            self.db = None
        if self._lock_file is not None:
            self._lock_file.close()
            self._lock_file = None

    def reserve(self, actor: str, simulator_id: str, body: Command) -> dict:
        request_id = str(body.request_id)
        old = self.get(request_id)
        encoded = canonical(body.model_dump(mode="json"))
        if old:
            row = self.db.execute("SELECT * FROM operations WHERE request_id=?",
                                  (request_id,)).fetchone()
            if (row["actor"], row["simulator_id"], row["command_json"]) != (
                    actor, simulator_id, encoded):
                raise Conflict("request_id already belongs to a different command or actor")
            return old
        count = self.db.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
        if count >= self.max_commands:
            raise Unavailable("audit command capacity reached")
        with self.db:
            self.db.execute("""
                INSERT INTO operations(request_id,simulator_id,actor,command_json,created_at)
                VALUES(?,?,?,?,?)
            """, (request_id, simulator_id, actor, encoded, utc_now()))
        return self.get(request_id)

    def append(self, request_id: str, status: str, data: dict) -> dict:
        with self.db:
            self.db.execute("""
                INSERT INTO events(request_id,status,data_json,created_at) VALUES(?,?,?,?)
            """, (request_id, status, canonical(data), utc_now()))
        return self.get(request_id)

    def get(self, request_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM operations WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            return None
        command = json.loads(row["command_json"])
        result = dict(sequence=row["sequence"], request_id=request_id,
                      simulator_id=row["simulator_id"], actor=row["actor"],
                      created_at=row["created_at"], status="pending", resolved=False,
                      before=None, after=None, error=None, **{k: v for k, v in command.items()
                                                           if k != "request_id"})
        events = []
        for event in self.db.execute(
                "SELECT * FROM events WHERE request_id=? ORDER BY event_id", (request_id,)):
            data = json.loads(event["data_json"])
            result.update(data, status=event["status"], updated_at=event["created_at"])
            events.append(dict(event_id=event["event_id"], status=event["status"],
                               created_at=event["created_at"], **data))
        result["events"] = events
        return result

    def list(self, limit: int = 50, before: int | None = None,
             simulator_id: str | None = None) -> list[dict]:
        rows = self.db.execute("""
            SELECT request_id FROM operations
            WHERE (? IS NULL OR sequence < ?) AND (? IS NULL OR simulator_id = ?)
            ORDER BY sequence DESC LIMIT ?
        """, (before, before, simulator_id, simulator_id, limit))
        return [self.get(row["request_id"]) for row in rows]

    def blocked(self, simulator_id: str) -> bool:
        # Every target is serialized; only its latest operation can still be pending/unknown.
        latest = self.list(limit=1, simulator_id=simulator_id)
        return bool(latest and latest[0]["status"] in ("pending", "outcome_unknown")
                    and not latest[0]["resolved"])
