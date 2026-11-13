"""Real malformed MQTT batch isolation and SIGTERM while DB commit is blocked."""
import asyncio
import copy
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

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
    if os.environ.get('EDGE_V2_INTEGRITY')!='1':pytest.skip('explicit private integrity bench required')
    assert os.readlink('/proc/self/ns/net')==os.environ['EMS_V2_DEMO_NETNS'], 'wrong network namespace'
    assert {p.name for p in Path('/sys/class/net').iterdir()}=={'lo'}, 'unexpected interface'
    assert os.environ['EDGE_V2_TEST_DSN']=='postgresql://postgres@127.0.0.1:5432/ems', 'unexpected DB'


def emit(name,**value):
    Path(os.environ['EDGE_V2_EVIDENCE'],name+'.json').write_text(json.dumps(dict(passed=True,**value),indent=2))


@pytest.mark.parametrize('kind',['bad-hash','duplicate-id','duplicate-key','invalid-utf8','excess-depth'])
def test_malformed_mqtt_batch_writes_nothing_then_valid_originals_recover_once(tmp_path,kind):
    box,config,mqtt=base.configured(tmp_path)
    first=box.enqueue(base.source_time(),VALUES)
    second=box.enqueue(base.source_time(),dict(VALUES,voltage=231))
    handled=threading.Event();acks=[]
    with base.running_receiver(config) as receiver,base.running_sender(box,mqtt) as sender:
        base.establish(sender)
        with sender.lock:envelope=sender.state.prepare(first)
        envelope=copy.deepcopy(envelope);envelope['samples']=[first,copy.deepcopy(second)]
        if kind=='bad-hash':envelope['samples'][1]['measurements']['voltage']=999
        elif kind=='duplicate-id':envelope['samples']=[first,first]
        elif kind=='excess-depth':envelope['unexpected']=[[[[[[[[[[0]]]]]]]]]]
        raw=canonical(envelope)
        if kind=='duplicate-key':raw=raw[:-1]+b',"batch_id":'+canonical(envelope['batch_id'])+b'}'
        elif kind=='invalid-utf8':raw=raw[:-1]+b',"unexpected":"\xff"}'
        handle=receiver.handle;publish=receiver.client.publish
        async def observe(topic,payload):
            try:await handle(topic,payload)
            finally:
                if payload==raw:handled.set()
        def observe_ack(topic,payload,**kwargs):
            if topic.endswith('/acks'):acks.append(json.loads(payload))
            return publish(topic,payload,**kwargs)
        receiver.handle=observe;receiver.client.publish=observe_ack
        sender.client.publish(sender.prefix+'samples',raw,qos=1,retain=False).wait_for_publish(timeout=3)
        assert handled.wait(3), 'malformed batch did not reach the actual receiver parser'
        assert not acks and box.pending_count()==2, 'malformed batch caused an ACK or source deletion'
        assert [len(base.db_rows(config,s)) for s in (first,second)]==[0,0], 'part of malformed batch committed'
        assert receiver.ready.is_set(), 'receiver stopped after hostile batch'
        base.deliver(sender,box)
    assert [len(base.db_rows(config,s)) for s in (first,second)]==[1,1] and box.pending_count()==0, 'valid recovery lost or duplicated original samples'
    emit('malformed-'+kind,kind=kind,actual_parser_observed=True,acks_before_recovery=0,
        rows_before=[0,0],rows_after=[1,1],pending_end=0,receiver_survived=True)


