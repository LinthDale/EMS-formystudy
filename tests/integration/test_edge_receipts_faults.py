"""Short private v2 fault tests; no serial hardware, shared services or long soak."""
import asyncio
from contextlib import asynccontextmanager, contextmanager
import copy
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import threading
import time
from types import SimpleNamespace
from uuid import UUID, uuid4

import asyncpg
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'services/delta'), str(ROOT/'services/edge-receiver')]
import test_edge_receipts_mqtt as base
from delta_device.reliable_sender import ReliableSender
from delta_device.reliable_store import ReliableOutbox
from delta_device.reliable_wire import canonical
from edge_receiver.store import ReceiptStore

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def owned_private_namespace():
    expected = os.environ.get('EMS_V2_DEMO_NETNS')
    if not expected or not os.environ.get('EDGE_V2_TEST_DSN'):
        pytest.skip('requires explicitly provisioned private fault bench')
    assert os.readlink('/proc/self/ns/net') == expected, 'private namespace mismatch'
    assert {p.name for p in Path('/sys/class/net').iterdir()} == {'lo'}, 'external interface present'
    assert os.environ['EDGE_V2_TEST_DSN'] == 'postgresql://postgres@127.0.0.1:5432/ems', 'unexpected database target'


def emit(name, **result):
    directory = os.environ.get('EDGE_V2_EVIDENCE')
    if directory:
        Path(directory, name+'.json').write_text(json.dumps(dict(passed=True, **result), indent=2))


def enqueue(box):
    return box.enqueue(base.source_time(), dict(voltage=230, current=5, power_kw=1, energy_kwh=100))


async def central_counts(store, item):
    async with store.connection() as db:
        receipts = await db.fetchval('SELECT count(*) FROM edge_ingest.receipts WHERE gateway_id=$1 AND sample_id=$2',
                                     item['gateway_id'], UUID(item['sample_id']))
        rows = await db.fetchval('SELECT count(*) FROM electricity_measurements WHERE edge_gateway_id=$1 AND edge_sample_id=$2',
                                 item['gateway_id'], UUID(item['sample_id']))
    return receipts, rows


@contextmanager
def projection_lock(config):
    held, release = threading.Event(), threading.Event()
    errors = []
    async def lock():
        async with ReceiptStore(os.environ[config['dsn_env']]).connection() as db:
            async with db.transaction():
                await db.execute('LOCK TABLE electricity_measurements IN ACCESS EXCLUSIVE MODE')
                held.set()
                assert await asyncio.to_thread(release.wait, 8), 'lock release deadline'
    def run():
        try:
            asyncio.run(lock())
        except Exception as exc:
            errors.append(type(exc).__name__)
            held.set()
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        assert held.wait(4) and not errors, f'private lock failed: {errors}'
        yield
    finally:
        release.set()
        thread.join(5)
        assert not thread.is_alive() and not errors, f'private lock cleanup failed: {errors}'


def test_database_timeout_keeps_source_then_recovers_once(tmp_path):
    box, config, mqtt = base.configured(tmp_path)
    item = enqueue(box)
    with base.running_receiver(config) as receiver, base.running_sender(box, mqtt) as sender:
        retryable = threading.Event()
        observed_results = []
        database_exceptions = []
        original_commit = receiver.store.commit
        async def observe_commit(sample):
            try:
                return await original_commit(sample)
            except Exception as exc:
                database_exceptions.append(type(exc).__name__)
                raise
        receiver.store.commit = observe_commit
        original_publish = receiver.client.publish
        def observe_result(topic, payload, **kwargs):
            if topic.endswith('/acks'):
                result = json.loads(payload)['results'][0]
                observed_results.append(result)
                if result.get('status') == 'retryable' and result.get('error_code') == 'database':
                    retryable.set()
            return original_publish(topic, payload, **kwargs)
        receiver.client.publish = observe_result
        base.establish(sender)
        with projection_lock(config):
            assert not sender.step(threading.Event()), 'locked DB produced committed ACK'
            assert retryable.wait(3), 'only sender ACK timeout observed; database timeout was not proven'
            assert 'TimeoutError' in database_exceptions, 'database retryable did not originate in actual timeout'
            assert box.pending_count() == 1 and box.pending()[0] == item, 'timeout deleted or altered source'
        store = ReceiptStore(os.environ[config['dsn_env']])
        assert asyncio.run(central_counts(store,item)) == (0,0), 'timed-out transaction was not fully rolled back'
        base.deliver(sender, box)
    counts = asyncio.run(central_counts(ReceiptStore(os.environ[config['dsn_env']]), item))
    assert counts == (1, 1) and box.pending_count() == 0, 'DB timeout retry lost or duplicated sample'
    emit('database-timeout', sample_id=item['sample_id'], true_database_retryable_observed=True,
         database_exception_kinds=database_exceptions,
         received_statuses=observed_results, after_failure=[0,0], receipts=counts[0], projections=counts[1], pending_end=0)


