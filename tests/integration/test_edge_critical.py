"""Bounded data ENOSPC, invalid physical slot, and real same-cluster forks."""
import json
import os
from pathlib import Path
import threading
from uuid import uuid4

import pytest

import test_edge_receipts_mqtt as base
from test_edge_wal_security import configured,emit

pytestmark=pytest.mark.integration
VALUES=dict(voltage=230,current=5,power_kw=1,energy_kwh=100)


@pytest.fixture(autouse=True)
def owned_gate():
    if os.environ.get('EDGE_V2_CRITICAL')!='1':pytest.skip('explicit owned critical bench required')
    assert os.readlink('/proc/self/ns/net')==os.environ['EMS_V2_DEMO_NETNS'], 'wrong namespace'
    assert {p.name for p in Path('/sys/class/net').iterdir()}=={'lo'}, 'unexpected network interface'


def control(op):
    directory=Path(os.environ['EDGE_V2_EVIDENCE']);token=str(uuid4())
    path=directory/('control-'+token+'.request.json');temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(request_id=token,op=op)));os.replace(temporary,path)
    response=path.with_name(path.name.replace('.request.json','.response.json'))
    base.wait_for(response.exists,seconds=120 if op=='timeline_matrix' else 65)
    result=json.loads(response.read_text())
    assert result.get('passed') is True and result.get('request_id')==token and result.get('op')==op, 'fixed operation failed'
    return result


def test_central_receipt_data_enospc_keeps_source_and_recovers_once(tmp_path,monkeypatch):
    box,config,mqtt=configured(tmp_path,monkeypatch);sample=box.enqueue(base.source_time(),VALUES)
    statuses=[]
    with base.running_receiver(config) as receiver,base.running_sender(box,mqtt,mode='field') as sender:
        publish=receiver.client.publish
        def observe(topic,payload,**kwargs):
            if topic.endswith('/acks'):statuses.extend(r['status'] for r in json.loads(payload)['results'])
            return publish(topic,payload,**kwargs)
        receiver.client.publish=observe;base.establish(sender)
        full=control('db_data_full')
        try:
            base.wait_for(lambda:bool(statuses) or (sender.step(threading.Event()) and bool(statuses)),seconds=8)
            assert statuses and set(statuses)=={'retryable'}, 'full central relation returned a committed ACK'
            assert box.pending()==[sample] and not base.db_rows(config,sample), 'full database deleted/partially projected source'
            failure_statuses=list(statuses)
        finally:freed=control('db_data_free')
        base.deliver(sender,box,seconds=12)
    assert len(base.db_rows(config,sample))==1 and box.pending_count()==0, 'central ENOSPC recovery lost/duplicated source'
    cleaned=control('db_data_clean')
    emit('central-data-full',full=full,freed=freed,statuses_during_failure=failure_statuses,source_preserved=True,
        rows=1,pending_end=0,tablespace_removed=cleaned['tablespace_removed'])


def test_lost_physical_slot_keeps_pending_until_verified_new_base_and_wal_chain(tmp_path,monkeypatch):
    box,config,mqtt=configured(tmp_path,monkeypatch);a=box.enqueue(base.source_time(),VALUES)
    statuses=[]
    with base.running_receiver(config) as receiver,base.running_sender(box,mqtt,mode='field') as sender:
        publish=receiver.client.publish
        def observe(topic,payload,**kwargs):
            if topic.endswith('/acks'):statuses.extend(r['status'] for r in json.loads(payload)['results'])
            return publish(topic,payload,**kwargs)
        receiver.client.publish=observe
        base.establish(sender);base.deliver(sender,box)
        assert box.pending_count()==0 and len(base.db_rows(config,a))==1, 'baseline did not receive committed ACK'
        lost=control('slot_lose')
        b=box.enqueue(base.source_time(),dict(VALUES,voltage=231))
        statuses.clear()
        base.wait_for(lambda:bool(statuses) or (sender.step(threading.Event()) and bool(statuses)),seconds=8)
        assert statuses and set(statuses)=={'retryable'} and box.pending()==[b], 'lost slot falsely confirmed source'
        lost_statuses=list(statuses)
        assert not base.db_rows(config,b), 'lost slot partially committed source'
    rebuilt=control('slot_reseed')
    generation=str(uuid4());Path(config['generation_file']).write_text(generation)
    with base.running_receiver(config),base.running_sender(box,mqtt,mode='field') as sender:
        base.establish(sender)
        assert sender.state.generation==generation, 'reseed did not rotate session generation'
        base.deliver(sender,box,seconds=12)
    assert [len(base.db_rows(config,s)) for s in (a,b)]==[1,1] and box.pending_count()==0, 'reseed lost or duplicated samples'
    emit('slot-reseed',lost=lost,rebuilt=rebuilt,ack_fenced_until_reseed=True,generation_rotated=True,
        statuses_during_failure=lost_statuses,source_preserved=True,rows=[1,1],pending_end=0)


def test_same_cluster_forks_require_explicit_timeline_for_second_pitr():
    proof=control('timeline_matrix')
    assert proof['branch_timelines']==[2,3] and proof['approved_timeline']==2, 'fork setup invalid'
    assert proof['pinned_rows']=='branch-two' and proof['unsafe_latest_rows']=='branch-three', 'branch selection counterexample missing'
    assert all(proof[k] for k in ('latest_rejected','second_pitr_promoted','backup_verified','pristine_inputs_unchanged')), 'pinned recovery incomplete'
    emit('timeline-pitr',**{k:v for k,v in proof.items() if k!='passed'})
