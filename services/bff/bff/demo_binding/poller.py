"""Telegram getUpdates long polling for booth binding (PRD-0024 FR-2410, ADR-036).

Outbound only: the BFF stays loopback-bound, so no webhook endpoint exists. A configured
webhook or a second poller is reported as state, never "fixed" by deleting the webhook.
Provider responses and exceptions are never logged (both may carry the bot token).
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Awaitable, Callable

import httpx

from ..config import Settings
from .service import DemoBinding, Reply

_log = logging.getLogger("bff.demo_binding")
_BOT_USERNAME = re.compile(r"[A-Za-z0-9_]{3,64}")


class TelegramError(Exception):
    def __init__(self, status: int, retry_after: int | None = None):
        super().__init__(f"telegram status {status}")
        self.status = status
        self.retry_after = retry_after


class TelegramPoller:
    WEBHOOK_RECHECK_S = 300
    CONFLICT_RETRY_S = 30
    MAX_BACKOFF_S = 60
    IDLE_S = 1          # pause after an empty batch (guards against a tight loop)
    BATCH_LIMIT = 100

    def __init__(self, settings: Settings, binding: DemoBinding, client: httpx.AsyncClient,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self.settings = settings
        self.binding = binding
        self.client = client
        self._sleep = sleep
        self._prepared = False
        self._first_poll = True
        self._failures = 0

    async def run(self) -> None:
        while True:
            try:
                delay = await self.step()
            except asyncio.CancelledError:
                raise
            except Exception:  # supervisor: fixed message only, never provider details
                _log.error("demo_binding poller_error")
                self.binding.set_state("unavailable")
                delay = self.MAX_BACKOFF_S
            if delay is None:
                return
            if delay:
                await self._sleep(delay)

    async def step(self) -> float | None:
        """One poll cycle. Returns seconds to wait before the next one; None stops polling."""
        self.binding.housekeeping()
        if not self.binding.pollable:
            return None
        try:
            if not self._prepared:
                webhook = await self._call("getWebhookInfo", {})
                if isinstance(webhook, dict) and webhook.get("url"):
                    self.binding.set_state("webhook_active")
                    return self.WEBHOOK_RECHECK_S
                me = await self._call("getMe", {})
                username = me.get("username") if isinstance(me, dict) else None
                if not (isinstance(username, str) and _BOT_USERNAME.fullmatch(username)):
                    raise ValueError("unexpected getMe result")
                self.binding.set_bot_username(username)
                self._prepared = True
            updates = await self._poll()
        except TelegramError as error:
            return self._on_error(error)
        except (httpx.HTTPError, ValueError, TypeError):
            return self._backoff()
        self.binding.set_state("ready")
        self._failures = 0
        await self._process(updates)
        return 0 if updates else self.IDLE_S

    async def _poll(self) -> list:
        payload = {"timeout": 0 if self._first_poll else self.settings.telegram_poll_timeout_s,
                   "limit": self.BATCH_LIMIT, "allowed_updates": ["message"]}
        offset = self.binding.load_offset()
        if offset is not None:
            payload["offset"] = offset + 1
        updates = await self._call("getUpdates", payload,
                                   timeout=self.settings.telegram_poll_timeout_s + 10)
        if not isinstance(updates, list):
            raise ValueError("unexpected getUpdates result")
        self._first_poll = False
        return updates

    async def _process(self, updates: list) -> None:
        last = None
        for update in updates:
            if not isinstance(update, dict) or type(update.get("update_id")) is not int:
                continue
            reply = self.binding.handle_update(update)
            if reply is not None:
                await self._reply(reply)
            last = update["update_id"] if last is None else max(last, update["update_id"])
        if last is not None:
            self.binding.save_offset(last)

    async def _reply(self, reply: Reply) -> None:
        try:
            await self._call("sendMessage", {"chat_id": reply.chat_id, "text": reply.text})
        except (TelegramError, httpx.HTTPError, ValueError, TypeError):
            _log.warning("demo_binding reply_failed")

    def _on_error(self, error: TelegramError) -> float | None:
        if error.status in (401, 404):
            self.binding.set_state("unauthorized")
            return None
        if error.status == 409:
            self.binding.set_state("conflict")
            return self.CONFLICT_RETRY_S
        if error.status == 429 and error.retry_after:
            return min(3600, max(1, error.retry_after))
        return self._backoff()

    def _backoff(self) -> float:
        self.binding.set_state("unavailable")
        delay = min(self.MAX_BACKOFF_S, 2 ** self._failures)
        self._failures += 1
        return delay

    async def _call(self, method: str, payload: dict, timeout: float | None = None) -> object:
        token = self.settings.telegram_bot_token.get_secret_value()
        response = await self.client.post(
            f"https://api.telegram.org/bot{token}/{method}", json=payload,
            timeout=timeout if timeout is not None else self.settings.telegram_timeout_s)
        try:
            body = response.json()
        except ValueError:
            body = None
        if response.status_code == 200 and isinstance(body, dict) and body.get("ok") is True \
                and "result" in body:
            return body["result"]
        parameters = body.get("parameters") if isinstance(body, dict) else None
        retry = parameters.get("retry_after") if isinstance(parameters, dict) else None
        raise TelegramError(response.status_code, retry if type(retry) is int else None)