def test_terminated_backend_rolls_back_partial_receipt_then_retry_commits_once(tmp_path):
    box, config, _ = base.configured(tmp_path)
    item = enqueue(box)
    store = ReceiptStore(os.environ[config['dsn_env']], timeout=5)
    original_connection, pids = store.connection, []
    @asynccontextmanager
    async def observed_connection():
        async with original_connection() as db:
            pids.append(db.get_server_pid())
            yield db
    store.connection = observed_connection
    async def check():
        task = None
        async with original_connection() as admin:
            transaction = admin.transaction()
            await transaction.start()
            try:
                await admin.execute('LOCK TABLE electricity_measurements IN ACCESS EXCLUSIVE MODE')
                task = asyncio.create_task(store.commit(item))
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    await admin.execute('SELECT pg_stat_clear_snapshot()')
                    if pids:
                        activity = await admin.fetchrow('SELECT wait_event_type,query FROM pg_stat_activity WHERE pid=$1',pids[0])
                        if (activity and activity['wait_event_type']=='Lock'
                                and 'FROM public.electricity_measurements' in activity['query']):
                            break
                    await asyncio.sleep(.01)
                else:
                    pytest.fail('own ingest backend never reached blocked projection')
                assert await admin.fetchval('SELECT pg_terminate_backend($1)', pids[0]), 'own backend was not terminated'
                with pytest.raises((asyncpg.PostgresConnectionError, asyncpg.InterfaceError)):
                    await task
            finally:
                await transaction.rollback()
                if task and not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        assert await central_counts(store, item) == (0, 0), 'partial receipt survived connection termination'
        await store.commit(item)
        assert await central_counts(store, item) == (1, 1), 'retry did not converge after backend death'
    asyncio.run(check())
    assert box.pending_count() == 1, 'DB result alone deleted producer source'
    emit('backend-termination', sample_id=item['sample_id'], terminated_own_backend=pids[0], after_failure=[0,0], after_retry=[1,1], source_still_pending=True)


def test_duplicate_projection_is_rejected_and_source_quarantined_without_deletion(tmp_path):
    box, config, mqtt = base.configured(tmp_path)
    item = enqueue(box)
    store = ReceiptStore(os.environ[config['dsn_env']])
    async def duplicate():
        await store.commit(item)
        async with store.connection() as db:
            await db.execute('''INSERT INTO electricity_measurements
                (time,device_id,voltage,current,power_kw,energy_kwh,edge_gateway_id,edge_sample_id)
                SELECT time,device_id,voltage,current,power_kw,energy_kwh,edge_gateway_id,edge_sample_id
                FROM electricity_measurements WHERE edge_gateway_id=$1 AND edge_sample_id=$2''',
                item['gateway_id'], UUID(item['sample_id']))
    asyncio.run(duplicate())
    with base.running_receiver(config), base.running_sender(box, mqtt) as sender:
        base.establish(sender)
        assert not sender.step(threading.Event()), 'two projections were accepted as committed'
    with box.connect() as db:
        state, payload = db.execute('SELECT state,payload FROM queue WHERE sample_id=?', (item['sample_id'],)).fetchone()
        assert state == 'quarantine' and json.loads(payload) == item, 'rejected source lost evidence'
    counts = asyncio.run(central_counts(store, item))
    assert counts == (1, 2) and box.pending_count() == 1 and not box.pending(), 'conflict was overwritten or hot retried'
    emit('duplicate-projection', sample_id=item['sample_id'], receipts=1, projections_preserved=2, local_state=state, retained_rows=1)


