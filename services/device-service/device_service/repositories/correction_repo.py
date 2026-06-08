"""device_corrections data access (human feedback, PRD-0003 Phase 1.4)."""
from __future__ import annotations

import json
from datetime import datetime

import asyncpg

_COL_NAMES = (
    "id", "device_id", "verdict", "corrected_device_type", "corrected_signals",
    "human_explanation", "created_at", "created_by_key_id", "salt_version",
    "prompt_version_at_correction", "applied_count", "last_applied_at", "is_active",
    "deactivated_at", "deactivation_reason",
)
_COLS = ", ".join(_COL_NAMES)
# dc-qualified form for joins against devices (which also has device_id) — avoids ambiguity
_DC_COLS = ", ".join(f"dc.{c}" for c in _COL_NAMES)


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


async def retrieve_relevant(
    conn: asyncpg.Connection, *, device_id: str, gateway_id: str | None,
    device_type_family: tuple[str, ...], topic_prefix: str,
) -> list[dict]:
    """Active corrections relevant to a device being classified (PRD §8.6.4, FR-331).

    Union of: (1) same device, (2) same gateway (resolved via the correction's own
    device row, since device_corrections has no gateway column), (3) corrected_device_type
    in the device-type family, (4) same topic prefix (first two `/`-segments of the
    correction device's source_topic). No count limit here — the 32KB prompt cap
    (§8.6.5a) is applied by the caller. Ordered most-recently-applied first so the cap
    keeps the freshest feedback."""
    rows = await conn.fetch(
        f"""SELECT {_DC_COLS}
            FROM public.device_corrections dc
            JOIN public.devices d ON d.device_id = dc.device_id
            WHERE dc.is_active
              AND (
                dc.device_id = $1
                OR ($2::text IS NOT NULL AND d.gateway_id = $2)
                OR dc.corrected_device_type = ANY($3::text[])
                OR ( $4 <> '' AND
                     split_part(d.metadata->>'source_topic', '/', 1) || '/' ||
                     split_part(d.metadata->>'source_topic', '/', 2) = $4 )
              )
            ORDER BY dc.last_applied_at DESC NULLS LAST, dc.created_at DESC, dc.id DESC""",
        device_id, gateway_id, list(device_type_family), topic_prefix,
    )
    return [_shape(r) for r in rows]  # type: ignore[misc]


async def latest_corrected_device_type(
    conn: asyncpg.Connection, *, device_id: str, gateway_id: str | None,
) -> str | None:
    """Latest active correction's corrected_device_type for FR-332 conflict detection:
    prefer the device's own latest, else fall back to the latest on the same gateway."""
    val = await conn.fetchval(
        """SELECT corrected_device_type FROM public.device_corrections
           WHERE is_active AND corrected_device_type IS NOT NULL AND device_id = $1
           ORDER BY created_at DESC, id DESC LIMIT 1""",
        device_id,
    )
    if val is not None or gateway_id is None:
        return val
    return await conn.fetchval(
        """SELECT dc.corrected_device_type FROM public.device_corrections dc
           JOIN public.devices d ON d.device_id = dc.device_id
           WHERE dc.is_active AND dc.corrected_device_type IS NOT NULL AND d.gateway_id = $1
           ORDER BY dc.created_at DESC, dc.id DESC LIMIT 1""",
        gateway_id,
    )


async def mark_applied(conn: asyncpg.Connection, ids: list[int]) -> None:
    """Atomically bump applied_count + last_applied_at for the corrections actually
    injected into a prompt (§7.3a applied_count). No-op on an empty list."""
    if not ids:
        return
    await conn.execute(
        """UPDATE public.device_corrections
           SET applied_count = applied_count + 1, last_applied_at = now()
           WHERE id = ANY($1::bigint[])""",
        [int(i) for i in ids],  # explicit coercion -> clear contract, no opaque asyncpg cast error
    )
