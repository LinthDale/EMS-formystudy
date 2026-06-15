"""Server-side sessions (PRD-0005 §9.2 [必過]).

- Session records are immutable (frozen dataclass); every touch produces a new
  record (coding-style: no in-place mutation).
- The store is a small async Protocol so the in-memory P1 implementation can be
  swapped for Redis (GATE-1: "P1 單機 in-process，水平擴展再 Redis") without
  touching SessionManager or any route.
- Expiry: absolute max lifetime AND idle timeout, both enforced on EVERY lookup.
- Role downgrade (and any role change) revokes the session — re-authentication
  is the only way to obtain a differently-scoped session (§9.1 [必過]).
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Callable, Protocol

from .config import Settings
from .roles import Role

_TOKEN_BYTES = 32  # 256-bit opaque session id

_log = logging.getLogger("bff.sessions")


@dataclass(frozen=True, slots=True)
class Session:
    id: str
    username: str
    role: Role
    created_at: float
    last_seen_at: float


class SessionStore(Protocol):
    """Async key-value session store. Implementations: InMemorySessionStore (P1),
    RedisSessionStore (future — same surface, external TTL optional).

    sweep(is_expired) proactively drops records the predicate rejects. A Redis
    store can no-op it (Redis evicts via native TTL); the in-memory store needs
    it because nothing else reaps never-re-accessed sessions."""

    async def get(self, session_id: str) -> Session | None: ...
    async def put(self, session: Session) -> None: ...
    async def delete(self, session_id: str) -> None: ...
    async def sweep(self, is_expired: Callable[[Session], bool]) -> int: ...


class InMemorySessionStore:
    """P1 single-process store. Not shared across workers — run one uvicorn
    worker, or swap for Redis when scaling out."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    async def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    async def put(self, session: Session) -> None:
        self._sessions[session.id] = session

    async def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    async def sweep(self, is_expired: Callable[[Session], bool]) -> int:
        """Drop every session the predicate marks expired; return how many.
        Snapshot the items first so we never mutate the dict mid-iteration."""
        doomed = [sid for sid, s in tuple(self._sessions.items()) if is_expired(s)]
        for sid in doomed:
            self._sessions.pop(sid, None)
        return len(doomed)


class SessionManager:
    """All session lifecycle rules in one place; clock injectable for tests."""

    def __init__(
        self,
        store: SessionStore,
        settings: Settings,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._store = store
        self._settings = settings
        self._clock = clock

    async def create(self, username: str, role: Role) -> Session:
        now = self._clock()
        session = Session(
            id=secrets.token_urlsafe(_TOKEN_BYTES),
            username=username,
            role=role,
            created_at=now,
            last_seen_at=now,
        )
        await self._store.put(session)
        return session

    def _is_expired(self, session: Session, now: float) -> bool:
        """Single source of truth for expiry — used by both per-request validate()
        and the background sweep, so the two can never drift apart."""
        return (
            now - session.created_at > self._settings.session_max_lifetime_s
            or now - session.last_seen_at > self._settings.session_idle_timeout_s
        )

    async def validate(self, session_id: str | None) -> Session | None:
        """Validate on EVERY request, before any key is chosen (§9.2).
        Expired sessions are deleted eagerly; valid ones are touched
        (new immutable record with refreshed last_seen_at)."""
        if not session_id:
            return None
        session = await self._store.get(session_id)
        if session is None:
            return None
        now = self._clock()
        if self._is_expired(session, now):
            await self._store.delete(session_id)
            return None
        touched = dataclasses.replace(session, last_seen_at=now)
        await self._store.put(touched)
        return touched

    async def sweep_expired(self) -> int:
        """Proactively reap sessions that expired but were never re-accessed
        (code-review MED). Uses the SAME expiry rule as validate(); does NOT
        touch live sessions' last_seen_at. Returns the number removed."""
        now = self._clock()
        return await self._store.sweep(lambda s: self._is_expired(s, now))

    async def revoke(self, session_id: str) -> None:
        await self._store.delete(session_id)

    async def change_role(self, session: Session, new_role: Role) -> bool:
        """Returns True if the session was terminated.

        §9.1 [必過]: a downgrade invalidates the session. We are deliberately
        stricter: ANY role change revokes — privilege moves only through a
        fresh login, never by re-scoping a live session.
        """
        if new_role is session.role:
            return False
        await self._store.delete(session.id)
        return True


async def run_sweep_loop(manager: SessionManager, interval_s: float) -> None:
    """Background janitor for the in-memory store: sweep expired sessions every
    interval_s. Started from main.py's lifespan and cancelled on shutdown.

    Cancellation-clean: the CancelledError raised inside asyncio.sleep is
    re-raised so the awaiting lifespan sees the task finish promptly. A sweep
    error is logged (never the session contents) and the loop keeps running so a
    transient failure does not silently kill the janitor."""
    while True:
        try:
            await asyncio.sleep(interval_s)
        except asyncio.CancelledError:
            raise
        try:
            removed = await manager.sweep_expired()
            if removed:
                _log.info("session sweep removed %d expired session(s)", removed)
        except Exception:  # noqa: BLE001 — keep the janitor alive across hiccups
            _log.exception("session sweep iteration failed; continuing")