def test_two_live_receivers_commit_same_mqtt_sample_once(tmp_path):
    box, config, mqtt = base.configured(tmp_path)
    item = enqueue(box)
    second = copy.deepcopy(config)
    second['mqtt']['client_id'] += '-b'
    completed = []
    with base.running_receiver(config) as first, base.running_receiver(second) as other, base.running_sender(box, mqtt) as sender:
        first_commit, other_commit = first.store.commit, other.store.commit
        async def record_first(sample):
            stamp = await first_commit(sample)
            completed.append('a')
            return stamp
        async def record_second(sample):
            stamp = await other_commit(sample)
            completed.append('b')
            return stamp
        first.store.commit, other.store.commit = record_first, record_second
        base.deliver(sender, box)
        base.wait_for(lambda: set(completed) == {'a','b'})
    counts = asyncio.run(central_counts(ReceiptStore(os.environ[config['dsn_env']]), item))
    assert counts == (1, 1) and box.pending_count() == 0 and box.audit_count() == 1, 'two receivers duplicated delivery'
    emit('two-live-receivers', sample_id=item['sample_id'], consumers=sorted(set(completed)), receipts=1, projections=1, pending_end=0)


def test_generation_rotation_and_real_old_ack_replay_cannot_delete_pending(tmp_path):
    box, config, mqtt = base.configured(tmp_path)
    item = enqueue(box)
    captured = []
    with base.running_sender(box, mqtt) as sender:
        with base.running_receiver(config) as receiver:
            original_publish = receiver.client.publish
            def lose_ack(topic, payload, **kwargs):
                if topic.endswith('/acks'):
                    captured.append(json.loads(payload))
                    return SimpleNamespace(rc=0)
                return original_publish(topic, payload, **kwargs)
            receiver.client.publish = lose_ack
            base.establish(sender)
            assert not sender.step(threading.Event()), 'dropped ACK removed source'
            assert captured and captured[0]['results'][0]['status'] == 'committed', 'no real committed ACK captured'
        old = captured[0]
        generation = str(uuid4())
        Path(config['generation_file']).write_text(generation)
        with base.running_receiver(config) as restarted:
            base.establish(sender)
            assert sender.state.generation == generation and generation != old['recovery_generation'], 'new generation not established'
            arrived = threading.Event()
            original_callback = sender.client.on_message
            def observe(client, userdata, message):
                original_callback(client, userdata, message)
                if message.topic.endswith('/acks'):
                    arrived.set()
            sender.client.on_message = observe
            restarted.client.publish(sender.prefix+'acks', canonical(old), qos=1, retain=False)
            assert arrived.wait(3), 'old ACK replay was not delivered over real MQTT'
            assert sender.accepted is None and box.pending_count() == 1, 'old-generation/session ACK deleted pending'
            sender.client.on_message = original_callback
            base.deliver(sender, box)
    assert len(base.db_rows(config,item)) == 1 and box.pending_count() == 0, 'new-session retry duplicated projection'
    emit('generation-old-ack', sample_id=item['sample_id'], old_generation=old['recovery_generation'], new_generation=generation,
         old_ack_delivered=True, old_ack_accepted=False, projections=1, pending_end=0, scope='ordinary receiver restart/rotation; not DB PITR')


