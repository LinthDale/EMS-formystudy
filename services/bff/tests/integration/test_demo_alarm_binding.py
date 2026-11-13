"""PRD-0024: booth QR binding through the real ASGI app; Telegram replaced at the HTTP boundary,
state in a temporary SQLite file (no docker, no network)."""
from __future__ import annotations

import json
import os
import stat
import time
from contextlib import contextmanager
from datetime import datetime
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from bff.demo_binding.codes import TAIPEI
from bff.demo_binding.store import BindingStore, StoreUnavailable
from bff.main import create_app
from tests.account_fakes import FakeAccounts
from tests.conftest import AUTH_USERS, ORIGIN, FakeClock, login, make_settings
from tests.demo_binding_fakes import (BOT, FIXED_CHAT, NOON, OTHER_VISITOR, TOKEN, VISITOR,
                                      code_from, start_text, telegram_message)

pytestmark = pytest.mark.integration
URL = "/api/alarms/demo"


class Telegram:
    """sendMessage boundary: ACKs with the chat it was asked to deliver to."""

    def __init__(self):
        self.calls: list[dict] = []
        self.mode = "ok"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        self.calls.append(payload)
        if self.mode == "timeout":
            raise httpx.ReadTimeout("private URL " + TOKEN, request=request)
        if self.mode == "reject":
            return httpx.Response(403, json={"ok": False, "description": TOKEN})
        chat = 999 if self.mode == "wrong_chat" else int(payload["chat_id"])
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(self.calls),
                                                                "chat": {"id": chat}}})


def booth_settings(tmp_path, **overrides):
    values = {"telegram_bot_token": TOKEN, "telegram_chat_id": FIXED_CHAT, "demo_bind_enabled": True,
              "demo_bind_db": str(tmp_path / "demo-alarm" / "state.sqlite3")}
    return make_settings(**{**values, **overrides})


@contextmanager
def running(settings, clock, telegram, *, ready=True):
    app = create_app(account_repository=FakeAccounts(AUTH_USERS), settings=settings,
                     telegram_transport=httpx.MockTransport(telegram), clock=clock,
                     demo_binder_autostart=False)
    with TestClient(app, base_url=ORIGIN) as client:
        binding = app.state.demo_binding
        if ready and binding is not None:
            binding.set_bot_username(BOT)
            binding.set_state("ready")
        login(client, "ops_user", "ops-pw")
        yield client, binding


def press(client):
    return client.post(URL, json={"request_id": str(uuid4())}, headers={"Origin": ORIGIN})


def scan(client, binding, clock, user_id=VISITOR, username="dalelin_visitor", update_id=1):
    code = code_from(client.get(URL).json()["binding"])
    reply = binding.handle_update(telegram_message(clock, user_id, start_text(code),
                                                   username=username, update_id=update_id))
    assert reply is not None and "綁定完成" in reply.text, reply


@pytest.fixture
def booth(tmp_path):
    clock, telegram = FakeClock(start=NOON), Telegram()
    with running(booth_settings(tmp_path), clock, telegram) as (client, binding):
        yield client, binding, clock, telegram


def test_bound_visitor_press_sends_only_visitor_text_in_taipei_time(booth):
    client, binding, clock, telegram = booth
    scan(client, binding, clock)
    sent = press(client)
    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert (body["status"], body["target"], body["visitor_number"]) == ("sent", "visitor", 1), body
    assert len(telegram.calls) == 1, "the fixed chat must not receive a copy"
    payload = telegram.calls[0]
    assert payload["chat_id"] == VISITOR, payload
    assert payload["text"] == "🚨 EMS 示範告警\n您是今天第 1 位觸發告警的客人！\n時間：2026-10-13 10:00", payload
    assert "parse_mode" not in payload


def test_same_visitor_keeps_number_and_next_visitor_gets_next(booth):
    client, binding, clock, telegram = booth
    scan(client, binding, clock)
    assert press(client).json()["visitor_number"] == 1
    clock.advance(31)
    assert press(client).json()["visitor_number"] == 1, "the same visitor keeps their number"
    scan(client, binding, clock, OTHER_VISITOR, username="bob_visitor", update_id=2)
    clock.advance(31)
    assert press(client).json()["visitor_number"] == 2
    assert client.get(URL).json()["binding"]["today"] == {"date": "2026-10-13", "visitor_count": 2}


def test_no_binding_press_sends_original_message_to_fixed_chat_uncounted(booth):
    client, _, _, telegram = booth
    body = press(client).json()
    assert (body["target"], body["visitor_number"]) == ("default", None), body
    payload = telegram.calls[0]
    assert payload["chat_id"] == FIXED_CHAT and "DEMO" in payload["text"] and "無需處置" in payload["text"]
    assert client.get(URL).json()["binding"]["today"]["visitor_count"] == 0


def test_expired_or_stopped_binding_falls_back_to_fixed_chat(booth):
    client, binding, clock, telegram = booth
    scan(client, binding, clock)
    clock.advance(601)
    assert press(client).json()["target"] == "default", "an expired binding must fall back"
    scan(client, binding, clock, update_id=2)
    clock.advance(5)
    binding.handle_update(telegram_message(clock, VISITOR, "/stop", update_id=3))
    clock.advance(31)
    assert press(client).json()["target"] == "default", "/stop must fall back"
    assert [p["chat_id"] for p in telegram.calls] == [FIXED_CHAT, FIXED_CHAT]


