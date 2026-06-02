"""Raw measurement sample access for on-demand reclassification (PRD-0003 §234 / §761).

Read ONLY, via the OPS pool: migration 010 grants SELECT on the measurement hypertables
to device_service_ops but NOT device_service_ai (the AI role never reads raw measurements).
Returns the most recent <=N rows for a device as field dicts the sanitizer can summarise
(time / device_id / device_type tags excluded; NULLs dropped).
"""
from __future__ import annotations

import asyncpg

# table -> field columns to sample (fixed allowlist; never interpolate user input as a table
# or column name). Tags (time/device_id/device_type) are intentionally excluded.
_TABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "electricity_measurements": ("voltage", "current", "power_kw", "energy_kwh"),
    "factory_measurements": ("temperature", "humidity", "motor_speed", "pump_on", "valve_open", "pressure"),
}
MAX_SAMPLES = 20  # §761: classification takes the most recent <= 20 raw messages


def table_for_gateway(gateway_id: str | None) -> str | None:
    """Map a device's gateway to its measurement hypertable. None if unknown (cannot reclassify
    — no known sample source)."""
    if gateway_id == "ems-gateway":
        return "electricity_measurements"
    if gateway_id in ("kc-gateway", "kc-ingest"):
        return "factory_measurements"
    return None


async def recent_samples(
    conn: asyncpg.Connection, *, table: str, device_id: str, limit: int = MAX_SAMPLES,
) -> list[dict]:
    """Most recent <= limit rows for device_id from an allowlisted measurement table, as
    field dicts (NULL columns dropped). Raises ValueError on an unknown table."""
    fields = _TABLE_FIELDS.get(table)
    if fields is None:
        raise ValueError(f"unknown measurement table {table!r}")
    cols = ", ".join(fields)  # fixed identifiers from the allowlist, not user input
    rows = await conn.fetch(
        f"SELECT {cols} FROM public.{table} WHERE device_id = $1 ORDER BY time DESC LIMIT $2",
        device_id, min(int(limit), MAX_SAMPLES),
    )
    return [{c: r[c] for c in fields if r[c] is not None} for r in rows]
