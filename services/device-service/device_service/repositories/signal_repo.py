"""device_signals data access (current-state + soft delete, ADR-011)."""
from __future__ import annotations

import asyncpg

_COLS = "id, device_id, signal_name, unit, datatype, direction, status"


async def list_active(conn: asyncpg.Connection, device_id: str) -> list[asyncpg.Record]:
    return await conn.fetch(
        f"SELECT {_COLS} FROM public.device_signals WHERE device_id=$1 AND status='active' ORDER BY signal_name",
        device_id,
    )


async def add(conn: asyncpg.Connection, device_id: str, sig: dict) -> asyncpg.Record:
    return await conn.fetchrow(
        f"""INSERT INTO public.device_signals
            (device_id, signal_name, unit, datatype, direction, source_ref, status)
            VALUES ($1,$2,$3,$4,$5,$6,'active')
            RETURNING {_COLS}""",
        device_id, sig["signal_name"], sig.get("unit"), sig.get("datatype"),
        sig.get("direction"), sig.get("source_ref"),
    )


async def retire(conn: asyncpg.Connection, device_id: str, signal_name: str) -> str | None:
    return await conn.fetchval(
        """UPDATE public.device_signals SET status='retired', retired_at=now()
           WHERE device_id=$1 AND signal_name=$2 AND status='active' RETURNING signal_name""",
        device_id, signal_name,
    )