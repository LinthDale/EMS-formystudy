"""Device table data access (asyncpg). Parameterized queries only."""
from __future__ import annotations

import json

import asyncpg

_COLS = (
    "device_id, device_type, status, protocol, vendor, model, location, gateway_id, "
    "classified_by, ai_confidence, created_at, updated_at, last_seen_at, confirmed_at"
)
# sort-column allowlist for list_ (PRD-0005 GATE-2). Keys are the API-facing names; values
# are the actual columns. NEVER interpolate raw user input into ORDER BY — look up here.
_SORT_COLS = {
    "device_id": "device_id",
    "device_type": "device_type",
    "status": "status",
    "ai_confidence": "ai_confidence",
    "created_at": "created_at",
    "updated_at": "updated_at",
    "last_seen_at": "last_seen_at",
}
# columns a plain PATCH may set (status / classified_by / lifecycle handled by dedicated endpoints)
_UPDATABLE = ("device_type", "protocol", "vendor", "model", "location", "gateway_id")
# classified_by values that mark a row as human-owned (frozen by the migration-010 trigger)
FREEZE_SET = ("human", "manual_override", "migration_backfill")


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


async def list_(
    conn: asyncpg.Connection, status: str | None = None, stale: bool | None = None,
    device_type: str | None = None, limit: int | None = None, offset: int = 0,
    sort: str = "device_id", order: str = "asc",
) -> list[asyncpg.Record]:
    if sort not in _SORT_COLS:  # defense-in-depth: the route Literal already guards this
        raise ValueError(f"unsortable column: {sort!r}")
    clauses, args = [], []
    if status:
        args.append(status)
        clauses.append(f"status=${len(args)}")
    if stale is True:
        clauses.append("stale_marked_at IS NOT NULL")
    elif stale is False:
        clauses.append("stale_marked_at IS NULL")
    if device_type:
        args.append(device_type)
        clauses.append(f"device_type=${len(args)}")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    # Postgres DESC puts NULLs FIRST by default -> always emit NULLS LAST explicitly;
    # device_id is the stable secondary key for deterministic pagination.
    direction = "DESC" if order == "desc" else "ASC"
    order_by = f" ORDER BY {_SORT_COLS[sort]} {direction} NULLS LAST, device_id ASC"
    paging = ""
    if limit is not None:
        args.append(limit)
        paging += f" LIMIT ${len(args)}"
    if offset:  # route enforces ge=0; 0 is a Postgres no-op -> omit (limit uses `is not None`: None=unlimited)
        args.append(offset)
        paging += f" OFFSET ${len(args)}"
    return await conn.fetch(f"SELECT {_COLS} FROM public.devices{where}{order_by}{paging}", *args)


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

async def demote_to_candidate(conn: asyncpg.Connection, device_id: str) -> asyncpg.Record | None:
    """Re-open a device for review (FR-330 demote_to_candidate / §8.6 confirmed→candidate).
    Clears classified_by so the AI path may re-classify it (apply_outcome requires a
    non-frozen candidate); also clears confirmed_at. status/classified_by ARE frozen
    columns, so the caller must hold a freeze_override token (ops_tx) for a frozen row;
    confirmed_at is NOT frozen but is cleared in the same token-bearing UPDATE.
    Returns None if the device_id no longer exists. Caller must reject status='retired'."""
    return await conn.fetchrow(
        f"""UPDATE public.devices
              SET status='candidate', classified_by=NULL, confirmed_at=NULL, updated_at=now()
            WHERE device_id=$1 RETURNING {_COLS}""",
        device_id,
    )


async def create_candidate(
    conn: asyncpg.Connection, device_id: str, device_type: str | None,
    source_topic: str, gateway_id: str | None = None,
) -> str | None:
    """Insert a new candidate (AI pool). classified_by stays NULL until classified.
    Idempotent via ON CONFLICT DO NOTHING (another worker may have created it)."""
    return await conn.fetchval(
        """INSERT INTO public.devices
               (device_id, device_type, status, gateway_id, metadata, last_seen_at)
           VALUES ($1, $2, 'candidate', $3, jsonb_build_object('source_topic', $4::text), now())
           ON CONFLICT (device_id) DO NOTHING
           RETURNING created_at""",
        device_id, device_type, gateway_id, source_topic,
    )


async def touch_last_seen(conn: asyncpg.Connection, device_id: str) -> None:
    # last_seen_at is not a frozen column -> allowed even on frozen devices (FR-335)
    await conn.execute(
        "UPDATE public.devices SET last_seen_at=now(), updated_at=now() WHERE device_id=$1",
        device_id,
    )


async def apply_outcome(conn: asyncpg.Connection, device_id: str, outcome) -> bool:
    """Apply a classification Outcome under the caller's advisory lock (§8.6.8).
    Re-checks the row is still a non-frozen candidate; writes ai_* + status + digest.
    Returns False if another worker already moved it on / it is frozen."""
    cur = await get(conn, device_id)
    if cur is None or cur["status"] != "candidate" or cur["classified_by"] in FREEZE_SET:
        return False
    res = outcome.result
    await conn.execute(
        """UPDATE public.devices SET
               status=$1, device_type=$2, ai_confidence=$3, ai_provider=$4,
               last_error=$5, classified_by='ai',
               confirmed_at=CASE WHEN $1='confirmed' THEN now() ELSE confirmed_at END,
               updated_at=now()
           WHERE device_id=$6""",
        outcome.new_status, res.device_type, res.confidence,
        outcome.digest.get("ai_provider"), outcome.last_error, device_id,
    )
    await conn.execute(
        """INSERT INTO public.device_review_digests
               (device_id, digest, summary_source, generated_at, provider, model, prompt_version)
           VALUES ($1, $2::jsonb, $3, now(), $4, $5, $6)
           ON CONFLICT (device_id) DO UPDATE SET
               digest=EXCLUDED.digest, summary_source=EXCLUDED.summary_source,
               generated_at=now(), provider=EXCLUDED.provider,
               model=EXCLUDED.model, prompt_version=EXCLUDED.prompt_version""",
        device_id, json.dumps(outcome.digest), outcome.summary_source,
        outcome.digest.get("ai_provider"), outcome.digest.get("ai_model"),
        outcome.digest.get("prompt_version"),
    )
    return True