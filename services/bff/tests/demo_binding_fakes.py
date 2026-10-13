"""Shared builders for PRD-0024 booth-binding tests (Telegram update shapes only, no network)."""
from __future__ import annotations

from datetime import datetime

from bff.demo_binding.codes import TAIPEI

TOKEN = "123456:unit-test-token-not-a-real-secret"
FIXED_CHAT = "123"
BOT = "ems_booth_bot"
VISITOR = 7301204517
OTHER_VISITOR = 7301204999
NOON = datetime(2026, 10, 13, 10, 0, tzinfo=TAIPEI).timestamp()


def telegram_message(clock, user_id: int = VISITOR, text: str = "/start", *,
                     username: str | None = "dalelin_visitor", first_name: str = "Dale",
                     chat_type: str = "private", is_bot: bool = False, age: int = 0,
                     update_id: int = 1) -> dict:
    sender = {"id": user_id, "is_bot": is_bot, "first_name": first_name}
    if username is not None:
        sender["username"] = username
    return {"update_id": update_id, "message": {
        "message_id": update_id, "date": int(clock()) - age,
        "chat": {"id": user_id, "type": chat_type}, "from": sender, "text": text}}


def start_text(code: str) -> str:
    return f"/start {code}"


def code_from(binding_status: dict) -> str:
    link = binding_status.get("deep_link")
    assert link and "start=" in link, f"no deep link in {binding_status!r}"
    return link.rsplit("start=", 1)[1]
