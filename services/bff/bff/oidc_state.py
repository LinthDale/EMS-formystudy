"""Transient OIDC login state — server-side, short-TTL (ADR-024 Phase-1).

Between ``GET /api/auth/oidc/login`` (redirect to the IdP) and
``GET /api/auth/oidc/callback`` the BFF must remember, per in-flight login:

- the PKCE ``code_verifier`` (NEVER sent to the browser; only its S256
  ``code_challenge`` goes to the IdP) — closes the authorization-code
  interception threat;
- the ``state`` value (CSRF / request-binding for the redirect round-trip);
- the ``nonce`` (replay binding, validated inside the id-token).

This is held server-side in a small store keyed by ``state``, mirroring the
session store design (ADR-023): an in-memory Protocol implementation for P1,
swappable for Redis when scaling out. Entries are single-use (consumed on
callback) and expire after ``oidc_state_ttl_s`` — a login that never returns
leaves nothing long-lived behind.

Records are immutable (frozen dataclass) and the clock is injectable so expiry
is testable without sleeps (project_rules §11). The verifier/nonce are secrets:
they are never logged and never serialised to the browser.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass(frozen=True, slots=True)
class OidcLoginState:
    """One in-flight Authorization-Code + PKCE login."""

    state: str
    code_verifier: str
    nonce: str
    created_at: float


class OidcStateStore(Protocol):
    """Key-by-state transient store. ``consume`` is atomic single-use: it
    removes and returns the entry (or None), so a replayed callback with the
    same state finds nothing."""

    def put(self, entry: OidcLoginState) -> None: ...
    def consume(self, state: str) -> OidcLoginState | None: ...
    def sweep(self, is_expired: Callable[[OidcLoginState], bool]) -> int: ...


class InMemoryOidcStateStore:
    """P1 single-process store (same caveat as InMemorySessionStore)."""

    def __init__(self) -> None:
        self._entries: dict[str, OidcLoginState] = {}

    def put(self, entry: OidcLoginState) -> None:
        self._entries[entry.state] = entry

    def consume(self, state: str) -> OidcLoginState | None:
        return self._entries.pop(state, None)

    def sweep(self, is_expired: Callable[[OidcLoginState], bool]) -> int:
        doomed = [s for s, e in tuple(self._entries.items()) if is_expired(e)]
        for s in doomed:
            self._entries.pop(s, None)
        return len(doomed)


class OidcStateManager:
    """Lifecycle rules for transient login state; clock injectable for tests."""

    def __init__(
        self,
        store: OidcStateStore,
        ttl_s: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._store = store
        self._ttl_s = ttl_s
        self._clock = clock

    def issue(self, state: str, code_verifier: str, nonce: str) -> OidcLoginState:
        entry = OidcLoginState(
            state=state,
            code_verifier=code_verifier,
            nonce=nonce,
            created_at=self._clock(),
        )
        self._store.put(entry)
        return entry

    def consume(self, state: str) -> OidcLoginState | None:
        """Single-use: removes the entry. Returns None for unknown state (CSRF /
        replay) or an entry that has aged past the TTL."""
        entry = self._store.consume(state)
        if entry is None:
            return None
        if self._is_expired(entry, self._clock()):
            return None
        return entry

    def _is_expired(self, entry: OidcLoginState, now: float) -> bool:
        return now - entry.created_at > self._ttl_s

    def sweep_expired(self) -> int:
        now = self._clock()
        return self._store.sweep(lambda e: self._is_expired(e, now))
