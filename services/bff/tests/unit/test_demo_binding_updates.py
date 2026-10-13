"""PRD-0024 FR-2401..FR-2404/FR-2407/FR-2411: bot command handling on the binding service."""
from __future__ import annotations

from bff.demo_binding.service import DemoBinding
from tests.conftest import FakeClock, make_settings
from tests.demo_binding_fakes import (BOT, FIXED_CHAT, NOON, OTHER_VISITOR, TOKEN, VISITOR,
                                      code_from, start_text, telegram_message)


def ready_binding(**overrides):
    clock = FakeClock(start=NOON)
    settings = make_settings(telegram_bot_token=TOKEN, telegram_chat_id=FIXED_CHAT,
                             demo_bind_enabled=True, demo_bind_db=":memory:", **overrides)
    binding = DemoBinding(settings, clock)
    binding.open()
    binding.set_bot_username(BOT)
    binding.set_state("ready")
    return binding, clock


def scan(binding, clock, user_id=VISITOR, **kwargs):
    code = code_from(binding.status())
    return binding.handle_update(telegram_message(clock, user_id, start_text(code), **kwargs))


def test_valid_start_code_binds_sender_and_replies_confirmation():
    binding, clock = ready_binding()
    reply = scan(binding, clock)
    assert reply is not None and reply.chat_id == VISITOR, reply
    assert "綁定完成" in reply.text and "10 分鐘" in reply.text and "/stop" in reply.text, reply.text
    current = binding.status()["current"]
    assert current == {"display": "@da***", "expires_in_seconds": 600}, current


def test_second_visitor_start_replaces_first_binding():
    binding, clock = ready_binding()
    scan(binding, clock)
    clock.advance(5)
    scan(binding, clock, OTHER_VISITOR, username="bob_visitor")
    current = binding.status()["current"]
    assert current["display"] == "@bo***", f"latest scan must win, got {current!r}"


def test_expired_code_start_is_rejected_with_rescan_reply():
    binding, clock = ready_binding()
    code = code_from(binding.status())
    clock.advance(301)
    reply = binding.handle_update(telegram_message(clock, VISITOR, start_text(code)))
    assert reply is not None and "重新掃描" in reply.text, reply
    assert binding.status()["current"] is None, "an expired code must not bind"


def test_bare_or_unknown_start_code_does_not_bind():
    binding, clock = ready_binding()
    for index, text in enumerate(("/start", "/start b" + "x" * 22)):
        clock.advance(5)
        reply = binding.handle_update(telegram_message(clock, VISITOR, text, update_id=index))
        assert reply is not None and "重新掃描" in reply.text, (text, reply)
    assert binding.status()["current"] is None


def test_stop_from_bound_visitor_unbinds_and_confirms():
    binding, clock = ready_binding()
    scan(binding, clock)
    clock.advance(5)
    reply = binding.handle_update(telegram_message(clock, VISITOR, "/stop", update_id=2))
    assert reply is not None and "已取消綁定" in reply.text, reply
    assert binding.status()["current"] is None


def test_stop_from_other_user_keeps_current_binding():
    binding, clock = ready_binding()
    scan(binding, clock)
    clock.advance(5)
    reply = binding.handle_update(telegram_message(clock, OTHER_VISITOR, "/stop", update_id=2))
    assert reply is not None and "沒有綁定" in reply.text, reply
    assert binding.status()["current"]["display"] == "@da***"


def test_non_private_bot_or_malformed_messages_are_ignored():
    binding, clock = ready_binding()
    code = code_from(binding.status())
    text = start_text(code)
    ignored = [
        telegram_message(clock, VISITOR, text, chat_type="group"),
        telegram_message(clock, VISITOR, text, is_bot=True),
        telegram_message(clock, VISITOR, text + " " + "x" * 64),
        {"update_id": 9, "edited_message": telegram_message(clock, VISITOR, text)["message"]},
        {"update_id": 10, "message": {**telegram_message(clock, VISITOR, text)["message"],
                                      "chat": {"id": OTHER_VISITOR, "type": "private"}}},
        {"update_id": 11, "message": {**telegram_message(clock, VISITOR, text)["message"], "text": None}},
        {"update_id": 12},
    ]
    for update in ignored:
        clock.advance(4)
        assert binding.handle_update(update) is None, update
    assert binding.status()["current"] is None


