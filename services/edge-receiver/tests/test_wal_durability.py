"""Field ACK must have independently flushed WAL, not just a local commit."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from edge_receiver.receiver import validate_config
from edge_receiver.store import ReceiptStore


def config(tmp_path):
    value=json.loads((Path(__file__).parents[1]/'deploy/receiver.example.json').read_text())
    generation=tmp_path/'generation';generation.write_text('77a7e12a-f5af-4025-b172-309cfbb5f082')
    value['generation_file']=str(generation)
    return value


def test_field_defaults_to_synchronous_wal_and_forbids_local_downgrade(tmp_path):
    value=validate_config(config(tmp_path))
    assert value['ack_durability']=='sync_wal' and value['wal_standby_name']=='ems_archive', 'field ACK lacks WAL guard'
    value['ack_durability']='local'
    with pytest.raises(ValueError):validate_config(value)


@pytest.mark.parametrize('name',['','*','ems_archive,other','x'*64,12])
def test_wal_standby_name_cannot_select_arbitrary_or_multiple_peers(tmp_path,name):
    value=config(tmp_path);value['wal_standby_name']=name
    with pytest.raises(ValueError):validate_config(value)


def test_demo_local_is_explicitly_separate_from_field(tmp_path):
    value=config(tmp_path);value.pop('ack_durability',None);value['mode']='demo'
    assert validate_config(value)['ack_durability']=='local', 'legacy isolated demo changed'


def test_remote_flush_gate_requires_named_peer_at_fixed_lsn():
    db=AsyncMock();db.fetchval.return_value=False
    store=ReceiptStore('private',timeout=1,standby_name='ems_archive')
    with pytest.raises(ValueError):asyncio.run(store.require_wal(db,'0/1234'))
    args=db.fetchval.call_args.args
    assert args[1:]==('ems_archive','0/1234'), 'flush check did not bind the required peer/LSN'


def test_remote_flush_gate_accepts_only_true_boolean():
    for value in (None,False,0,'t'):
        db=AsyncMock();db.fetchval.return_value=value
        with pytest.raises(ValueError):asyncio.run(ReceiptStore('private',standby_name='ems_archive').require_wal(db))
    db=AsyncMock();db.fetchval.return_value=True
    asyncio.run(ReceiptStore('private',standby_name='ems_archive').require_wal(db))


def test_host_wal_helper_command_log_replaces_worker_symlink(tmp_path):
    import sys
    sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
    from verify_private import record_owned_command
    outside=tmp_path/'secret';outside.write_text('preserve')
    evidence=tmp_path/'commands.json';evidence.symlink_to(outside)
    record_owned_command(tmp_path,[],'owned-basebackup-client',['docker','create'],'owned-cid')
    assert outside.read_text()=='preserve' and not evidence.is_symlink(), 'host helper followed worker symlink'
    assert json.loads(evidence.read_text())[0]['name']=='owned-basebackup-client', 'command log lost'


def test_pitr_assessment_requires_each_actual_recovery_proof():
    import sys
    import xml.etree.ElementTree as ET
    sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
    from verify_private import assess_wal_report
    root=ET.Element('testsuite')
    for c in ET.parse(Path(__file__).parent/'fixtures/faults-and-boundary.xml').getroot():
        if c.get('classname','').endswith('test_bench_slot_boundary'):root.append(c)
    ET.SubElement(root,'testcase',name='test_acknowledged_postbackup_sample_recovers_from_independent_wal_after_primary_loss')
    keys=('wal_outage_kept_source','postcommit_wal_loss_kept_source','migration_least_privilege','postbackup_acked_payload_absent',
        'original_primary_stopped','original_pgdata_not_used','backup_and_wal_identity_match',
        'pitr_excluded_after_target','old_ack_rejected','missing_wal_failed_closed','recovered_sync_wal_ready')
    proof=dict.fromkeys(keys,True);proof.update(final_rows=[1,1,1,1],pending_end=0)
    xml=ET.tostring(root,encoding='unicode')
    assert assess_wal_report(xml,0,proof)['passed'], 'complete PITR evidence rejected'
    for key in (*keys,'final_rows','pending_end'):
        bad=dict(proof);bad.pop(key)
        assert not assess_wal_report(xml,0,bad)['passed'], f'absent {key} falsely passed'


@pytest.mark.parametrize('op',['wal_primary_loss','wal_recover','wal_missing'])
def test_wal_control_rejects_worker_selected_cid_path_sql_or_target(op):
    import sys
    from uuid import uuid4
    sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
    from verify_private import validate_wal_request
    valid=dict(request_id=str(uuid4()),op=op)
    validate_wal_request(valid)
    for key in ('cid','path','sql','target'):
        with pytest.raises(ValueError):validate_wal_request(dict(valid,**{key:'arbitrary'}))


@pytest.mark.parametrize('kind',['symlink','fifo','oversize','unknown-name'])
def test_independent_wal_snapshot_rejects_unsafe_or_unbounded_files(tmp_path,kind):
    import os
    import sys
    sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
    from private_wal import PrivateWal
    from verify_private import read_worker_bytes,atomic_host_text
    output=tmp_path/'out';output.mkdir()
    wal=PrivateWal(tmp_path,output,[],None,None,[],'image','1000:1000',atomic_host_text,read_worker_bytes)
    path=tmp_path/'wal'/('unknown' if kind=='unknown-name' else '000000010000000000000003.partial')
    outside=tmp_path/'secret';outside.write_bytes(b'keep')
    if kind=='symlink':path.symlink_to(outside)
    elif kind=='fifo':os.mkfifo(path)
    elif kind=='oversize':
        with path.open('wb') as f:f.truncate(16*1024*1024+1)
    else:path.write_bytes(b'bad')
    with pytest.raises((OSError,ValueError)):wal.snapshot('wal',publish=True)
    assert outside.read_bytes()==b'keep' and list(output.iterdir())==[], 'unsafe WAL file published'