def test_sqlite_full_retires_oldest_and_preserves_newest_after_reopen(tmp_path):
    identity = dict(gateway_id='g-full',device_id='d1',stream_id=str(uuid4()),config_revision='r1',profile_version='v135')
    box = ReliableOutbox(tmp_path/'full'/'q.db',100,**identity,byte_limit=65536,audit_limit=100)
    expected = []
    start = base.source_time()
    for index in range(20):
        sample = box.enqueue(start+index*1000,dict(voltage=230,current=5,power_kw=1,energy_kwh=100,pad='x'*12000))
        expected.append(sample)
    reopened = ReliableOutbox(box.path,100,**identity,byte_limit=65536,audit_limit=100)
    with reopened.connect() as db:
        actual = [json.loads(r[0]) for r in db.execute('SELECT payload FROM queue ORDER BY capture_seq')]
        metadata = dict(db.execute('SELECT key,value FROM metadata'))
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'disk limit damaged queue'
        assert actual and len(actual)<len(expected) and actual == expected[-len(actual):], 'disk limit failed to retain latest suffix'
        assert int(metadata['sequence']) == len(expected) and int(metadata['latest_timestamp']) == expected[-1]['sampled_at_us']*1000, 'failed transaction advanced metadata'
    assert box.path.stat().st_size <= 65536, 'private DB exceeded configured limit'
    evidence = os.environ.get('EDGE_V2_EVIDENCE')
    if evidence:
        shutil.copyfile(box.path,Path(evidence,'sqlite-full-outbox.db'))
    status=reopened.retention_status()
    assert status['unconfirmed_evicted_total']==len(expected)-len(actual), 'byte retirement count wrong'
    emit('sqlite-full', enqueued=len(expected), retained_after_reopen=len(actual), integrity='ok',
         database_bytes=box.path.stat().st_size, retention=status, retained_ids=[s['sample_id'] for s in actual])


def test_audit_capacity_after_ack_recycles_oldest_and_accepts_new_sample(tmp_path):
    identity = dict(gateway_id='g-audit',device_id='d1',stream_id=str(uuid4()),config_revision='r1',profile_version='v135')
    box = ReliableOutbox(tmp_path/'audit'/'q.db',10,**identity,audit_limit=1)
    item = enqueue(box)
    box.committed(item['sample_id'],item['payload_hash'])
    new=enqueue(box)
    with box.connect() as db:
        assert db.execute("SELECT value FROM metadata WHERE key='sequence'").fetchone()[0] == '2', 'audit full blocked new sequence'
    assert box.pending() == [new] and box.audit_count() == 1, 'audit cap failed to retain newest'
    status=box.retention_status()
    assert status['committed_audit_evicted_total']==1 and status['unconfirmed_evicted_total']==0, 'audit retirement mislabeled delivery loss'
    emit('audit-capacity', retained_audit_rows=1,new_sample_accepted=True,sequence=2,retention=status)


def test_untrusted_client_certificate_rejected_by_real_mtls_broker_and_keeps_queue(tmp_path):
    box, config, mqtt = base.configured(tmp_path,gateway='qa-edge')
    item = enqueue(box)
    pki = Path(os.environ['EDGE_V2_TEST_PKI'])
    mqtt.update(port=8886,tls=True,ca_file=str(pki/'ca.crt'),cert_file=str(pki/'client.crt'),key_file=str(pki/'client.key'))
    with base.running_sender(box,mqtt,mode='field'):
        pass  # Positive control: same listener/CA accepts commissioned client.
    mqtt.update(cert_file=str(pki/'rogue-client.crt'),key_file=str(pki/'rogue-client.key'))
    sender = ReliableSender(box,mqtt,'field',ack_timeout=1)
    rejected = threading.Event()
    original_disconnect = sender.client.on_disconnect
    def disconnected(client,userdata,flags,reason,properties):
        original_disconnect(client,userdata,flags,reason,properties)
        if reason != 0:
            rejected.set()
    sender.client.on_disconnect = disconnected
    sender.client.on_connect_fail = lambda *_: rejected.set()
    sender.start()
    try:
        assert rejected.wait(4), 'untrusted client did not reach observable TLS rejection'
        assert not sender.subscribed.is_set() and not sender.session_ready.is_set(), 'untrusted client established MQTT session'
        assert box.pending_count() == 1 and box.pending()[0] == item and not base.db_rows(config,item), 'TLS failure lost source or reached DB'
    finally:
        sender.close()
    emit('untrusted-mtls', sample_id=item['sample_id'], valid_client_positive_control=True, rogue_client_rejected=True,pending=1,projections=0)
