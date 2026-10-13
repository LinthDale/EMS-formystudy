"""PRD-0024 FR-2401/FR-2408: rotating deep-link codes, display masking, Taipei calendar day."""
from __future__ import annotations

import re
from datetime import datetime

import pytest
from pydantic import ValidationError

from bff.demo_binding.codes import TAIPEI, BindCodes, mask_display, taipei_day
from tests.conftest import FakeClock, make_settings


def test_fresh_codes_current_returns_url_safe_code_that_validates():
    codes = BindCodes(rotate_s=60, ttl_s=300, clock=FakeClock())
    code = codes.current()
    assert re.fullmatch(r"b[A-Za-z0-9_-]{22}", code), f"got {code!r}"
    assert codes.is_valid(code), "a freshly issued code must validate"


def test_same_rotation_window_current_reuses_code():
    clock = FakeClock()
    codes = BindCodes(rotate_s=60, ttl_s=300, clock=clock)
    first = codes.current()
    clock.advance(59)
    assert codes.current() == first, "code must not rotate inside the 60 s window"


def test_rotation_issues_new_code_and_previous_stays_valid_until_its_ttl():
    clock = FakeClock()
    codes = BindCodes(rotate_s=60, ttl_s=300, clock=clock)
    first = codes.current()
    clock.advance(60)
    second = codes.current()
    assert second != first, "a new code must be issued after the rotation period"
    assert codes.is_valid(first) and codes.is_valid(second), "both codes must validate inside TTL"
    clock.advance(240)  # first issued 300 s ago -> expired; second issued 240 s ago
    assert not codes.is_valid(first), "a code older than its TTL must be rejected"
    assert codes.is_valid(second), "the newer code must still validate"


def test_unknown_or_malformed_code_validation_rejects():
    codes = BindCodes(rotate_s=60, ttl_s=300, clock=FakeClock())
    codes.current()
    for bad in ("", "b" + "x" * 22, "../../etc", "b" * 200, None, 12345):
        assert not codes.is_valid(bad), f"accepted {bad!r}"


def test_username_present_mask_keeps_two_chars():
    shown = mask_display({"username": "dalelin", "first_name": "Dale"})
    assert shown == "@da***", f"got {shown!r}"


def test_no_username_mask_uses_first_visible_char_of_first_name():
    assert mask_display({"first_name": "林大明"}) == "林***"
    shown = mask_display({"first_name": "​‮ Dale"})
    assert shown == "D***", f"invisible/format characters must be skipped, got {shown!r}"


def test_no_usable_name_mask_falls_back_to_generic_label():
    assert mask_display({}) == "Telegram 訪客"
    shown = mask_display({"username": "bad name!", "first_name": "​"})
    assert shown == "Telegram 訪客", f"got {shown!r}"


def test_code_ttl_shorter_than_rotation_fails_fast():
    with pytest.raises(ValidationError):
        make_settings(demo_bind_code_rotate_s=120, demo_bind_code_ttl_s=60)


def test_taipei_day_changes_exactly_at_local_midnight():
    last_second = datetime(2026, 10, 13, 23, 59, 59, tzinfo=TAIPEI).timestamp()
    assert taipei_day(last_second) == "2026-10-13"
    assert taipei_day(last_second + 1) == "2026-10-14"
