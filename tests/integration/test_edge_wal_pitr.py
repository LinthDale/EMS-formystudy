"""Actual physical PG15 restore after primary loss; no source DB oracle later."""
import asyncio
import copy
import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest

import test_edge_receipts_mqtt as base
from test_edge_restore_load import control, emit, stored_identity, VALUES
from edge_receiver.store import ReceiptStore
from delta_device.reliable_wire import canonical

pytestmark=pytest.mark.integration


def test_acknowledged_postbackup_sample_recovers_from_independent_wal_after_primary_loss(tmp_path):
    if os.environ.get('EDGE_V2_WAL_PITR')!='1':pytest.skip('explicit private WAL bench required')
    assert os.readlink('/proc/self/ns/net')==os.environ['EMS_V2_DEMO_NETNS'], 'wrong private namespace'
    assert {p.name for p in Path('/sys/class/net').iterdir()}=={'lo'}, 'network escape'
    box,config,mqtt=base.configured(tmp_path);config['ack_durability']='sync_wal';config['db_timeout_seconds']=2
    async def privileges():
        async with ReceiptStore(os.environ[config['dsn_env']]).connection() as db:
            assert await db.fetchval("SELECT has_function_privilege('web_anon','edge_ingest.sync_wal_flushed(text,pg_lsn)','EXECUTE')") is False, 'public durability function exposed'
            assert await db.fetchval("SELECT pg_has_role('ems_edge_receiver','pg_read_all_stats','MEMBER')") is False, 'receiver overprivileged'
            await db.execute('SET ROLE ems_edge_receiver')
            assert await db.fetchval("SELECT edge_ingest.sync_wal_flushed('ems_archive',NULL)") is True, 'least privilege receiver cannot check durability'
            assert await db.fetchval("SELECT edge_ingest.sync_wal_flushed('other',NULL)") is False, 'unrequired peer accepted'
    asyncio.run(privileges())
    a=box.enqueue(base.source_time(),VALUES);statuses=[];captured=[]
    with base.running_receiver(config) as receiver,base.running_sender(box,mqtt) as sender:
        base.establish(sender)
        publish=receiver.client.publish
        def observe(topic,payload,**kwargs):
            if topic.endswith('/acks'):statuses.extend(json.loads(payload)['results'])
            return publish(topic,payload,**kwargs)
        receiver.client.publish=observe
        stopped=control('wal_stop')
        base.wait_for(lambda:bool(statuses) or (sender.step(threading.Event()) and bool(statuses)),seconds=7)
        assert statuses and all(r['status']=='retryable' for r in statuses) and box.pending()==[a], 'WAL outage falsely confirmed or deleted source'
        started=control('wal_start')
        # Also cut WAL after the actual COMMIT, before the final ACK gate.
        # A must already exist centrally, yet stay pending when this gate fails.
        require=receiver.store.require_wal;after_commit=[];statuses.clear()
        async def cut_after_commit(db,lsn=None):
            if lsn is not None and not after_commit:
                after_commit.append(control('wal_stop'))
            await require(db,lsn)
        receiver.store.require_wal=cut_after_commit
        base.wait_for(lambda:bool(statuses) or (sender.step(threading.Event()) and bool(statuses)),seconds=8)
        assert after_commit and all(r['status']=='retryable' for r in statuses), 'post-COMMIT WAL failure falsely ACKed'
        assert box.pending()==[a] and len(base.db_rows(config,a))==1, 'post-COMMIT uncertain source/receipt window missing'
        receiver.store.require_wal=require;control('wal_start');base.deliver(sender,box)
        backup=control('wal_basebackup')
        b=box.enqueue(base.source_time(),dict(VALUES,voltage=231));base.deliver(sender,box)
        with box.connect() as db:
            assert db.execute('SELECT count(*) FROM queue WHERE sample_id=?',(b['sample_id'],)).fetchone()[0]==0, 'B payload not deleted after ACK'
            assert db.execute('SELECT state FROM audit WHERE sample_id=?',(b['sample_id'],)).fetchone()[0]=='committed', 'B not ACKed'
        reference=[stored_identity(config,s) for s in (a,b)]
        point=control('wal_restorepoint')
        c=box.enqueue(base.source_time(),dict(VALUES,voltage=232))
        def drop(topic,payload,**kwargs):
            if topic.endswith('/acks'):
                captured.append(json.loads(payload));return SimpleNamespace(rc=0)
            return publish(topic,payload,**kwargs)
        receiver.client.publish=drop
        base.wait_for(lambda:bool(captured) or (sender.step(threading.Event()) and bool(captured)),seconds=8)
        assert captured[-1]['results'][0]['status']=='committed' and box.pending()==[c], 'C was not committed with ACK lost'
        c_reference=stored_identity(config,c)
    old_ack=captured[-1]
    loss=control('wal_primary_loss')
    missing=control('wal_missing')
    recovery=control('wal_recover')
    target=copy.deepcopy(config);target['dsn_env']='EDGE_V2_PITR_DSN'
    assert os.environ[target['dsn_env']]=='postgresql://postgres@127.0.0.1:5433/ems', 'wrong recovered DSN'
    assert [stored_identity(target,s) for s in (a,b)]==reference, 'PITR changed receipt/hash/retention/timestamps/projection'
    assert stored_identity(target,c) is None and box.pending()==[c], 'PITR did not stop before C'
    generation=str(uuid4());Path(config['generation_file']).write_text(generation)
    with base.running_receiver(target),base.running_sender(box,mqtt) as sender:
        base.establish(sender);assert sender.state.generation==generation, 'generation not rotated'
        observed=threading.Event();callback=sender.client.on_message
        def observe_old(client,userdata,message):
            callback(client,userdata,message)
            if message.topic==sender.prefix+'acks' and json.loads(message.payload)==old_ack:observed.set()
        sender.client.on_message=observe_old
        sender.client.publish(sender.prefix+'acks',canonical(old_ack),qos=1).wait_for_publish(timeout=3)
        assert observed.wait(3) and sender.accepted is None and box.pending()==[c], 'old generation ACK deleted C'
        sender.client.on_message=callback;base.deliver(sender,box)
        d=box.enqueue(base.source_time(),dict(VALUES,voltage=233));base.deliver(sender,box)
    restored_c=stored_identity(target,c)
    assert restored_c['sample']==c_reference['sample'] and restored_c['projection']==c_reference['projection'], 'C resend changed original identity/values'
    rows=[len(base.db_rows(target,s)) for s in (a,b,c,d)]
    assert rows==[1,1,1,1] and box.pending_count()==0, 'PITR/replay missing or duplicate rows'
    emit('wal-pitr',wal_outage_kept_source=True,postcommit_wal_loss_kept_source=True,migration_least_privilege=True,
        postbackup_acked_payload_absent=True,original_primary_stopped=loss['original_primary_stopped'],
        original_pgdata_not_used=loss['original_pgdata_used_for_recovery'] is False,
        backup_and_wal_identity_match=True,pitr_excluded_after_target=True,old_ack_rejected=True,
        missing_wal_failed_closed=missing['target_not_reached'] and not missing['promoted'],
        recovered_sync_wal_ready=True,final_rows=rows,pending_end=box.pending_count(),
        recovered_acked_after_backup_sample_id=b['sample_id'],pending_replayed_sample_id=c['sample_id'],
        stopped=stopped,started=started,backup=backup,restore_point=point,primary_loss=loss,
        missing_wal=missing,recovery=recovery,
        scope='same-host isolated containers; physical basebackup+independently fsynced WAL, not site failure/RPO/RTO certification')
