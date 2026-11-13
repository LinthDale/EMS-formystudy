"""PRD-0024 FR-2410: getUpdates long-poll lifecycle with Telegram faked at the HTTP boundary."""
from __future__ import annotations

import asyncio
import json

import httpx

from bff.demo_alarms import protect_telegram_logs
from bff.demo_binding.poller import TelegramPoller
from bff.demo_binding.service import DemoBinding
from tests.conftest import FakeClock, make_settings
from tests.demo_binding_fakes import (BOT, FIXED_CHAT, NOON, TOKEN, VISITOR, code_from,
                                      start_text, telegram_message)


class FakeTelegram:
    """Scripted Bot API: records (method, payload); never implements deleteWebhook."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.webhook_url = ""
        self.batches: list[list] = []
        self.results: dict[str, object] = {}
        self.failures: list = []  # consumed one per call: Exception or (status, body)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        payload = json.loads(request.content or b"{}")
        self.calls.append((method, payload))
        assert method != "deleteWebhook", "the poller must never delete a webhook"
        if self.failures:
            failure = self.failures.pop(0)
            if isinstance(failure, Exception):
                raise failure
            return httpx.Response(failure[0], json=failure[1])
        if method in self.results:
            result = self.results[method]
        elif method == "getWebhookInfo":
            result = {"url": self.webhook_url, "pending_update_count": 0}
        elif method == "getMe":
            result = {"id": 42, "is_bot": True, "username": BOT}
        elif method == "getUpdates":
            result = self.batches.pop(0) if self.batches else []
        else:
            result = {"message_id": 9, "chat": {"id": payload.get("chat_id")}}
        return httpx.Response(200, json={"ok": True, "result": result})

    def methods(self) -> list[str]:
        return [method for method, _ in self.calls]


def scenario(check):
    async def body():
        clock = FakeClock(start=NOON)
        settings = make_settings(telegram_bot_token=TOKEN, telegram_chat_id=FIXED_CHAT,
                                 demo_bind_enabled=True, demo_bind_db=":memory:")
        binding = DemoBinding(settings, clock)
        binding.open()
        telegram, sleeps = FakeTelegram(), []

        async def sleep(seconds):
            sleeps.append(seconds)

        async with httpx.AsyncClient(transport=httpx.MockTransport(telegram)) as client:
            poller = TelegramPoller(settings, binding, client, sleep=sleep)
            await check(poller, binding, telegram, clock, sleeps)
    asyncio.run(body())


def test_first_cycle_checks_webhook_and_bot_then_reports_ready():
    async def check(poller, binding, telegram, clock, sleeps):
        assert await poller.step() == 1, "an empty batch idles one second"
        assert telegram.methods() == ["getWebhookInfo", "getMe", "getUpdates"], telegram.methods()
        first = telegram.calls[-1][1]
        assert first["timeout"] == 0 and first["allowed_updates"] == ["message"], first
        assert "offset" not in first, first
        status = binding.status()
        assert status["state"] == "ready", status
        assert status["deep_link"].startswith(f"https://t.me/{BOT}?start="), status
    scenario(check)


def test_batch_is_processed_then_next_cycle_long_polls_from_offset():
    async def check(poller, binding, telegram, clock, sleeps):
        await poller.step()
        code = code_from(binding.status())
        telegram.batches.append([
            telegram_message(clock, VISITOR, start_text(code), update_id=41),
            {"update_id": 42, "edited_message": {"text": "ignored"}},
        ])
        assert await poller.step() == 0, "a non-empty batch polls again immediately"
        sent = [payload for method, payload in telegram.calls if method == "sendMessage"]
        assert len(sent) == 1 and sent[0]["chat_id"] == VISITOR, sent
        assert "綁定完成" in sent[0]["text"], sent
        assert binding.load_offset() == 42
        await poller.step()
        last = telegram.calls[-1][1]
        assert last["offset"] == 43 and last["timeout"] == 25, last
    scenario(check)


def test_stale_backlog_is_confirmed_without_any_reply():
    async def check(poller, binding, telegram, clock, sleeps):
        telegram.batches.append([telegram_message(clock, VISITOR + n, "/start", age=600, update_id=n)
                                 for n in range(1, 4)])
        await poller.step()
        assert "sendMessage" not in telegram.methods(), telegram.methods()
        assert binding.load_offset() == 3
    scenario(check)


def test_active_webhook_pauses_binding_and_is_never_deleted():
    async def check(poller, binding, telegram, clock, sleeps):
        telegram.webhook_url = "https://example.invalid/hook"
        assert await poller.step() == 300
        status = binding.status()
        assert status["state"] == "webhook_active" and status["deep_link"] is None, status
        assert "getUpdates" not in telegram.methods(), telegram.methods()
    scenario(check)


def test_conflict_reports_state_and_retries_after_thirty_seconds():
    async def check(poller, binding, telegram, clock, sleeps):
        await poller.step()
        telegram.failures.append((409, {"ok": False, "error_code": 409, "description": "Conflict"}))
        assert await poller.step() == 30
        status = binding.status()
        assert status["state"] == "conflict" and status["deep_link"] is None, status
    scenario(check)


def test_unauthorized_token_stops_the_poll_loop():
    async def check(poller, binding, telegram, clock, sleeps):
        telegram.failures.extend([httpx.ConnectError("offline"),
                                  (401, {"ok": False, "error_code": 401})])
        await asyncio.wait_for(poller.run(), 1)
        assert binding.status()["state"] == "unauthorized"
        assert sleeps == [1], f"one backoff before the fatal 401, got {sleeps}"
    scenario(check)


def test_network_failures_back_off_exponentially_to_sixty_seconds():
    async def check(poller, binding, telegram, clock, sleeps):
        telegram.failures.extend([httpx.ConnectError("offline")] * 8)
        delays = [await poller.step() for _ in range(8)]
        assert delays == [1, 2, 4, 8, 16, 32, 60, 60], delays
        assert binding.status()["state"] == "unavailable"
        assert await poller.step() == 1 and binding.status()["state"] == "ready"
        telegram.failures.append(httpx.ConnectError("offline"))
        assert await poller.step() == 1, "backoff restarts after a success"
    scenario(check)


def test_malformed_updates_result_is_treated_as_transient_failure():
    async def check(poller, binding, telegram, clock, sleeps):
        telegram.results["getUpdates"] = {"not": "a list"}
        assert await poller.step() == 1
        assert binding.status()["state"] == "unavailable"
    scenario(check)


def test_rate_limited_poll_waits_for_retry_after():
    async def check(poller, binding, telegram, clock, sleeps):
        await poller.step()
        telegram.failures.append((429, {"ok": False, "parameters": {"retry_after": 7}}))
        assert await poller.step() == 7
    scenario(check)


def test_poll_logs_drop_getupdates_lines_and_redact_token(caplog):
    caplog.set_level("INFO")
    protect_telegram_logs()

    async def check(poller, binding, telegram, clock, sleeps):
        await poller.step()
    scenario(check)
    assert "getUpdates" not in caplog.text, "long-poll request lines must not flood the log"
    assert "getMe" in caplog.text and "[REDACTED]" in caplog.text, caplog.text
    assert TOKEN not in caplog.text