def test_sigterm_during_real_database_wait_exits_cleanly_and_full_edge_restart_recovers(tmp_path):
    box,config,mqtt=base.configured(tmp_path);config['db_timeout_seconds']=5
    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    edge_config=dict(mode='demo',device_id='d1',outbox_path=str(box.path),queue_limit=100,poll_interval=1,batch_size=1,
        mqtt=mqtt,modbus=dict(transport='tcp',host='127.0.0.1',port=port,unit_id=1,timeout=1),
        delivery=dict(protocol=2,ack_timeout_seconds=5,**{k:box.identity[k] for k in ('gateway_id','stream_id','config_revision','profile_version')}))
    path=tmp_path/'edge.json';path.write_text(json.dumps(edge_config));children=[]
    def samples():
        with box.connect() as db:return [json.loads(r[0]) for r in db.execute('SELECT payload FROM queue ORDER BY capture_seq')]
    async def blocked():
        async with ReceiptStore(os.environ['EDGE_V2_TEST_DSN']).connection() as db:
            return await db.fetchval("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE pid<>pg_backend_pid() AND wait_event_type='Lock' AND query LIKE '%FROM public.electricity_measurements%')")
    with (tmp_path/'sim.log').open('w') as simlog,(tmp_path/'edge.log').open('w') as edgelog:
        try:
            sim=subprocess.Popen([sys.executable,'-m','delta_device','simulator','--host','127.0.0.1','--port',str(port),'--scenario','day'],stdout=simlog,stderr=subprocess.STDOUT);children.append(sim)
            def ready():
                assert sim.poll() is None, 'private simulator died'
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.2):return True
                except OSError:return False
            base.wait_for(ready)
            with base.running_receiver(config):
                with projection_lock(config):
                    edge=subprocess.Popen([sys.executable,'-m','delta_device','edge','--config',str(path)],stdout=edgelog,stderr=subprocess.STDOUT);children.append(edge)
                    base.wait_for(lambda:asyncio.run(blocked()),seconds=4)
                    assert box.pending_count()>=1, 'source was not pending while central DB blocked'
                    started=time.monotonic();edge.terminate();edge.wait(4);elapsed=time.monotonic()-started
                    assert edge.returncode==0, 'SIGTERM forced or crashed the edge instead of graceful exit'
                    saved=samples();assert saved, 'SIGTERM discarded unacknowledged source'
                    assert asyncio.run(blocked()), 'database wait ended before graceful edge exit was observed'
                identity=[dict(sample_id=s['sample_id'],payload_hash=s['payload_hash']) for s in saved]
                reopened=ReliableOutbox(box.path,100,**box.identity)
                assert samples()==saved, 'graceful restart changed original source payloads'
                second=subprocess.Popen([sys.executable,'-m','delta_device','edge','--config',str(path)],stdout=edgelog,stderr=subprocess.STDOUT);children.append(second)
                before_count=box.audit_count()
                base.wait_for(lambda:all(len(base.db_rows(config,s))==1 for s in saved) and box.audit_count()>before_count,seconds=9)
                second.terminate();second.wait(4)
                assert second.returncode==0, 'restarted edge failed graceful shutdown'
                with base.running_sender(reopened,mqtt) as sender:base.deliver(sender,reopened,seconds=12)
                with box.connect() as db:ledger=[dict(sample_id=r[0],payload_hash=r[1]) for r in db.execute('SELECT sample_id,payload_hash FROM audit ORDER BY capture_seq')]
                async def central():
                    async with ReceiptStore(os.environ['EDGE_V2_TEST_DSN']).connection() as db:
                        rows=await db.fetch('SELECT sample_id::text,payload_hash,sample FROM edge_ingest.receipts WHERE gateway_id=$1',box.identity['gateway_id'])
                        projections=await db.fetch('SELECT edge_sample_id::text,COUNT(*) n FROM electricity_measurements WHERE edge_gateway_id=$1 GROUP BY edge_sample_id',box.identity['gateway_id'])
                        values=await db.fetch('SELECT edge_sample_id::text AS sample_id,time,device_id,voltage,current,power_kw,energy_kwh FROM electricity_measurements WHERE edge_gateway_id=$1',box.identity['gateway_id'])
                        return rows,projections,values
                receipts,projections,projection_values=asyncio.run(central())
                assert {r['sample_id']:r['payload_hash'] for r in receipts}=={r['sample_id']:r['payload_hash'] for r in ledger}, 'central IDs/hashes differ from acquisition ledger'
                assert len(projections)==len(ledger) and all(r['n']==1 for r in projections), 'restart duplicated or lost projections'
                restored={r['sample_id']:json.loads(r['sample']) for r in receipts}
                assert {r['sample_id'] for r in projection_values}=={r['sample_id'] for r in ledger}, 'projection ID set differs from source ledger'
                for row in projection_values:
                    expected=restored[row['sample_id']]
                    assert row['time']==datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(microseconds=expected['sampled_at_us']), 'projection changed source time'
                    assert row['device_id']==expected['device_id'] and all(row[k]==expected['measurements'][k] for k in VALUES), 'projection differs from canonical measurements'
                assert all(restored[s['sample_id']]==s for s in saved), 'pre-SIGTERM canonical content changed'
                assert reopened.pending_count()==0, 'graceful restart left unprocessed sources'
                emit('sigterm-db-wait',real_db_lock_observed=True,wait_still_active_at_exit=True,
                    first_exit=edge.returncode,restart_exit=second.returncode,graceful_exit_seconds=elapsed,
                    saved_before_restart=identity,total_acquired=len(ledger),receipts=len(receipts),projections=len(projections),
                    all_projection_counts_one=True,projection_ids_match=True,projection_values_match=True,
                    original_canonical_unchanged=True,ledger_hashes_match=True,pending_end=0)
        finally:
            for child in reversed(children):
                if child.poll() is None:
                    child.terminate()
                    try:child.wait(4)
                    except subprocess.TimeoutExpired:child.kill();child.wait(3)
    for name in ('sim','edge'):Path(os.environ['EDGE_V2_EVIDENCE'],'sigterm-'+name+'.log').write_bytes((tmp_path/(name+'.log')).read_bytes())
