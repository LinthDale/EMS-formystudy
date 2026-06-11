"""Roles and the role -> channel-key mapping (PRD-0005 §9.1 [必過]).

Each session carries exactly ONE role; each role maps to AT MOST one
X-API-Key channel. READONLY maps to no channel at all (it can only consume
BFF-mediated public reads). The AI channel/MCP is deliberately absent: the
BFF never holds or forwards the AI key (PRD-0005 §1 / §6.1).
"""
from __future__ import annotations

from enum import Enum

from .config import Settings


class Role(str, Enum):
    OPS = "ops"
    INGEST = "ingest"
    READONLY = "readonly"


# NOTE on §9.1 "role downgrade invalidates the session": SessionManager.change_role
# applies a deliberately STRICTER rule — ANY role change revokes the session — so no
# privilege-ranking comparison exists here (privilege moves only through a fresh login).


def channel_key_for(role: Role, settings: Settings) -> str | None:
    """Resolve the single upstream key channel a role may spend.

    Returns None when the role has no channel (READONLY) — callers must then
    refuse to call key-gated upstreams (fail closed, never borrow another key).
    """
    if role is Role.OPS:
        return settings.ops_api_key or None
    if role is Role.INGEST:
        return settings.ingest_api_key or None
    return None
