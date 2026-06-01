"""X-API-Key authentication — three channels OPS / INGEST / AI (FR-310, §8.6.1).

Stateless: the presented key is matched (constant-time) against the three configured
keys to resolve a Channel; endpoints declare which channels they accept.
"""
from __future__ import annotations

import secrets
from enum import Enum

from fastapi import Depends, Header, HTTPException, Request


class Channel(str, Enum):
    OPS = "ops"
    INGEST = "ingest"
    AI = "ai"


def resolve_channel(api_key: str | None, settings) -> Channel | None:
    if not api_key:
        return None
    # constant-time compare against each configured (non-empty) key
    for channel, configured in (
        (Channel.OPS, settings.ops_api_key),
        (Channel.INGEST, settings.ingest_api_key),
        (Channel.AI, settings.ai_api_key),
    ):
        if configured and secrets.compare_digest(api_key, configured):
            return channel
    return None


def require(*allowed: Channel):
    """FastAPI dependency factory: 401 if key unknown, 403 if channel not allowed."""

    async def _dep(
        request: Request,
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> Channel:
        settings = request.app.state.settings
        channel = resolve_channel(x_api_key, settings)
        if channel is None:
            raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")
        if channel not in allowed:
            raise HTTPException(status_code=403, detail=f"channel {channel.value} not permitted here")
        return channel

    return Depends(_dep)