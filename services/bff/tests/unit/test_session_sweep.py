"""In-memory session sweep — code-review MED: validate() evicts expired sessions
only when they are re-accessed, so never-re-touched sessions accumulate in the
single-process store. SessionManager.sweep_expired() proactively drops them; a
background task (started in main.py lifespan) runs it on BFF_SESSION_SWEEP_INTERVAL_S.

Pure-logic tests (no docker, injected FakeClock, project_rules §11). The async
SessionManager surface is driven via asyncio.run() to avoid a new pytest-asyncio
test dependency."""
from __future__ import annotations

import asyncio

import pytest

from bff.roles import Role
from bff.sessions import InMemorySessionStore, SessionManager
from tests.conftest import IDLE_TIMEOUT_S, MAX_LIFETIME_S, FakeClock, make_settings


def _manager(clock: FakeClock) -> tuple[SessionManager, InMemorySessionStore]:
    store = InMemorySessionStore()
    mgr = SessionManager(store, make_settings(), clock)
    return mgr, store


def test_sweep_removes_idle_expired_session_without_prior_access():
    """A session left untouched past its idle timeout is removed by the sweep,
    even though validate() was never called again to evict it lazily."""
    clock = FakeClock()
    mgr, store = _manager(clock)

    async def scenario():
        s = await mgr.create("ops_user", Role.OPS)
        clock.advance(IDLE_TIMEOUT_S + 1)
        removed = await mgr.sweep_expired()
        return s, removed

    s, removed = asyncio.run(scenario())
    assert removed == 1, f"sweep should report 1 removed session, got {removed}"
    assert asyncio.run(store.get(s.id)) is None, "idle-expired session must be gone after sweep"


def test_sweep_removes_session_past_absolute_max_lifetime():
    clock = FakeClock()
    mgr, store = _manager(clock)

    async def scenario():
        s = await mgr.create("ops_user", Role.OPS)
        # keep it warm under the idle window, but cross the absolute max lifetime
        clock.advance(MAX_LIFETIME_S + 1)
        removed = await mgr.sweep_expired()
        return s, removed

    s, removed = asyncio.run(scenario())
    assert removed == 1, f"sweep should remove the over-max-lifetime session, got {removed}"
    assert asyncio.run(store.get(s.id)) is None, "over-max-lifetime session must be swept"


def test_sweep_keeps_live_sessions():
    """Sessions still inside both windows survive the sweep untouched."""
    clock = FakeClock()
    mgr, store = _manager(clock)

    async def scenario():
        live = await mgr.create("ops_user", Role.OPS)
        clock.advance(IDLE_TIMEOUT_S // 2)  # still well within the idle window
        removed = await mgr.sweep_expired()
        kept = await store.get(live.id)
        return live, removed, kept

    live, removed, kept = asyncio.run(scenario())
    assert removed == 0, f"no live session should be swept, got {removed}"
    assert kept is not None, "live session must survive the sweep"
    assert kept.id == live.id


def test_sweep_removes_only_expired_leaving_live():
    """Mixed bag: expired sessions go, live ones stay, in a single sweep."""
    clock = FakeClock()
    mgr, store = _manager(clock)

    async def scenario():
        expired = await mgr.create("old_user", Role.OPS)
        clock.advance(IDLE_TIMEOUT_S + 1)
        fresh = await mgr.create("new_user", Role.INGEST)  # created after jump -> live
        removed = await mgr.sweep_expired()
        return expired, fresh, removed

    expired, fresh, removed = asyncio.run(scenario())
    assert removed == 1, f"exactly the one expired session should be removed, got {removed}"
    assert asyncio.run(store.get(expired.id)) is None, "expired session must be swept"
    assert asyncio.run(store.get(fresh.id)) is not None, "freshly created session must remain"


def test_sweep_does_not_refresh_last_seen_of_live_sessions():
    """The sweep is a janitor, not an access — it must not extend live sessions
    (otherwise an idle session could be kept alive forever by the sweeper)."""
    clock = FakeClock()
    mgr, store = _manager(clock)

    async def scenario():
        live = await mgr.create("ops_user", Role.OPS)
        before = await store.get(live.id)
        clock.advance(IDLE_TIMEOUT_S // 2)
        await mgr.sweep_expired()
        after = await store.get(live.id)
        return before, after

    before, after = asyncio.run(scenario())
    assert after is not None
    assert after.last_seen_at == before.last_seen_at, (
        "sweep must not touch last_seen_at of a live session"
    )


def test_sweep_interval_is_configurable_via_settings():
    """BFF_SESSION_SWEEP_INTERVAL_S tunable (default 300) drives the background task."""
    assert make_settings().session_sweep_interval_s == 300, "default sweep interval must be 300s"
    custom = make_settings(session_sweep_interval_s=42)
    assert custom.session_sweep_interval_s == 42, "sweep interval must be overridable"


def test_non_positive_sweep_interval_rejected():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        make_settings(session_sweep_interval_s=0)
