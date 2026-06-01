"""Device table data access (asyncpg). Parameterized queries only."""
from __future__ import annotations

import asyncpg

_COLS = (
    "device_id, device_type, status, protocol, vendor, model, location, gateway_id, "
    "classified_by, created_at, updated_at, last_seen_at, confirmed_at"
)
# columns a plain PATCH may set (status / classified_by / lifecycle handled by dedicated endpoints)
_UPDATABLE = ("device_type", "protocol", "vendor", "model", "location", "gateway_id")


async def create(conn: asyncpg.Connection, data: dict) -> asyncpg.Record:
    return await conn.fetchrow(
        f"""INSERT INTO public.devices
            (device_id, device_type, protocol, vendor, model, location, gateway_id, status)
            VALUES ($1,$2,$3,$4,$5,$6,$7,'candidate')
            RETURNING {_COLS}""",
        data["device_id"], data.get("device_type"), data.get("protocol"),
        data.get("vendor"), data.get("model"), data.get("location"), data.get("gateway_id"),
    )


async def get(conn: asyncpg.Connection, device_id: str) -> asyncpg.Record | None:
    return await conn.fetchrow(f"SELECT {_COLS} FROM public.devices WHERE device_id=$1", device_id)


async def list_(conn: asyncpg.Connection, status: str | None = None, stale: bool | None = None) -> list[asyncpg.Record]:
    clauses, args = [], []
    if status:
        args.append(status)
        clauses.append(f"status=${len(args)}")
    if stale is True:
        clauses.append("stale_marked_at IS NOT NULL")
    elif stale is False:
        clauses.append("stale_marked_at IS NULL")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return await conn.fetch(f"SELECT {_COLS} FROM public.devices{where} ORDER BY device_id", *args)


async def update(conn: asyncpg.Connection, device_id: str, fields: dict) -> asyncpg.Record | None:
    sets, args = [], []
    for col in _UPDATABLE:
        if col in fields and fields[col] is not None:
            args.append(fields[col])
            sets.append(f"{col}=${len(args)}")
    if not sets:
        return await get(conn, device_id)
    sets.append("updated_at=now()")
    args.append(device_id)
    return await conn.fetchrow(
        f"UPDATE public.devices SET {', '.join(sets)} WHERE device_id=${len(args)} RETURNING {_COLS}",
        *args,
    )


async def set_lifecycle(
    conn: asyncpg.Connection, device_id: str, *, status: str,
    classified_by: str | None = None, device_type: str | None = None, set_confirmed_at: bool = False,
) -> asyncpg.Record | None:
    sets, args = ["status=$1", "updated_at=now()"], [status]
    if classified_by is not None:
        args.append(classified_by)
        sets.append(f"classified_by=${len(args)}")
    if device_type is not None:
        args.append(device_type)
        sets.append(f"device_type=${len(args)}")
    if set_confirmed_at:
        sets.append("confirmed_at=now()")
    args.append(device_id)
    return await conn.fetchrow(
        f"UPDATE public.devices SET {', '.join(sets)} WHERE device_id=${len(args)} RETURNING {_COLS}",
        *args,
    )