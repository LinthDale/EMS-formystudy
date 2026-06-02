"""device_audit_log data access (PRD-0003 §8.7.5 / FR-339 / FR-344).

Append-only: only record() (INSERT) and window-count reads. No update/delete — the
table is tamper-resistant by grant (migration 014). record() runs inside the caller's
transaction so the audit row commits atomically with the action it describes.
"""
from __future__ import annotations

import json
from datetime import datetime

import asyncpg

EVENT_TYPES = frozenset({
    "freeze_override", "ai_feedback_create", "demote",
    "deactivate", "rate_limit_exceeded", "guardrail_block", "status_advance",
})


async def record(
    conn: asyncpg.Connection, *, event_type: str, actor: str,
    device_id: str | None = None, actor_key_id: str | None = None,
    salt_version: str | None = None, request_id: str | None = None,
    correction_id: int | None = None, outcome: str | None = None,
    detail: dict | None = None,
) -> int:
    """Append one audit row in the caller's transaction; returns its id. event_type is
    validated against the DB CHECK constraint too, but we fail fast here with a clear error."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown audit event_type {event_type!r}")
    return await conn.fetchval(
        """INSERT INTO public.device_audit_log
               (event_type, device_id, actor, actor_key_id, salt_version,
                request_id, correction_id, outcome, detail)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb) RETURNING id""",
        event_type, device_id, actor, actor_key_id, salt_version,
        request_id, correction_id, outcome, json.dumps(detail or {}),
    )


async def count_recent(
    conn: asyncpg.Connection, *, event_type: str, since: datetime,
    device_id: str | None = None, actor_key_id: str | None = None,
) -> int:
    """Count events of a type since a cutoff, optionally scoped by device or key.
    Serves FR-339 (per-device guardrail BLOCK / 1h) and FR-344 (per-key deactivate window)."""
    clauses, args = ["event_type = $1", "event_time >= $2"], [event_type, since]
    if device_id is not None:
        args.append(device_id)
        clauses.append(f"device_id = ${len(args)}")
    if actor_key_id is not None:
        args.append(actor_key_id)
        clauses.append(f"actor_key_id = ${len(args)}")
    return await conn.fetchval(
        f"SELECT count(*) FROM public.device_audit_log WHERE {' AND '.join(clauses)}", *args
    )
