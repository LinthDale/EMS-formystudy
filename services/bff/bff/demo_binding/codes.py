"""Rotating deep-link codes, display masking and the Asia/Taipei calendar day (PRD-0024)."""
from __future__ import annotations

import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping

# Taiwan has no DST; a fixed offset avoids depending on tzdata in the slim image.
TAIPEI = timezone(timedelta(hours=8))
GENERIC_DISPLAY = "Telegram 訪客"
_CODE = re.compile(r"b[A-Za-z0-9_-]{22}")
_USERNAME = re.compile(r"[A-Za-z0-9_]{1,64}")
_HIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Cn", "Co", "Cs", "Zl", "Zp", "Zs", "Mn", "Me"})


def taipei_day(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, TAIPEI).date().isoformat()


def taipei_minute(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, TAIPEI).strftime("%Y-%m-%d %H:%M")


def _new_code() -> str:
    return "b" + secrets.token_urlsafe(16)  # 128 bits -> 22 base64url characters


def mask_display(sender: Mapping) -> str:
    """Public panel label: '@' + two username chars, else the first visible first-name char."""
    username = sender.get("username")
    if isinstance(username, str) and _USERNAME.fullmatch(username):
        return "@" + username[:2] + "***"
    first_name = sender.get("first_name")
    if isinstance(first_name, str):
        for char in first_name:
            if unicodedata.category(char) not in _HIDDEN_CATEGORIES:
                return char + "***"
    return GENERIC_DISPLAY


class BindCodes:
    """In-memory start codes: a new one every rotate_s, each accepted for ttl_s after issue."""

    def __init__(self, rotate_s: int, ttl_s: int, clock: Callable[[], float],
                 new_code: Callable[[], str] = _new_code):
        self._rotate_s = rotate_s
        self._ttl_s = ttl_s
        self._clock = clock
        self._new_code = new_code
        self._issued: dict[str, float] = {}  # code -> issued_at
        self._current: str | None = None

    def _live(self, now: float) -> dict[str, float]:
        return {code: at for code, at in self._issued.items() if now - at < self._ttl_s}

    def current(self) -> str:
        now = self._clock()
        live = self._live(now)
        if self._current is None or now - self._issued.get(self._current, -self._rotate_s) >= self._rotate_s:
            self._current = self._new_code()
            live = {**live, self._current: now}
        self._issued = live
        return self._current

    def is_valid(self, code: object) -> bool:
        if not isinstance(code, str) or not _CODE.fullmatch(code):
            return False
        issued = self._issued.get(code)
        return issued is not None and self._clock() - issued < self._ttl_s
