"""Short actual logical restore, bounded overload, and backlog/live delivery."""
import asyncio
import copy
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from uuid import UUID,uuid4

import paho.mqtt.client as mqtt_client
import pytest

import test_edge_receipts_mqtt as base
from test_edge_receipts_faults import projection_lock
from delta_device.reliable_store import ReliableOutbox
from delta_device.reliable_wire import canonical
from edge_receiver.store import ReceiptStore

pytestmark=pytest.mark.integration
VALUES=dict(voltage=230,current=5,power_kw=1,energy_kwh=100)


@pytest.fixture(autouse=True)
def private_gate():
    expected=os.environ.get('EMS_V2_DEMO_NETNS')
    if not expected or os.environ.get('EDGE_V2_RESTORE_LOAD')!='1':
        pytest.skip('requires explicitly provisioned private restore/load bench')
    assert os.readlink('/proc/self/ns/net')==expected and {p.name for p in Path('/sys/class/net').iterdir()}=={'lo'}, 'wrong private namespace'
    assert os.environ.get('EDGE_V2_TEST_DSN')=='postgresql://postgres@127.0.0.1:5432/ems', 'unexpected source DB'
    assert os.environ.get('EDGE_V2_RESTORED_DSN')=='postgresql://postgres@127.0.0.1:5432/ems_restore', 'unexpected restored DB'


def emit(name,**result):
    Path(os.environ['EDGE_V2_EVIDENCE'],name+'.json').write_text(json.dumps(dict(passed=True,**result),indent=2))


def control(op):
    directory=Path(os.environ['EDGE_V2_EVIDENCE']);token=str(uuid4())
    request=directory/('control-'+token+'.request.json');temporary=request.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(request_id=token,op=op)));os.replace(temporary,request)
    response=directory/('control-'+token+'.response.json')
    base.wait_for(response.exists,seconds=45)
    result=json.loads(response.read_text())
    assert result.get('passed') is True and result.get('request_id')==token and result.get('op')==op, 'private DB control failed'
    return result


def stored_identity(config,sample):
    async def read():
        async with ReceiptStore(os.environ[config['dsn_env']]).connection() as db:
            receipt=await db.fetchrow('SELECT payload_hash,sample,committed_at,retention_until FROM edge_ingest.receipts WHERE gateway_id=$1 AND sample_id=$2',
                                     sample['gateway_id'],UUID(sample['sample_id']))
        if not receipt:return None
        return dict(payload_hash=receipt['payload_hash'],sample=json.loads(receipt['sample']),
            committed_at=receipt['committed_at'].isoformat(),retention_until=receipt['retention_until'].isoformat())
    receipt=asyncio.run(read())
    if receipt is not None:
        receipt['projection']=[{k:(v.isoformat() if hasattr(v,'isoformat') else v) for k,v in row.items()}
                               for row in base.db_rows(config,sample)]
    return receipt


