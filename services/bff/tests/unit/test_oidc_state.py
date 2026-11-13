"""Transient OIDC login-state store (ADR-024): single-use + short TTL.

The verifier/state/nonce must survive only the redirect round-trip. These tests
pin the lifecycle rules with an injectable clock (no sleeps, project_rules §11)."""
from __future__ import annotations

from bff.oidc_state import InMemoryOidcStateStore, OidcStateManager
from tests.conftest import FakeClock


def _manager(ttl_s: float = 300.0) -> tuple[OidcStateManager, FakeClock]:
    clock = FakeClock()
    return OidcStateManager(InMemoryOidcStateStore(), ttl_s, clock), clock


def test_issue_then_consume_returns_the_entry():
    mgr, _clock = _manager()
    mgr.issue("state-1", "verifier-1", "nonce-1")
    entry = mgr.consume("state-1")
    assert entry is not None
    assert entry.code_verifier == "verifier-1"
    assert entry.nonce == "nonce-1"


def test_consume_is_single_use():
    mgr, _clock = _manager()
    mgr.issue("state-1", "verifier-1", "nonce-1")
    assert mgr.consume("state-1") is not None
    assert mgr.consume("state-1") is None, "a state may be consumed only once (anti-replay)"


def test_unknown_state_consumes_to_none():
    mgr, _clock = _manager()
    assert mgr.consume("never-issued") is None


def test_entry_past_ttl_is_not_returned():
    mgr, clock = _manager(ttl_s=300.0)
    mgr.issue("state-1", "verifier-1", "nonce-1")
    clock.advance(301.0)  # just past the TTL
    assert mgr.consume("state-1") is None, "an expired login state must not be usable"


def test_entry_within_ttl_is_returned():
    mgr, clock = _manager(ttl_s=300.0)
    mgr.issue("state-1", "verifier-1", "nonce-1")
    clock.advance(299.0)
    assert mgr.consume("state-1") is not None


def test_sweep_drops_only_expired_entries():
    mgr, clock = _manager(ttl_s=300.0)
    mgr.issue("old", "v1", "n1")
    clock.advance(301.0)
    mgr.issue("new", "v2", "n2")  # issued at the advanced time
    removed = mgr.sweep_expired()
    assert removed == 1, f"only the aged entry should be swept, removed={removed}"
    assert mgr.consume("new") is not None, "the fresh entry must survive the sweep"
