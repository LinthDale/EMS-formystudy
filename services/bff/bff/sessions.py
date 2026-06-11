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

import dataclasses
import secrets
import time
from dataclasses import dataclass
from typing import Callable, Protocol

from .config import Settings
from .roles import Role

_TOKEN_BYTES = 32  # 256-bit opaque session id


@dataclass(frozen=True, slots=True)
class Session:
    id: str
    username: str
    role: Role
    created_at: float
    last_seen_at: float


class SessionStore(Protocol):
    """Async key-value session store. Implementations: InMemorySessionStore (P1),
    RedisSessionStore (future — same surface, external TTL optional)."""

    async def get(self, session_id: str) -> Session | None: ...
    async def put(self, session: Session) -> None: ...
    async def delete(self, session_id: str) -> None: ...


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
        if now - session.created_at > self._settings.session_max_lifetime_s:
            await self._store.delete(session_id)
            return None
        if now - session.last_seen_at > self._settings.session_idle_timeout_s:
            await self._store.delete(session_id)
            return None
        touched = dataclasses.replace(session, last_seen_at=now)
        await self._store.put(touched)
        return touched

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