def test_real_database_backup_restore_new_generation_recovers_pending_and_exposes_acked_loss(tmp_path):
    box,config,mqtt=base.configured(tmp_path)
    before_backup=box.enqueue(base.source_time(),VALUES)
    captured=[]
    with base.running_receiver(config) as receiver,base.running_sender(box,mqtt) as sender:
        base.deliver(sender,box)
        backup=control('db_backup')
        acked_after_backup=box.enqueue(base.source_time(),dict(VALUES,voltage=231))
        base.deliver(sender,box)
        pending=box.enqueue(base.source_time(),dict(VALUES,voltage=232))
        publish=receiver.client.publish
        def drop_ack(topic,payload,**kwargs):
            if topic.endswith('/acks'):
                captured.append(json.loads(payload));return SimpleNamespace(rc=0)
            return publish(topic,payload,**kwargs)
        receiver.client.publish=drop_ack
        # Preserve sender/receiver pacing: forcing next_send=0 here would hit
        # the real batch limiter rather than the intended commit/lost-ACK window.
        base.wait_for(lambda:bool(captured) or (sender.step(threading.Event()) and bool(captured)),seconds=8)
        assert captured and captured[-1]['results'][0]['status']=='committed', 'postbackup sample never committed'
        assert box.pending()==[pending] and len(base.db_rows(config,pending))==1, 'lost-ACK source window missing'
    old_ack=captured[-1]
    source_before=[stored_identity(config,s) for s in (before_backup,acked_after_backup,pending)]
    restored=control('db_restore')
    target=copy.deepcopy(config);target['dsn_env']='EDGE_V2_RESTORED_DSN'
    old_generation=Path(config['generation_file']).read_text()
    new_generation=str(uuid4());Path(config['generation_file']).write_text(new_generation)
    restored_counts=[len(base.db_rows(target,s)) for s in [before_backup,acked_after_backup,pending]]
    assert restored_counts==[1,0,0], 'restore did not actually roll back to the earlier dump'
    assert stored_identity(target,before_backup)==source_before[0], 'backup restore changed canonical identity/hash/receipt timestamps or projection'
    assert [stored_identity(config,s) for s in (before_backup,acked_after_backup,pending)]==source_before, 'restore modified original receipt or projection'
    with base.running_receiver(target),base.running_sender(box,mqtt) as sender:
        base.establish(sender)
        assert sender.state.generation==new_generation!=old_generation, 'generation was restored with the DB'
        delivered_old=threading.Event();callback=sender.client.on_message
        def observe(client,userdata,message):
            callback(client,userdata,message)
            if message.topic==sender.prefix+'acks' and json.loads(message.payload)==old_ack:delivered_old.set()
        sender.client.on_message=observe
        sender.client.publish(sender.prefix+'acks',canonical(old_ack),qos=1,retain=False)
        assert delivered_old.wait(3), 'real old ACK replay was not observed'
        assert sender.accepted is None and box.pending()==[pending], 'old pre-restore ACK deleted pending'
        sender.client.on_message=callback
        base.deliver(sender,box)
        fresh=box.enqueue(base.source_time(),dict(VALUES,voltage=233));base.deliver(sender,box)
    assert [len(base.db_rows(target,s)) for s in [before_backup,acked_after_backup,pending,fresh]]==[1,0,1,1], 'restored DB recovery lost or duplicated data'
    recovered=stored_identity(target,pending)
    assert recovered['sample']==pending and recovered['projection']==source_before[2]['projection'], 'pending recovery altered original hash/source time/values'
    # The ACKed source payload was legitimately removed before the restore;
    # audit still identifies the loss, but it cannot regenerate the payload.
    with box.connect() as db:
        assert db.execute('SELECT state FROM audit WHERE sample_id=?',(acked_after_backup['sample_id'],)).fetchone()[0]=='committed', 'lost-after-backup audit evidence missing'
        assert db.execute('SELECT COUNT(*) FROM queue WHERE sample_id=?',(acked_after_backup['sample_id'],)).fetchone()[0]==0, 'test did not exercise loss of both available payload copies'
    emit('database-restore',backup=backup,restore=restored,old_generation=old_generation,new_generation=new_generation,
         original_db_preserved=True,restored_counts_before_replay=restored_counts,
         backup_identity_and_projection_matched=True,recovered_original_identity_and_projection_matched=True,
         old_ack_replayed=True,old_ack_accepted=False,pending_original_id=pending['sample_id'],
         recovered_pending_rows=1,fresh_rows=1,pending_end=0,
         unrecoverable_acked_after_backup=[acked_after_backup['sample_id']],
         scope='logical restore from dump+local only; source DB retained solely as test oracle, not WAL PITR/RPO/RTO acceptance')