def test_messages_older_than_two_minutes_are_ignored_silently():
    binding, clock = ready_binding()
    code = code_from(binding.status())
    assert binding.handle_update(telegram_message(clock, VISITOR, start_text(code), age=121)) is None
    assert binding.status()["current"] is None, "stale backlog must not bind"
    clock.advance(5)
    assert binding.handle_update(telegram_message(clock, VISITOR, start_text(code), age=119)) is not None
    assert binding.status()["current"] is not None


def test_binding_expires_ten_minutes_after_bind_time():
    binding, clock = ready_binding()
    scan(binding, clock)
    clock.advance(599)
    assert binding.status()["current"]["expires_in_seconds"] == 1
    clock.advance(1)
    assert binding.status()["current"] is None, "binding must expire at 600 s"


def test_rapid_repeat_commands_from_same_user_are_dropped():
    binding, clock = ready_binding()
    assert scan(binding, clock) is not None
    clock.advance(2)
    assert scan(binding, clock) is None, "second command inside 3 s must be dropped"
    clock.advance(1)
    assert scan(binding, clock) is not None


def test_global_reply_budget_caps_replies_but_still_binds_latest():
    binding, clock = ready_binding()
    code = code_from(binding.status())
    replies = [binding.handle_update(telegram_message(clock, 1000 + n, start_text(code),
                                                      username=f"user{n:03d}x", update_id=n))
               for n in range(25)]
    assert sum(r is not None for r in replies) == 20, "at most 20 bot replies per minute"
    assert binding.status()["current"]["display"] == "@us***"
    clock.advance(60)
    assert binding.handle_update(telegram_message(clock, 2000, start_text(code_from(binding.status())))) \
        is not None, "budget must refill after a minute"


def test_status_hides_deep_link_unless_poller_is_ready():
    binding, _ = ready_binding()
    for state in ("starting", "conflict", "webhook_active", "unauthorized", "unavailable"):
        binding.set_state(state)
        status = binding.status()
        assert status["state"] == state and status["deep_link"] is None, status


def test_status_reports_taipei_date_and_zero_count_initially():
    binding, _ = ready_binding()
    today = binding.status()["today"]
    assert today == {"date": "2026-10-13", "visitor_count": 0}, today


def test_target_number_is_reserved_only_after_recorded_delivery():
    binding, clock = ready_binding()
    scan(binding, clock)
    first = binding.resolve_target(clock())
    assert first.chat_id == VISITOR and first.number == 1, first
    assert binding.resolve_target(clock()).number == 1, "an unrecorded attempt must not consume a number"
    binding.record_delivery(first)
    clock.advance(5)
    scan(binding, clock, OTHER_VISITOR, username="bob_visitor")
    assert binding.resolve_target(clock()).number == 2
    assert binding.status()["today"]["visitor_count"] == 1


def test_no_binding_resolves_no_target():
    binding, clock = ready_binding()
    assert binding.resolve_target(clock()) is None


def test_unconfigured_telegram_marks_binding_unavailable_and_ignores_updates():
    clock = FakeClock(start=NOON)
    binding = DemoBinding(make_settings(demo_bind_enabled=True, demo_bind_db=":memory:"), clock)
    binding.open()
    status = binding.status()
    assert status["state"] == "unavailable" and status["deep_link"] is None, status
    assert binding.handle_update(telegram_message(clock, VISITOR, "/start")) is None
    assert binding.resolve_target(clock()) is None
