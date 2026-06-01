"""device_corrections data access (human feedback, PRD-0003 Phase 1.4)."""
from __future__ import annotations

import json
from datetime import datetime

import asyncpg

_COLS = (
    "id, device_id, verdict, corrected_device_type, corrected_signals, "
    "human_explanation, created_at, created_by_key_id, salt_version, "
    "prompt_version_at_correction, applied_count, last_applied_at, is_active, "
    "deactivated_at, deactivation_reason"
)


def _shape(row: asyncpg.Record | None) -> dict | None:
    if row is None:
        return None
    out = dict(row)
    sigs = out.get("corrected_signals")
    if isinstance(sigs, str):
        out["corrected_signals"] = json.loads(sigs)
    return out


async def count_recent_by_key(conn: asyncpg.Connection, key_id: str, since: datetime) -> int:
    return await conn.fetchval(
        "SELECT count(*) FROM public.device_corrections WHERE created_by_key_id=$1 AND created_at >= $2",
        key_id, since,
    )


async def count_recent_by_device(conn: asyncpg.Connection, device_id: str, since: datetime) -> int:
    return await conn.fetchval(
        "SELECT count(*) FROM public.device_corrections WHERE device_id=$1 AND created_at >= $2",
        device_id, since,
    )


async def create(conn: asyncpg.Connection, data: dict) -> dict:
    row = await conn.fetchrow(
        f"""INSERT INTO public.device_corrections
              (device_id, verdict, corrected_device_type, corrected_signals,
               human_explanation, created_by_key_id, salt_version, prompt_version_at_correction)
           VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8)
           RETURNING {_COLS}""",
        data["device_id"], data["verdict"], data.get("corrected_device_type"),
        json.dumps(data.get("corrected_signals")) if data.get("corrected_signals") is not None else None,
        data["human_explanation"], data["created_by_key_id"], data["salt_version"],
        data.get("prompt_version_at_correction"),
    )
    return _shape(row)  # type: ignore[return-value]


async def list_for_device(conn: asyncpg.Connection, device_id: str, *, active_only: bool = False) -> list[dict]:
    where = "device_id=$1"
    if active_only:
        where += " AND is_active"
    rows = await conn.fetch(
        f"SELECT {_COLS} FROM public.device_corrections WHERE {where} ORDER BY created_at DESC, id DESC",
        device_id,
    )
    return [_shape(r) for r in rows]  # type: ignore[misc]


async def deactivate(conn: asyncpg.Connection, device_id: str, correction_id: int, reason: str) -> dict | None:
    row = await conn.fetchrow(
        f"""UPDATE public.device_corrections
              SET is_active=FALSE, deactivated_at=now(), deactivation_reason=$2
           WHERE id=$1 AND device_id=$3 AND is_active
           RETURNING {_COLS}""",
        correction_id, reason, device_id,
    )
    return _shape(row)
