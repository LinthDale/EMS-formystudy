"""Database access — two asyncpg pools, one per DB role (ADR-017).

AI pool (device_service_ai): MQTT/classification path, writes ai_* + digests.
OPS pool (device_service_ops): CRUD / confirm / override / reject; mutating a frozen
record requires SET LOCAL device_service.freeze_override (migration 010/011).

Note: ops_tx GUC + advisory lock are transaction-scoped — requires direct asyncpg
pooling or a session-mode external pooler (PgBouncer transaction/statement mode
would break them; see ADR-017).
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import asyncpg


class Database:
    def __init__(self, *, host: str, port: int, name: str, ai_password: str, ops_password: str):
        self._common = dict(host=host, port=port, database=name)
        self._ai_password = ai_password
        self._ops_password = ops_password
        self.ai_pool: asyncpg.Pool | None = None
        self.ops_pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.ai_pool = await asyncpg.create_pool(
            user="device_service_ai", password=self._ai_password,
            min_size=1, max_size=10, **self._common,
        )
        self.ops_pool = await asyncpg.create_pool(
            user="device_service_ops", password=self._ops_password,
            min_size=1, max_size=5, **self._common,
        )

    async def close(self) -> None:
        for pool in (self.ai_pool, self.ops_pool):
            if pool is not None:
                await pool.close()

    async def healthz(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for name, pool in (("ai", self.ai_pool), ("ops", self.ops_pool)):
            if pool is None:
                out[name] = "starting"
                continue
            try:
                async with pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                out[name] = "ok"
            except Exception:
                out[name] = "down"
        return out

    @asynccontextmanager
    async def ops_tx(self, *, freeze_override: str | None = None, lock: str | None = None):
        """OPS transaction.

        lock: if given, take a transaction-scoped advisory lock keyed on it (serialises
              concurrent lifecycle mutations of the same device vs the AI auto-confirm
              path, §8.6.8 / W-A).
        freeze_override: if given (a request id), set the GUC token so the freeze trigger
              lets a legitimate confirm/override/reject mutate a frozen row.
        """
        async with self.ops_pool.acquire() as conn:  # type: ignore[union-attr]
            async with conn.transaction():
                if lock:
                    await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", lock)
                if freeze_override:
                    await conn.execute(
                        "SELECT set_config('device_service.freeze_override', $1, true)",
                        freeze_override,
                    )
                yield conn

    @asynccontextmanager
    async def ai_tx(self, *, lock: str | None = None):
        """AI-pool transaction (device_service_ai). Never sets a freeze override — the
        AI role can only mutate non-frozen rows (candidate -> confirmed); the DB trigger
        blocks frozen rows. Optional advisory lock serialises per-device classification."""
        async with self.ai_pool.acquire() as conn:  # type: ignore[union-attr]
            async with conn.transaction():
                if lock:
                    await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", lock)
                yield conn