def test_status_shows_masked_binding_without_identifiers(booth):
    client, binding, clock, telegram = booth
    scan(client, binding, clock)
    press(client)
    status = client.get(URL)
    block = status.json()["binding"]
    assert block["state"] == "ready" and block["deep_link"].startswith(f"https://t.me/{BOT}?start=")
    assert block["current"] == {"display": "@da***", "expires_in_seconds": 600}, block
    recent = status.json()["recent"][0]
    assert (recent["target"], recent["visitor_number"]) == ("visitor", 1), recent
    for secret in (str(VISITOR), "dalelin_visitor", TOKEN):
        assert secret not in status.text, f"{secret!r} leaked in status"


def test_binding_status_requires_ops_session(booth):
    client, _, _, _ = booth
    login(client, "view_user", "view-pw")
    assert client.get(URL).status_code == 403


def test_definite_failure_releases_number_but_timeout_keeps_it(booth):
    client, binding, clock, telegram = booth
    scan(client, binding, clock)
    for mode in ("reject", "wrong_chat"):
        telegram.mode = mode
        failed = press(client)
        assert failed.status_code == 502 and TOKEN not in failed.text, failed.text
        clock.advance(31)
    assert client.get(URL).json()["binding"]["today"]["visitor_count"] == 0
    telegram.mode = "timeout"
    unknown = press(client)
    assert unknown.status_code == 502 and unknown.json()["detail"] == "telegram_delivery_unknown"
    assert client.get(URL).json()["binding"]["today"]["visitor_count"] == 1, "unknown outcome is counted"
    telegram.mode = "ok"
    scan(client, binding, clock, OTHER_VISITOR, username="bob_visitor", update_id=2)
    clock.advance(31)
    assert press(client).json()["visitor_number"] == 2


def test_restart_keeps_binding_and_daily_count(tmp_path):
    clock, telegram = FakeClock(start=NOON), Telegram()
    settings = booth_settings(tmp_path)
    with running(settings, clock, telegram) as (client, binding):
        scan(client, binding, clock)
        assert press(client).json()["visitor_number"] == 1
    clock.advance(31)
    with running(settings, clock, telegram) as (client, _):
        block = client.get(URL).json()["binding"]
        assert block["current"]["display"] == "@da***" and block["today"]["visitor_count"] == 1, block
        assert press(client).json()["visitor_number"] == 1, "same visitor after restart keeps number"


def test_midnight_rollover_restarts_numbering_for_new_day(tmp_path):
    clock = FakeClock(start=datetime(2026, 10, 13, 23, 58, tzinfo=TAIPEI).timestamp())
    with running(booth_settings(tmp_path), clock, Telegram()) as (client, binding):
        scan(client, binding, clock)
        assert press(client).json()["visitor_number"] == 1
        clock.advance(180)
        body = press(client).json()
        assert body["visitor_number"] == 1 and body["target"] == "visitor", body
        assert client.get(URL).json()["binding"]["today"] == {"date": "2026-10-14", "visitor_count": 1}


def test_feature_disabled_keeps_prd0019_behaviour(tmp_path):
    telegram = Telegram()
    settings = booth_settings(tmp_path, demo_bind_enabled=False)
    with running(settings, FakeClock(start=NOON), telegram) as (client, binding):
        assert binding is None
        assert client.get(URL).json()["binding"] is None
        assert press(client).json()["target"] == "default"
        assert telegram.calls[0]["chat_id"] == FIXED_CHAT
    assert not (tmp_path / "demo-alarm").exists(), "disabled feature must not create state"


def test_locked_state_file_disables_binding_but_demo_still_sends(tmp_path):
    settings = booth_settings(tmp_path)
    holder = BindingStore(settings.demo_bind_db)
    try:
        with pytest.raises(StoreUnavailable):
            BindingStore(settings.demo_bind_db)
        telegram = Telegram()
        with running(settings, FakeClock(start=NOON), telegram, ready=False) as (client, _):
            block = client.get(URL).json()["binding"]
            assert block["state"] == "unavailable" and block["deep_link"] is None, block
            assert press(client).json()["target"] == "default"
    finally:
        holder.close()


def test_autostarted_poller_reaches_ready_and_stops_on_shutdown(tmp_path):
    methods = []

    def telegram(request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        methods.append(method)
        result = {"getWebhookInfo": {"url": ""}, "getMe": {"username": BOT}, "getUpdates": []}
        return httpx.Response(200, json={"ok": True, "result": result.get(method, {})})

    app = create_app(account_repository=FakeAccounts(AUTH_USERS), settings=booth_settings(tmp_path),
                     telegram_transport=httpx.MockTransport(telegram), clock=FakeClock(start=NOON))
    with TestClient(app, base_url=ORIGIN) as client:
        login(client, "ops_user", "ops-pw")
        block = client.get(URL).json()["binding"]
        for _ in range(100):
            if block["state"] == "ready":
                break
            time.sleep(0.02)
            block = client.get(URL).json()["binding"]
        assert block["state"] == "ready" and block["deep_link"].startswith(f"https://t.me/{BOT}?start="), block
    assert methods[:3] == ["getWebhookInfo", "getMe", "getUpdates"], methods
    assert "deleteWebhook" not in methods


def test_state_file_and_directory_are_private(tmp_path):
    store = BindingStore(str(tmp_path / "demo-alarm" / "state.sqlite3"))
    try:
        file_mode = stat.S_IMODE(os.stat(tmp_path / "demo-alarm" / "state.sqlite3").st_mode)
        dir_mode = stat.S_IMODE(os.stat(tmp_path / "demo-alarm").st_mode)
        assert (file_mode, dir_mode) == (0o600, 0o700), (oct(file_mode), oct(dir_mode))
    finally:
        store.close()
