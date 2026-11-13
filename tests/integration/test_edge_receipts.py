"""FR-2106: private real PostgreSQL receipt/projection transaction and dedup."""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from uuid import uuid4
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'services/delta'), str(ROOT / 'services/edge-receiver')]
from delta_device.reliable_store import ReliableOutbox
from delta_device.reliable_wire import sample_hash
from edge_receiver.store import ReceiptStore, Conflict, OutsideWindow

pytestmark = pytest.mark.integration


def run(coro):
    return asyncio.run(coro)


def configured(tmp_path):
    dsn = os.environ.get('EDGE_V2_TEST_DSN')
    if not dsn:
        pytest.skip('requires explicitly provisioned private v2 DB')
    box = ReliableOutbox(tmp_path / 'q' / 'queue.db', 100, 'g-' + uuid4().hex[:10],
                         'd1', str(uuid4()), 'r1', 'delta-v135')
    item = box.enqueue(int(datetime.now(timezone.utc).timestamp() * 1e6) * 1000,
                       dict(voltage=230, current=5, power_kw=1, energy_kwh=100))
    return ReceiptStore(dsn), box, item


async def counts(store, item):
    async with store.connection() as db:
        args = (item['gateway_id'], item['sample_id'])
        receipt = await db.fetchval('SELECT count(*) FROM edge_ingest.receipts WHERE gateway_id=$1 AND sample_id=$2::uuid', *args)
        rows = await db.fetch('SELECT * FROM electricity_measurements WHERE edge_gateway_id=$1 AND edge_sample_id=$2::uuid', *args)
    return receipt, rows


def test_identical_retry_and_parallel_receivers_insert_once(tmp_path):
    store, box, item = configured(tmp_path)
    async def check():
        results = await asyncio.gather(*(store.commit(item) for _ in range(6)))
        receipt, rows = await counts(store, item)
        assert len(results) == 6 and receipt == len(rows) == 1, 'parallel resend duplicated projection'
        assert rows[0]['voltage'] == 230 and rows[0]['device_id'] == 'd1', 'projection content differs'
    run(check())
    assert box.pending_count() == 1, 'central commit without application ACK deleted producer row'


def test_same_id_changed_content_and_same_sequence_changed_id_are_conflicts(tmp_path):
    store, _, item = configured(tmp_path)
    async def check():
        await store.commit(item)
        bad = json.loads(json.dumps(item))
        bad['measurements']['voltage'] = 240.0
        bad['payload_hash'] = sample_hash(bad)
        with pytest.raises(Conflict):
            await store.commit(bad)
        bad = dict(item, sample_id=str(uuid4()))
        bad['payload_hash'] = sample_hash(bad)
        with pytest.raises(Conflict):
            await store.commit(bad)
        receipt, rows = await counts(store, item)
        assert receipt == len(rows) == 1 and rows[0]['voltage'] == 230, 'conflict altered original'
    run(check())


def test_missing_projection_parallel_repair_inserts_once_and_bad_projection_rejected(tmp_path):
    store, _, item = configured(tmp_path)
    async def check():
        await store.commit(item)
        async with store.connection() as db:
            await db.execute('DELETE FROM electricity_measurements WHERE edge_gateway_id=$1', item['gateway_id'])
        await asyncio.gather(*(store.commit(item) for _ in range(6)))
        receipt, rows = await counts(store, item)
        assert receipt == len(rows) == 1, 'parallel repair duplicated'
        async with store.connection() as db:
            await db.execute('UPDATE electricity_measurements SET voltage=240 WHERE edge_gateway_id=$1', item['gateway_id'])
        with pytest.raises(Conflict):
            await store.commit(item)
        assert (await counts(store, item))[1][0]['voltage'] == 240, 'conflict silently overwritten'
    run(check())


def test_partial_database_failure_rolls_back_receipt_and_retries_original(tmp_path):
    store, _, item = configured(tmp_path)
    async def check():
        async with store.connection() as db:
            await db.execute('ALTER TABLE electricity_measurements ADD CONSTRAINT qa_reject_voltage CHECK (voltage <> 98765) NOT VALID')
        bad = json.loads(json.dumps(item))
        bad['measurements']['voltage'] = 98765.0
        bad['payload_hash'] = sample_hash(bad)
        try:
            import asyncpg
            with pytest.raises(asyncpg.CheckViolationError):
                await store.commit(bad)
            receipt, rows = await counts(store, bad)
            assert receipt == len(rows) == 0, 'partial transaction survived projection failure'
        finally:
            async with store.connection() as db:
                await db.execute('ALTER TABLE electricity_measurements DROP CONSTRAINT qa_reject_voltage')
        await store.commit(item)
        assert (await counts(store, item))[0] == 1, 'original retry failed after rollback'
    run(check())


def test_same_timestamp_different_sample_identity_both_survive(tmp_path):
    store, _, item = configured(tmp_path)
    other = dict(item, sample_id=str(uuid4()), capture_seq=item['capture_seq'] + 1)
    other['payload_hash'] = sample_hash(other)
    async def check():
        await store.commit(item)
        await store.commit(other)
        assert len((await counts(store, item))[1]) == len((await counts(store, other))[1]) == 1, 'timestamp used as identity'
    run(check())


@pytest.mark.parametrize('delta_us', [-91 * 86400 * 1000000, 121 * 1000000])
def test_timestamp_outside_database_utc_window_is_rejected(tmp_path, delta_us):
    store, _, item = configured(tmp_path)
    item['sampled_at_us'] += delta_us
    item['payload_hash'] = sample_hash(item)
    with pytest.raises(OutsideWindow):
        run(store.commit(item))


def test_migration_twice_legacy_projection_and_least_privilege_receiver(tmp_path):
    store, _, item = configured(tmp_path)
    async def check():
        migration = (ROOT / 'infra/timescaledb/migrations/019_edge_committed_receipts.sql').read_text()
        async with store.connection() as db:
            await db.execute(migration)
            await db.execute(migration)
            assert not await db.fetchval("SELECT has_table_privilege('web_anon','edge_ingest.receipts','SELECT')"), 'receipt exposed to public query role'
            cols = await db.fetch("SELECT column_name FROM information_schema.columns WHERE table_schema='api' AND table_name='electricity_measurements'")
            assert {r[0] for r in cols} == {'time','device_id','voltage','current','power_kw','energy_kwh'}, 'legacy API view changed'
            await db.execute('CREATE ROLE qa_receiver LOGIN IN ROLE ems_edge_receiver')
            await db.execute('CREATE ROLE qa_nondurable LOGIN IN ROLE ems_edge_receiver')
            await db.execute("ALTER ROLE qa_nondurable SET synchronous_commit='off'")
        limited = ReceiptStore(store.dsn.replace('postgres@', 'qa_receiver@'))
        await limited.commit(item)
        assert (await counts(store, item))[0] == 1, 'least-privilege role cannot commit'
        async with limited.connection() as db:
            import asyncpg
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await db.execute('DELETE FROM electricity_measurements WHERE edge_gateway_id=$1', item['gateway_id'])
        unsafe = ReceiptStore(store.dsn.replace('postgres@', 'qa_nondurable@'))
        with pytest.raises(ValueError, match='persistence'):
            async with unsafe.connection():
                pass
    run(check())
