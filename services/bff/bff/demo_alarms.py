"""Fixed-recipient demo notifications; no device control or Grafana mutation (ADR-028)."""
from __future__ import annotations

import asyncio
import logging
import math
import re
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

import httpx
from fastapi import HTTPException

from .config import Settings

_log = logging.getLogger("bff.demo_alarm")
_TAIPEI = timezone(timedelta(hours=8))


class TelegramURLFilter(logging.Filter):
    """HTTPX logs its request URL at INFO; Telegram puts the secret in that URL."""
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        clean = re.sub(r"(/bot)[0-9]+:[A-Za-z0-9_-]+", r"\1[REDACTED]", message)
        if clean != message:
            record.msg, record.args = clean, ()
        return True


def protect_telegram_logs() -> None:
    logger = logging.getLogger("httpx")
    if not any(isinstance(f, TelegramURLFilter) for f in logger.filters):
        logger.addFilter(TelegramURLFilter())
    # httpcore DEBUG can contain the raw HTTP target; never enable it for this app.
    logging.getLogger("httpcore").setLevel(logging.WARNING)


@dataclass(frozen=True)
class Attempt:
    expires_at: float
    result: dict | None = None
    error: str | None = None


class DemoAlarms:
    TTL_SECONDS = 600
    MAX_ATTEMPTS = 64

    def __init__(self, settings: Settings, clock: Callable[[], float] = time.time):
        self.settings = settings
        self.clock = clock
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0
        self._attempts: dict[str, Attempt] = {}
        self._recent: deque[dict] = deque(maxlen=10)

    @property
    def configured(self) -> bool:
        return bool(self.settings.telegram_bot_token.get_secret_value() and self.settings.telegram_chat_id)

    @property
    def cooldown(self) -> int:
        return max(0, math.ceil(self._next_allowed - self.clock()))

    def status(self) -> dict:
        return {"configured": self.configured, "cooldown_seconds": self.cooldown,
                "recent": list(reversed(self._recent))}

    @staticmethod
    def _limited(seconds: int) -> HTTPException:
        return HTTPException(429, "demo_alarm_cooldown", headers={"Retry-After": str(max(1, seconds))})

    async def send(self, event_id: str, client: httpx.AsyncClient) -> dict:
        async with self._lock:
            now = self.clock()
            self._attempts = {key: value for key, value in self._attempts.items() if value.expires_at > now}
            previous = self._attempts.get(event_id)
            if previous:
                if previous.error:
                    raise HTTPException(502, previous.error)
                if previous.result is None:
                    raise HTTPException(409, "demo_alarm_in_progress")
                return {**previous.result, "cooldown_seconds": self.cooldown}
            if not self.configured:
                raise HTTPException(503, "telegram_not_configured")
            if self.cooldown:
                raise self._limited(self.cooldown)
            if len(self._attempts) >= self.MAX_ATTEMPTS:
                raise self._limited(math.ceil(min(a.expires_at for a in self._attempts.values()) - now))
            expires = now + self.TTL_SECONDS
            self._attempts[event_id] = Attempt(expires)
            self._next_allowed = now + self.settings.demo_alarm_cooldown_s

        started = time.monotonic()
        sent_at = datetime.fromtimestamp(now, _TAIPEI).isoformat(timespec="seconds")
        text = ("🔔 EMS 示範警報\n"
                "類型：DEMO／通知測試\n"
                f"事件：{event_id}\n時間：{sent_at}\n"
                "內容：由 EMS 警報中心手動觸發，確認 Telegram 通知通道。\n"
                "這是測試訊息，無需處置。")
        token = self.settings.telegram_bot_token.get_secret_value()
        error = "telegram_delivery_failed"
        try:
            async with asyncio.timeout(self.settings.telegram_timeout_s):
                response = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": self.settings.telegram_chat_id, "text": text},
                    timeout=self.settings.telegram_timeout_s, follow_redirects=False,
                )
            payload = response.json()
            if response.status_code == 429 and isinstance(payload, dict):
                parameters = payload.get("parameters")
                retry = parameters.get("retry_after") if isinstance(parameters, dict) else None
                if type(retry) is int:
                    self._next_allowed = max(self._next_allowed, self.clock() + min(3600, max(1, retry)))
            result = payload.get("result") if isinstance(payload, dict) else None
            chat = result.get("chat") if isinstance(result, dict) else None
            if not (response.status_code == 200 and isinstance(payload, dict) and payload.get("ok") is True
                    and isinstance(result, dict) and type(result.get("message_id")) is int
                    and result["message_id"] > 0 and isinstance(chat, dict)
                    and str(chat.get("id")) == self.settings.telegram_chat_id):
                raise ValueError("invalid Telegram acknowledgement")
        except (httpx.TimeoutException, TimeoutError):
            error = "telegram_delivery_unknown"
        except (httpx.HTTPError, ValueError, TypeError):
            pass  # Never log provider response/exception: both may include credentials.
        except asyncio.CancelledError:
            self._attempts[event_id] = Attempt(expires, error="telegram_delivery_unknown")
            raise
        else:
            delivery = {"status": "sent", "event_id": event_id, "sent_at": sent_at, "channel": "telegram"}
            self._attempts[event_id] = Attempt(expires, result=delivery)
            self._recent.append(delivery)
            _log.info("demo_alarm event_id=%s status=sent duration_ms=%d", event_id,
                      (time.monotonic() - started) * 1000)
            return {**delivery, "cooldown_seconds": self.cooldown}
        self._attempts[event_id] = Attempt(expires, error=error)
        _log.warning("demo_alarm event_id=%s status=%s duration_ms=%d", event_id, error,
                     (time.monotonic() - started) * 1000)
        raise HTTPException(502, error)
