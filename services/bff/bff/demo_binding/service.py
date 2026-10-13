"""Booth binding service: bot commands, status block and send-target resolution (PRD-0024).

Untrusted input: every Telegram update. Only private, non-bot, short `/start <code>` and
`/stop` messages younger than MAX_UPDATE_AGE_S are acted on; replies are rate limited.
Nothing here logs a chat id, username or display name.
"""
from __future__ import annotations

import logging
import math
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Callable

from ..config import Settings
from .codes import BindCodes, mask_display, taipei_day
from .store import BindingStore, StoreUnavailable

_log = logging.getLogger("bff.demo_binding")
STATES = frozenset({"ready", "starting", "webhook_active", "conflict", "unauthorized", "unavailable"})
_START = re.compile(r"/start(?:@[A-Za-z0-9_]{1,64})?(?:\s+(\S{1,64}))?")
_STOP = re.compile(r"/stop(?:@[A-Za-z0-9_]{1,64})?")
_BOT_USERNAME = re.compile(r"[A-Za-z0-9_]{3,64}")

EXPIRED_TEXT = "這個 QR Code 已失效，請重新掃描攤位螢幕上的 QR Code。"
STOPPED_TEXT = "已取消綁定，您不會再收到示範告警。"
NOT_BOUND_TEXT = "您目前沒有綁定。"


def bound_text(ttl_s: int) -> str:
    minutes = max(1, round(ttl_s / 60))
    return ("✅ 綁定完成！攤位人員按下按鈕後，您會在這裡收到 EMS 示範告警。"
            f"綁定 {minutes} 分鐘內有效，輸入 /stop 可取消。"
            "我們只暫存您的 Telegram 聊天 ID 以發送這則示範訊息，到期即刪除。")


@dataclass(frozen=True)
class Reply:
    chat_id: int
    text: str


@dataclass(frozen=True)
class Target:
    chat_id: int
    visitor_hash: str
    number: int
    day: str