def test_real_mqtt_burst_fills_bounded_receiver_queue_then_recovers_original_once(tmp_path):
    box,config,mqtt=base.configured(tmp_path);config['db_timeout_seconds']=5
    item=box.enqueue(base.source_time(),VALUES)
    metrics=dict(messages=0,dropped=0,peak=0,rate_denied=0);committed=[]
    connected=threading.Event()
    burst=mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2,client_id='burst-'+uuid4().hex[:12])
    burst.on_connect=lambda *args:connected.set()
    burst.connect_async('127.0.0.1',1883,30);burst.loop_start()
    try:
        assert connected.wait(4), 'burst publisher did not connect'
        with base.running_receiver(config) as receiver,base.running_sender(box,mqtt) as sender:
            base.establish(sender)
            callback=receiver.client.on_message;rate=receiver.rate_allowed;publish=receiver.client.publish
            def observe(client,userdata,message):
                full=receiver.incoming.full();callback(client,userdata,message)
                metrics['messages']+=1;metrics['dropped']+=int(full);metrics['peak']=max(metrics['peak'],receiver.incoming.qsize())
            def observe_rate(*args):
                allowed=rate(*args);metrics['rate_denied']+=int(not allowed);return allowed
            def observe_ack(topic,payload,**kwargs):
                if topic.endswith('/acks'):
                    committed.extend(r for r in json.loads(payload)['results'] if r['status']=='committed')
                return publish(topic,payload,**kwargs)
            receiver.client.on_message=observe;receiver.rate_allowed=observe_rate;receiver.client.publish=observe_ack
            with sender.lock:envelope=sender.state.prepare(item)
            with projection_lock(config):
                burst.publish(sender.prefix+'samples',canonical(envelope),qos=1).wait_for_publish(timeout=3)
                async def blocked():
                    async with ReceiptStore(os.environ[config['dsn_env']]).connection() as db:
                        return await db.fetchval("SELECT count(*) FROM pg_stat_activity WHERE pid<>pg_backend_pid() AND wait_event_type='Lock' AND query LIKE '%FROM public.electricity_measurements%'")
                base.wait_for(lambda:asyncio.run(blocked())>0,seconds=3)
                infos=[burst.publish(sender.prefix+'samples',canonical(envelope),qos=1) for _ in range(199)]
                for info in infos:
                    assert info.rc==0, 'burst was dropped at publisher instead of receiver'
                    info.wait_for_publish(timeout=3)
                base.wait_for(lambda:metrics['messages']==200,seconds=3)
                assert metrics['peak']==receiver.incoming.maxsize==64 and metrics['dropped']>0, 'real input burst did not reach the receiver capacity limit'
                assert not committed and box.pending()==[item], 'blocked/overflow receiver falsely confirmed delivery'
                burst_counts={key:metrics[key] for key in ('messages','dropped','peak')}
            base.wait_for(receiver.incoming.empty,seconds=7)
            base.wait_for(lambda:bool(committed),seconds=5)
            assert metrics['rate_denied']>0 and receiver.ready.is_set(), 'no actual rate overload or receiver crashed'
            base.deliver(sender,box,seconds=12)
            fresh=box.enqueue(base.source_time(),dict(VALUES,voltage=231));base.deliver(sender,box)
        assert len(base.db_rows(config,item))==len(base.db_rows(config,fresh))==1 and box.pending_count()==0, 'overload recovery lost or duplicated source'
    finally:burst.disconnect();burst.loop_stop()
    emit('receiver-overload',mqtt_messages=200,unique_source_samples=1,**burst_counts,
         total_messages_including_recovery=metrics['messages'],rate_denied=metrics['rate_denied'],
         receiver_capacity=64,actual_db_lock_observed=True,no_committed_ack_while_locked=True,
         original_sample_id=item['sample_id'],original_rows=1,fresh_rows=1,pending_end=0)


def test_thousand_old_samples_do_not_block_new_samples_at_production_sender_cadence(tmp_path):
    original,config,mqtt=base.configured(tmp_path)
    box=ReliableOutbox(original.path,2000,**original.identity)
    old_time=base.source_time()-3*86400*1000000000
    old=[box.enqueue(old_time+i*1000,VALUES) for i in range(1000)]
    commits=[];completed={};latencies=[];ranks=[];stop=threading.Event();errors=[]
    with base.running_receiver(config) as receiver,base.running_sender(box,mqtt) as sender:
        commit=receiver.store.commit
        async def observed(sample):
            result=await commit(sample)
            completed[sample['sample_id']]=time.monotonic();commits.append(sample['sample_id'])
            return result
        receiver.store.commit=observed
        base.establish(sender)
        def send():
            try:
                while not stop.is_set():
                    sender.step(stop);stop.wait(1)  # Same pacing as edge.run(), not an accelerated drain.
            except Exception as exc:errors.append(type(exc).__name__)
        thread=threading.Thread(target=send,daemon=True);thread.start()
        try:
            base.wait_for(lambda:len(commits)>=2,seconds=6)
            for i in range(3):
                before=len(commits);started=time.monotonic()
                sample=box.enqueue(base.source_time(),dict(VALUES,voltage=240+i))
                base.wait_for(lambda:sample['sample_id'] in completed,seconds=4)
                latency=completed[sample['sample_id']]-started
                rank=commits[before:].index(sample['sample_id'])+1
                latencies.append(latency);ranks.append(rank)
                assert latency<4 and rank<=3, 'new sample waited behind historical backlog'
            assert old[0]['sample_id'] in commits and old[1]['sample_id'] in commits, 'newest priority starved oldest history'
        finally:
            stop.set();thread.join(4)
            assert not thread.is_alive() and not errors, f'production-paced sender failed: {errors}'
    with box.connect() as db:
        audit_count=db.execute('SELECT COUNT(*) FROM audit').fetchone()[0]
        pending_count=db.execute('SELECT COUNT(*) FROM queue').fetchone()[0]
        confirmed=db.execute("SELECT COUNT(*) FROM audit WHERE state='committed'").fetchone()[0]
        assert audit_count==1003 and pending_count+confirmed==1003 and pending_count>900, 'test drained/recreated/dropped history instead of measuring bounded live delay'
    emit('live-backlog-delay',old_samples=1000,new_samples=3,sender_wait_seconds=1,
         enqueue_to_commit_seconds=latencies,completion_ranks_after_enqueue=ranks,
         oldest_backlog_advanced=True,confirmed_samples=confirmed,pending_history_retained=pending_count,
         retained_total=1003,scope='three short samples on private local stack, not a percentile or field SLA')
