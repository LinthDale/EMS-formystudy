"""PRD-0024 FR-2407/FR-2409/FR-2411: binding + day-visitor store (in-memory SQLite; file
persistence and locking are covered in tests/integration/test_demo_alarm_binding.py)."""
from __future__ import annotations

import hashlib

from bff.demo_binding.store import BindingStore

DAY = "2026-10-13"
NEXT_DAY = "2026-10-14"


def fresh_store() -> BindingStore:
    store = BindingStore(":memory:")
    store.ensure_day(DAY)
    return store


def test_new_store_has_no_binding_offset_or_visitors():
    store = fresh_store()
    assert store.get_binding(1000.0) is None
    assert store.get_offset() is None
    assert store.visitor_count() == 0


def test_second_binding_replaces_the_single_current_binding():
    store = fresh_store()
    store.set_binding(111, "@aa***", now=1000.0, ttl_s=600)
    store.set_binding(222, "@bb***", now=1001.0, ttl_s=600)
    binding = store.get_binding(1002.0)
    assert (binding.chat_id, binding.display, binding.expires_at) == (222, "@bb***", 1601.0), binding


def test_binding_reaching_expiry_is_removed():
    store = fresh_store()
    store.set_binding(111, "@aa***", now=1000.0, ttl_s=600)
    assert store.get_binding(1599.9) is not None, "binding must be valid before expiry"
    assert store.get_binding(1600.0) is None, "binding must expire at bound_at + ttl"
    assert store.get_binding(1000.0) is None, "expired row must be deleted, not just hidden"


def test_clear_binding_only_matches_the_bound_chat():
    store = fresh_store()
    store.set_binding(111, "@aa***", now=1000.0, ttl_s=600)
    assert store.clear_binding(222) is False, "another chat must not clear the binding"
    assert store.get_binding(1001.0) is not None
    assert store.clear_binding(111) is True
    assert store.get_binding(1001.0) is None


def test_committed_numbers_are_sequential_and_stable_per_visitor():
    store = fresh_store()
    first = store.visitor_hash(111)
    assert store.number_for(first) is None
    assert store.commit_number(DAY, first, 1) == 1
    assert store.commit_number(DAY, first, 5) == 1, "a known visitor keeps the original number"
    second = store.visitor_hash(222)
    assert store.commit_number(DAY, second, 2) == 2
    assert store.visitor_count() == 2
    assert store.number_for(first) == 1


def test_day_rollover_clears_visitors_and_rotates_hash_key():
    store = fresh_store()
    old = store.visitor_hash(111)
    store.commit_number(DAY, old, 1)
    store.ensure_day(NEXT_DAY)
    assert store.visitor_count() == 0, "a new Taipei day must start from zero"
    assert store.visitor_hash(111) != old, "the daily key must change so old hashes are unlinkable"


def test_commit_for_previous_day_after_rollover_is_ignored():
    store = fresh_store()
    stale = store.visitor_hash(111)
    store.ensure_day(NEXT_DAY)
    assert store.commit_number(DAY, stale, 1) is None
    assert store.visitor_count() == 0


def test_visitor_hash_is_keyed_not_a_plain_digest_of_the_id():
    store = fresh_store()
    digest = store.visitor_hash(111)
    assert len(digest) == 32 and digest != hashlib.sha256(b"111").hexdigest()[:32], digest


def test_offset_round_trips_and_overwrites():
    store = fresh_store()
    store.set_offset(41)
    store.set_offset(42)
    assert store.get_offset() == 42
