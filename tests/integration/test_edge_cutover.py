"""Short field-role, conversion SIGKILL, and duplicate-client reconnect tests."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
import paho.mqtt.client as mqtt_client
import pytest

import test_edge_receipts_mqtt as base
from delta_device.delivery import Outbox,encode_line
from delta_device.migrate_delivery import migrate
from delta_device.reliable_store import ReliableOutbox
from delta_device.reliable_transport import connection_policy
from delta_device.reliable_wire import canonical
from edge_receiver.store import ReceiptStore

pytestmark=pytest.mark.integration
VALUES=dict(voltage=230,current=5,power_kw=1,energy_kwh=100)


@pytest.fixture(autouse=True)
def private_gate():
    if os.environ.get('EDGE_V2_CUTOVER')!='1':pytest.skip('explicitly provisioned private cutover bench required')
    assert os.readlink('/proc/self/ns/net')==os.environ['EMS_V2_DEMO_NETNS'], 'wrong network namespace'
    assert {p.name for p in Path('/sys/class/net').iterdir()}=={'lo'}, 'unexpected network interface'
    assert os.environ['EDGE_V2_TEST_DSN']=='postgresql://postgres@127.0.0.1:5432/ems', 'unexpected database'


def emit(name,**value):
    Path(os.environ['EDGE_V2_EVIDENCE'],name+'.json').write_text(json.dumps(dict(passed=True,**value),indent=2))


def admin(sql,*args):
    async def run():
        async with ReceiptStore(os.environ['EDGE_V2_TEST_DSN']).connection() as db:
            return await db.execute(sql,*args)
    return asyncio.run(run())


def field_config(tmp_path):
    box,config,mqtt=base.configured(tmp_path,gateway='qa-edge')
    pki=Path(os.environ['EDGE_V2_TEST_PKI'])
    tls=dict(port=8886,tls=True,ca_file=str(pki/'ca.crt'))
    mqtt.update(tls,cert_file=str(pki/'client.crt'),key_file=str(pki/'client.key'))
    config['mqtt'].update(tls,cert_file=str(pki/'edge-receiver.crt'),key_file=str(pki/'edge-receiver.key'))
    config['mode']='field'
    return box,config,mqtt


def test_field_mtls_limited_database_role_repairs_missing_projection_after_permission_recovery(tmp_path,monkeypatch):
    box,config,mqtt=field_config(tmp_path)
    role='qa_cutover_'+uuid4().hex
    admin('CREATE ROLE '+role+' LOGIN IN ROLE ems_edge_receiver')
    monkeypatch.setenv('EDGE_V2_LIMITED_DSN',os.environ['EDGE_V2_TEST_DSN'].replace('postgres@',role+'@'))
    limited=ReceiptStore(os.environ['EDGE_V2_LIMITED_DSN'],standby_name='ems_archive')
    async def privileges():
        async with limited.connection() as db:
            flags=await db.fetchrow('SELECT rolsuper,rolreplication,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user')
            assert all(v is False for v in flags.values()), 'field role has administrative privileges'
            for sql in ('DELETE FROM edge_ingest.receipts WHERE false',
                        "UPDATE edge_ingest.receipts SET payload_hash=payload_hash WHERE false",
                        'CREATE TABLE edge_ingest.unwanted_table(id int)', 'SELECT * FROM pg_shadow'):
                with pytest.raises(asyncpg.InsufficientPrivilegeError):await db.execute(sql)
            return dict(flags)
    flags=asyncio.run(privileges())
    config['dsn_env']='EDGE_V2_LIMITED_DSN';config['db_timeout_seconds']=2
    sample=box.enqueue(base.source_time(),VALUES);acks=[];failures=[]
    try:
        with base.running_receiver(config) as receiver,base.running_sender(box,mqtt,mode='field') as sender:
            base.establish(sender);publish=receiver.client.publish;commit=receiver.store.commit
            async def observe_commit(item):
                try:return await commit(item)
                except Exception as exc:failures.append(type(exc).__name__);raise
            receiver.store.commit=observe_commit
            def drop(topic,payload,**kwargs):
                if topic.endswith('/acks'):
                    acks.append(json.loads(payload));return SimpleNamespace(rc=0)
                return publish(topic,payload,**kwargs)
            receiver.client.publish=drop
            assert not sender.step(threading.Event()), 'lost ACK unexpectedly deleted source'
            assert acks[-1]['results'][0]['status']=='committed' and len(base.db_rows(config,sample))==1, 'limited field path did not really commit'
            first_stamp=acks[-1]['results'][0]['committed_at']
            admin('DELETE FROM electricity_measurements WHERE edge_sample_id=$1::uuid',sample['sample_id'])
            admin('REVOKE INSERT ON public.electricity_measurements FROM ems_edge_receiver')
            acks.clear()
            base.wait_for(lambda:bool(acks) or (sender.step(threading.Event()) and bool(acks)),seconds=8)
            assert failures==['InsufficientPrivilegeError'] and acks[-1]['results'][0]['status']=='retryable', 'missing privilege was not observed as retryable'
            assert box.pending()==[sample] and not base.db_rows(config,sample), 'permission failure fabricated projection/ACK'
            admin('GRANT INSERT ON public.electricity_measurements TO ems_edge_receiver')
            receiver.client.publish=publish;base.deliver(sender,box,seconds=12)
            stamp=asyncio.run(limited.commit(sample))
            assert stamp==first_stamp, 'repair replaced original receipt commit timestamp'
        assert len(base.db_rows(config,sample))==1 and box.pending_count()==0, 'limited role recovery duplicated or lost sample'
        emit('field-limited-role',administrative_flags=flags,denied_operations=4,
            actual_exception=failures[0],source_preserved_during_denial=True,receipt_timestamp_unchanged=True,
            mqtt_mtls=True,ack_durability=receiver.config['ack_durability'],rows=1,pending_end=0)
    finally:
        admin('GRANT INSERT ON public.electricity_measurements TO ems_edge_receiver')


CHILD=r'''
import json,os,signal,sys
from pathlib import Path
from delta_device.migrate_delivery import migrate
from delta_device.reliable_store import ReliableOutbox
source,target,stage,marker,identity=sys.argv[1:]
def stop():
    temporary=Path(marker+'.tmp');temporary.write_text(json.dumps(dict(stage=stage,pid=os.getpid())))
    os.replace(temporary,marker)
    signal.pause()
if stage=='after_first_row':
    original=ReliableOutbox.enqueue
    def enqueue(self,*args,**kwargs):
        result=original(self,*args,**kwargs);stop();return result
    ReliableOutbox.enqueue=enqueue
else:
    original=os.link
    def link(*args,**kwargs):
        if stage=='before_publish':stop()
        result=original(*args,**kwargs)
        if stage=='after_publish':stop()
        return result
    os.link=link
migrate(source,target,10,json.loads(identity),source_stopped=True)
'''


@pytest.mark.parametrize('stage',['after_first_row','before_publish','after_publish'])
def test_v1_conversion_sigkill_preserves_source_and_publishes_only_complete_v2(tmp_path,stage):
    initial,config,mqtt=base.configured(tmp_path/'connection')
    identity=initial.identity
    source=Outbox(tmp_path/'legacy'/'queue.db',10,'d1')
    timestamps=[base.source_time()+i*1000 for i in range(3)]
    snapshots=[dict(VALUES,voltage=230+i) for i in range(3)]
    for stamp,snapshot in zip(timestamps,snapshots):source.enqueue(stamp,encode_line('d1',snapshot,stamp),snapshot)
    source.ack(source.pending(10)[1][0])
    source_bytes=source.path.read_bytes();source_hash=hashlib.sha256(source_bytes).hexdigest()
    target=tmp_path/'converted'/'queue.db';marker=tmp_path/'boundary.json'
    with (tmp_path/'child.log').open('w') as log:
        child=subprocess.Popen([sys.executable,'-c',CHILD,str(source.path),str(target),stage,str(marker),json.dumps(identity)],stdout=log,stderr=subprocess.STDOUT)
        try:
            base.wait_for(lambda:marker.exists() or child.poll() is not None,seconds=8)
            assert marker.exists() and child.poll() is None, 'conversion did not reach the requested live boundary'
            observed=json.loads(marker.read_text())
            assert observed==dict(stage=stage,pid=child.pid), 'child did not report its own exact conversion boundary'
            child.kill();child.wait(3)
        finally:
            if child.poll() is None:child.kill();child.wait(3)
    assert child.returncode==-9 and source.path.read_bytes()==source_bytes, 'SIGKILL changed stopped v1 source'
    published=target.exists()
    assert published==(stage=='after_publish'), 'partial migration became the configured runnable destination'
    if not published:
        receipt=migrate(source.path,target,10,identity,source_stopped=True)
    else:
        with pytest.raises(FileExistsError):migrate(source.path,target,10,identity,source_stopped=True)
        with ReliableOutbox(target,10,**identity).connect() as db:
            receipt=json.loads(db.execute("SELECT value FROM metadata WHERE key='v1_migration'").fetchone()[0])
    box=ReliableOutbox(target,10,**identity)
    with box.connect() as db:
        samples=[json.loads(row[0]) for row in db.execute('SELECT payload FROM queue ORDER BY capture_seq')]
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok', 'published v2 damaged'
    assert len(samples)==receipt['rows']==len(receipt['mapping'])==2, 'published subset or resurrected legacy ACK'
    assert [s['sampled_at_us'] for s in samples]==[timestamps[i]//1000 for i in (0,2)], 'migration changed source timestamps'
    assert [s['measurements']['voltage'] for s in samples]==[230,232], 'migration changed source values'
    assert {s['sample_id'] for s in samples}=={m['sample_id'] for m in receipt['mapping']}, 'migration receipt lost IDs'
    with base.running_receiver(config),base.running_sender(box,mqtt) as sender:base.deliver(sender,box)
    assert [len(base.db_rows(config,s)) for s in samples]==[1,1] and box.pending_count()==0, 'converted source failed real delivery'
    assert source.path.read_bytes()==source_bytes, 'resumed migration/delivery modified v1 source'
    emit('conversion-'+stage,stage=stage,child_exit=child.returncode,observed=observed,published_at_crash=published,
        original_sha256=source_hash,source_unchanged=True,rows=2,central_rows=[1,1],pending_end=0,
        stable_mapping=True,scope='process SIGKILL only, not storage/power-cut durability')


def test_duplicate_mtls_client_id_disconnect_keeps_source_and_rejects_old_ack_after_reconnect(tmp_path):
    box,config,mqtt=field_config(tmp_path)
    first=box.enqueue(base.source_time(),VALUES);acks=[];disconnected=threading.Event()
    with base.running_receiver(config) as receiver,base.running_sender(box,mqtt,mode='field') as sender:
        base.establish(sender);publish=receiver.client.publish
        def drop(topic,payload,**kwargs):
            if topic.endswith('/acks'):
                acks.append(json.loads(payload));return SimpleNamespace(rc=0)
            return publish(topic,payload,**kwargs)
        receiver.client.publish=drop
        # Keep the actual batch inflight until the broker collision disconnects
        # it. Waiting for step() to time out first would invalidate the session
        # independently and make the collision assertion vacuous.
        sender.ack_timeout=5
        outcomes=[];send_errors=[]
        def send_inflight():
            try:outcomes.append(sender.step(threading.Event()))
            except Exception as exc:send_errors.append(type(exc).__name__)
        sending=threading.Thread(target=send_inflight,daemon=True);sending.start()
        base.wait_for(lambda:bool(acks),seconds=3)
        old_ack=acks[-1];old_challenge=sender.state.challenge
        assert (old_ack['results'][0]['status']=='committed' and sender.session_ready.is_set()
            and sender.state.challenge==old_ack['session_challenge']
            and sender.state.batch_id==old_ack['batch_id'] and sending.is_alive()), 'lost ACK was not still inflight before collision'
        disconnect=sender.client.on_disconnect;disconnect_states=[]
        def observe_disconnect(*args):
            with sender.lock:
                disconnect_states.append(dict(ready=sender.session_ready.is_set(),
                    challenge=sender.state.challenge,batch_id=sender.state.batch_id))
                disconnect(*args)
            disconnected.set()
        sender.client.on_disconnect=observe_disconnect
        sender.client.reconnect_delay_set(min_delay=2,max_delay=2)
        twin=mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2,client_id=mqtt['client_id'],reconnect_on_failure=False)
        connection_policy(twin,mqtt,'field');connected=threading.Event();twin.on_connect=lambda *_:connected.set()
        try:
            twin.connect('127.0.0.1',8886,30);twin.loop_start()
            assert connected.wait(3) and disconnected.wait(3), 'broker did not disconnect the duplicate client ID'
            assert disconnect_states[0]==dict(ready=True,challenge=old_challenge,batch_id=old_ack['batch_id']), 'ACK timeout invalidated the batch before the actual collision'
            assert not sender.session_ready.is_set() and box.pending()==[first], 'disconnect accepted old delivery or lost source'
            second=box.enqueue(base.source_time(),dict(VALUES,voltage=231))
        finally:
            twin.disconnect();twin.loop_stop()
            sending.join(6)
            assert not sending.is_alive() and outcomes==[False] and not send_errors, 'collision did not interrupt the pending send safely'
        receiver.client.publish=publish
        base.wait_for(lambda:sender.subscribed.is_set() and sender.state.challenge!=old_challenge,seconds=6)
        base.establish(sender)
        new_challenge=sender.state.challenge
        seen=threading.Event();message=sender.client.on_message
        def observe_ack(client,userdata,msg):
            message(client,userdata,msg)
            if msg.topic==sender.prefix+'acks' and json.loads(msg.payload)==old_ack:seen.set()
        sender.client.on_message=observe_ack
        publish(sender.prefix+'acks',canonical(old_ack),qos=1,retain=False).wait_for_publish(timeout=3)
        assert seen.wait(3) and sender.accepted is None and box.pending_count()==2, 'old challenge ACK deleted source after collision'
        sender.client.on_message=message;base.deliver(sender,box)
    assert [len(base.db_rows(config,s)) for s in (first,second)]==[1,1] and box.pending_count()==0, 'collision recovery lost/duplicated source'
    emit('duplicate-client-id',actual_disconnect=True,inflight_at_collision=True,observed_disconnect=disconnect_states[0],
        old_challenge=old_challenge,new_challenge=new_challenge,
        old_ack_observed=True,old_ack_accepted=False,source_preserved=True,central_rows=[1,1],pending_end=0)
