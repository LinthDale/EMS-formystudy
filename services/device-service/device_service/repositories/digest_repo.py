"""Review-digest read access (device_review_digests, PRD-0003 §8.4).

Read-only: the digest is written on the classification path (device_repo.apply_outcome).
JSONB comes back as text (no asyncpg codec registered) -> parsed here.
"""
from __future__ import annotations

import json

import asyncpg

_FIELDS = ("device_id", "digest", "summary_source", "generated_at", "provider", "model", "prompt_version")
_COLS = ", ".join(_FIELDS)
# qualified form for the JOIN: devices also has `model` (and others), so digest columns
# must be table-qualified to avoid AmbiguousColumnError.
_DR_COLS = ", ".join(f"dr.{c}" for c in _FIELDS)


def _shape(row: asyncpg.Record) -> dict:
    digest = row["digest"]
    if isinstance(digest, str):  # asyncpg returns JSONB as text without a codec
        digest = json.loads(digest)
    return {
        "device_id": row["device_id"],
        "digest": digest,
        "summary_source": row["summary_source"],
        "generated_at": row["generated_at"],
        "provider": row["provider"],
        "model": row["model"],
        "prompt_version": row["prompt_version"],
    }


async def get(conn: asyncpg.Connection, device_id: str) -> dict | None:
    """Digest-only read (no device existence check). Used where the caller already
    knows the device exists (e.g. the MCP get_device_digest tool)."""
    row = await conn.fetchrow(
        f"SELECT {_COLS} FROM public.device_review_digests WHERE device_id=$1", device_id
    )
    return _shape(row) if row is not None else None


async def list_low_confidence(
    conn: asyncpg.Connection, *, threshold: float = 0.9, limit: int = 20,
) -> list[dict]:
    """Digests of CANDIDATE devices with ai_confidence <= threshold (MCP
    list_low_confidence_candidates, §8.2). Lowest-confidence first. Joins devices (status +
    ai_confidence) to device_review_digests; only devices that already have a digest appear."""
    rows = await conn.fetch(
        f"""SELECT {_DR_COLS}
            FROM public.devices d
            JOIN public.device_review_digests dr ON dr.device_id = d.device_id
            WHERE d.status = 'candidate' AND d.ai_confidence IS NOT NULL AND d.ai_confidence <= $1
            ORDER BY d.ai_confidence ASC, d.device_id
            LIMIT $2""",
        threshold, max(1, min(int(limit), 200)),
    )
    return [_shape(r) for r in rows]  # type: ignore[misc]


async def get_with_device(conn: asyncpg.Connection, device_id: str) -> tuple[bool, dict | None]:
    """Atomic (device_exists, digest_or_None) in one round-trip via LEFT JOIN, so a
    concurrent delete cannot split the existence check from the digest fetch.
    Returns (False, None) unknown device; (True, None) device without a digest yet."""
    row = await conn.fetchrow(
        f"""SELECT {_DR_COLS}
            FROM public.devices d
            LEFT JOIN public.device_review_digests dr ON dr.device_id = d.device_id
            WHERE d.device_id = $1""",
        device_id,
    )
    if row is None:
        return (False, None)
    if row["digest"] is None:  # device exists, no digest row joined
        return (True, None)
    return (True, _shape(row))
