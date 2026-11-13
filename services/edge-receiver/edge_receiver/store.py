"""One transaction owns receipt, projection, dedup and missing-row repair."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
from uuid import UUID

import asyncpg

from delta_device.reliable_wire import FIELDS, canonical, validate_sample


class Conflict(ValueError):
    """Immutable identity or projection conflicts; never overwrite evidence."""


class OutsideWindow(ValueError):
    """Source time lies outside the bounded replay window."""


class ReceiptStore:
    def __init__(self, dsn, timeout=5, standby_name=None, tls=None):
        self.dsn, self.timeout = dsn, timeout
        self.standby_name = standby_name
        self.tls = tls

    async def require_wal(self, db, lsn=None):
        if self.standby_name is not None:
            if await db.fetchval('SELECT edge_ingest.sync_tls_wal_flushed($1,$2::text::pg_lsn)',
                                 self.standby_name, lsn) is not True:
                raise ValueError('synchronous WAL durability unavailable')

    @asynccontextmanager
    async def connection(self):
        options={} if self.tls is None else dict(ssl=self.tls)
        db = await asyncpg.connect(self.dsn, timeout=self.timeout, command_timeout=self.timeout, **options)
        try:
            if await db.fetchval('SHOW fsync') != 'on' or await db.fetchval('SHOW synchronous_commit') != 'on':
                raise ValueError('database persistence prerequisites')
            await self.require_wal(db)
            yield db
        finally:
            await db.close(timeout=self.timeout)

    async def commit(self, sample):
        sample = validate_sample(sample, sample['gateway_id'])
        gateway, sid = sample['gateway_id'], UUID(sample['sample_id'])
        try:
            async with self.connection() as db:
                async with db.transaction(isolation='read_committed'):
                    await db.execute('SET LOCAL synchronous_commit=on')
                    now = await db.fetchval('SELECT clock_timestamp()')
                    now_us = int((now - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds() * 1000000)
                    if not now_us - 90 * 86400 * 1000000 <= sample['sampled_at_us'] <= now_us + 120 * 1000000:
                        raise OutsideWindow('outside_window')
                    sampled = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=sample['sampled_at_us'])
                    retention = max(now, sampled) + timedelta(days=91)
                    await db.execute('''INSERT INTO edge_ingest.receipts
                        (gateway_id,sample_id,device_id,stream_id,capture_seq,window_id,config_revision,
                         payload_hash,sampled_at_us,retention_until,sample)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb)
                        ON CONFLICT DO NOTHING''',
                        gateway, sid, sample['device_id'], UUID(sample['stream_id']), sample['capture_seq'],
                        UUID(sample['window_id']), sample['config_revision'], sample['payload_hash'],
                        sample['sampled_at_us'], retention, canonical(sample).decode())
                    receipt = await db.fetchrow('''SELECT payload_hash,sample,committed_at
                        FROM edge_ingest.receipts WHERE gateway_id=$1 AND sample_id=$2 FOR UPDATE''', gateway, sid)
                    if not receipt or receipt['payload_hash'] != sample['payload_hash'] or json.loads(receipt['sample']) != sample:
                        raise Conflict('conflict')
                    # Re-read projection AFTER receipt lock; all writers/repair share this lock.
                    rows = await db.fetch('''SELECT time,device_id,voltage,current,power_kw,energy_kwh
                        FROM public.electricity_measurements WHERE edge_gateway_id=$1 AND edge_sample_id=$2
                        ORDER BY time LIMIT 2''', gateway, sid)
                    if len(rows) > 1:
                        raise Conflict('conflict')
                    if rows:
                        row = rows[0]
                        if (row['time'] != sampled or row['device_id'] != sample['device_id']
                                or any(row[k] != sample['measurements'][k] for k in FIELDS)):
                            raise Conflict('conflict')
                    else:
                        await db.execute('''INSERT INTO public.electricity_measurements
                            (time,device_id,voltage,current,power_kw,energy_kwh,edge_gateway_id,edge_sample_id)
                            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)''', sampled, sample['device_id'],
                            *(sample['measurements'][k] for k in FIELDS), gateway, sid)
                    committed_at = receipt['committed_at'].isoformat()
                # This line is reachable only after asyncpg's transaction COMMIT returned.
                if self.standby_name is not None:
                    lsn = await db.fetchval('SELECT pg_current_wal_flush_lsn()::text')
                    await self.require_wal(db, lsn)
                return committed_at
        except asyncpg.UniqueViolationError as exc:
            raise Conflict('conflict') from exc