class DemoBinding:
    MAX_UPDATE_AGE_S = 120    # spec-locked (PRD-0024 §5)
    USER_INTERVAL_S = 3       # spec-locked: one command per user per 3 s
    REPLIES_PER_MINUTE = 20   # spec-locked: global bot reply budget
    MAX_TEXT = 64

    def __init__(self, settings: Settings, clock: Callable[[], float] = time.time):
        self.settings = settings
        self.clock = clock
        self._codes = BindCodes(settings.demo_bind_code_rotate_s, settings.demo_bind_code_ttl_s, clock)
        self._store: BindingStore | None = None
        self._state = "unavailable"
        self._bot_username: str | None = None
        self._last_command: dict[int, float] = {}
        self._reply_times: tuple[float, ...] = ()

    # --- lifecycle / state ----------------------------------------------------------------
    def open(self) -> None:
        configured = bool(self.settings.telegram_bot_token.get_secret_value()
                          and self.settings.telegram_chat_id)
        if not configured:
            self.set_state("unavailable")
            return
        try:
            self._store = BindingStore(self.settings.demo_bind_db)
        except StoreUnavailable:
            _log.warning("demo_binding store_unavailable")
            self.set_state("unavailable")
            return
        self.set_state("starting")

    def close(self) -> None:
        if self._store is not None:
            self._store.close()
            self._store = None

    @property
    def pollable(self) -> bool:
        return self._store is not None and self._state != "unauthorized"

    @property
    def bot_username(self) -> str | None:
        return self._bot_username

    def set_state(self, state: str) -> None:
        if state not in STATES:
            raise ValueError(f"unknown binding state {state!r}")
        if self._store is None and state != "unavailable":
            return  # without durable state the feature stays unavailable
        if state != self._state:
            _log.info("demo_binding state=%s", state)
        self._state = state

    def set_bot_username(self, username: str) -> None:
        if not _BOT_USERNAME.fullmatch(username):
            raise ValueError("invalid bot username")
        if username != self._bot_username:
            _log.info("demo_binding bot=@%s", username)
        self._bot_username = username

    def _store_failed(self) -> None:
        _log.error("demo_binding store_failed")
        self.close()
        self.set_state("unavailable")

    # --- persistence helpers for the poller ---------------------------------------------
    def housekeeping(self) -> None:
        if self._store is None:
            return
        now = self.clock()
        try:
            self._store.ensure_day(taipei_day(now))
            self._store.get_binding(now)  # deletes an expired row
        except sqlite3.Error:
            self._store_failed()

    def load_offset(self) -> int | None:
        if self._store is None:
            return None
        try:
            return self._store.get_offset()
        except sqlite3.Error:
            self._store_failed()
            return None

    def save_offset(self, update_id: int) -> None:
        if self._store is None:
            return
        try:
            self._store.set_offset(update_id)
        except sqlite3.Error:
            self._store_failed()

    # --- staff side ------------------------------------------------------------------------
    def status(self) -> dict:
        now = self.clock()
        day = taipei_day(now)
        current, count = None, 0
        if self._store is not None:
            try:
                self._store.ensure_day(day)
                binding = self._store.get_binding(now)
                count = self._store.visitor_count()
            except sqlite3.Error:
                self._store_failed()
            else:
                if binding is not None:
                    current = {"display": binding.display,
                               "expires_in_seconds": max(1, math.ceil(binding.expires_at - now))}
        link = None
        if self._state == "ready" and self._bot_username:
            link = f"https://t.me/{self._bot_username}?start={self._codes.current()}"
        return {"state": self._state, "deep_link": link, "current": current,
                "today": {"date": day, "visitor_count": count}}

    def resolve_target(self, now: float) -> Target | None:
        """The visitor to alarm right now, with the number their message will carry."""
        if self._store is None:
            return None
        try:
            day = taipei_day(now)
            self._store.ensure_day(day)
            binding = self._store.get_binding(now)
            if binding is None:
                return None
            visitor = self._store.visitor_hash(binding.chat_id)
            number = self._store.number_for(visitor) or self._store.visitor_count() + 1
        except sqlite3.Error:
            self._store_failed()
            return None
        return Target(binding.chat_id, visitor, number, day)

    def record_delivery(self, target: Target) -> None:
        """Count a delivered (or possibly delivered) visitor message."""
        if self._store is None:
            return
        try:
            self._store.commit_number(target.day, target.visitor_hash, target.number)
        except sqlite3.Error:
            self._store_failed()

    # --- visitor side (Telegram updates) ---------------------------------------------------
    def handle_update(self, update: object) -> Reply | None:
        if self._store is None or not isinstance(update, dict):
            return None
        message = update.get("message")
        if not isinstance(message, dict):
            return None
        chat, sender, text, date = (message.get("chat"), message.get("from"),
                                    message.get("text"), message.get("date"))
        if not (isinstance(chat, dict) and isinstance(sender, dict) and isinstance(text, str)
                and type(date) is int and chat.get("type") == "private"
                and sender.get("is_bot") is False and type(sender.get("id")) is int
                and chat.get("id") == sender.get("id") and len(text) <= self.MAX_TEXT):
            return None
        now = self.clock()
        if now - date > self.MAX_UPDATE_AGE_S:
            return None
        start, stop = _START.fullmatch(text.strip()), _STOP.fullmatch(text.strip())
        if not (start or stop) or not self._allow_command(sender["id"], now):
            return None
        try:
            return self._start(sender, start.group(1), now) if start else self._stop(sender["id"], now)
        except sqlite3.Error:
            self._store_failed()
            return None

    def _start(self, sender: dict, code: str | None, now: float) -> Reply | None:
        if code is None or not self._codes.is_valid(code):
            _log.info("demo_binding event=rejected")
            return self._reply(sender["id"], EXPIRED_TEXT, now)
        self._store.set_binding(sender["id"], mask_display(sender), now, self.settings.demo_bind_ttl_s)
        _log.info("demo_binding event=bound")
        return self._reply(sender["id"], bound_text(self.settings.demo_bind_ttl_s), now)

    def _stop(self, user_id: int, now: float) -> Reply | None:
        if self._store.clear_binding(user_id):
            _log.info("demo_binding event=unbound")
            return self._reply(user_id, STOPPED_TEXT, now)
        return self._reply(user_id, NOT_BOUND_TEXT, now)

    def _allow_command(self, user_id: int, now: float) -> bool:
        recent = {uid: at for uid, at in self._last_command.items() if now - at < 60}
        last = recent.get(user_id)
        if last is not None and now - last < self.USER_INTERVAL_S:
            self._last_command = recent
            return False
        self._last_command = {**recent, user_id: now}
        return True

    def _reply(self, chat_id: int, text: str, now: float) -> Reply | None:
        window = tuple(at for at in self._reply_times if now - at < 60)
        if len(window) >= self.REPLIES_PER_MINUTE:
            self._reply_times = window
            return None
        self._reply_times = window + (now,)
        return Reply(chat_id, text)
