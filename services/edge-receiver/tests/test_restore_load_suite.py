"""Logical restore/load evidence cannot be replaced with exit-zero claims."""
from pathlib import Path
import os
import sys
from uuid import uuid4
import xml.etree.ElementTree as ET
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from verify_private import assess_restore_load_report,control_target,lifecycle_control,suite_targets


def fixture():
    root=ET.Element('testsuite')
    for c in ET.parse(Path(__file__).parent/'fixtures/faults-and-boundary.xml').getroot():
        if c.get('classname','').endswith('test_bench_slot_boundary'):root.append(c)
    for name in ['test_real_database_backup_restore_new_generation_recovers_pending_and_exposes_acked_loss',
        'test_real_mqtt_burst_fills_bounded_receiver_queue_then_recovers_original_once',
        'test_thousand_old_samples_do_not_block_new_samples_at_production_sender_cadence']:
        ET.SubElement(root,'testcase',name=name,classname='tests.restore_load')
    proof={'database-restore':dict(passed=True,backup=dict(passed=True,format='pg_dump-custom',backup_sha256='a'*64,backup_bytes=100),
        restore=dict(passed=True,target_database='ems_restore',restore_method='pg_restore-to-new-database'),
        original_db_preserved=True,restored_counts_before_replay=[1,0,0],old_ack_replayed=True,old_ack_accepted=False,
        backup_identity_and_projection_matched=True,recovered_original_identity_and_projection_matched=True,
        old_generation='old',new_generation='new',recovered_pending_rows=1,fresh_rows=1,pending_end=0,unrecoverable_acked_after_backup=['id']),
        'receiver-overload':dict(passed=True,mqtt_messages=200,messages=200,unique_source_samples=1,peak=64,receiver_capacity=64,
            dropped=100,rate_denied=10,actual_db_lock_observed=True,no_committed_ack_while_locked=True,original_rows=1,fresh_rows=1,pending_end=0),
        'live-backlog-delay':dict(passed=True,old_samples=1000,new_samples=3,sender_wait_seconds=1,
            enqueue_to_commit_seconds=[1,2,2],completion_ranks_after_enqueue=[1,2,2],oldest_backlog_advanced=True,
            retained_total=1003,pending_history_retained=997,confirmed_samples=6)}
    return root,proof


def test_restore_load_suite_is_bounded_and_database_control_is_owned():
    assert suite_targets('restore-load')==('/app/tests/integration/test_edge_restore_load.py','/app/services/delta/tests/test_bench_slot_boundary.py'), 'unbounded restore/load suite'
    for op in ['db_backup','db_restore']:
        assert control_target(dict(request_id=str(uuid4()),op=op),[('database','own-db')])=='own-db', 'DB control selected shared target'
        with pytest.raises(ValueError):control_target(dict(request_id=str(uuid4()),op=op),[])


def test_complete_restore_load_proof_passes():
    root,proof=fixture()
    assert assess_restore_load_report(ET.tostring(root,encoding='unicode'),0,proof)['passed'], 'complete proof rejected'


@pytest.mark.parametrize('mutation',['skip','missing-case','duplicate-case','no-real-dump','no-restore-rollback',
    'old-ack-accepted','generation-not-changed','hidden-acked-loss','backup-values-changed','recovered-values-changed','queue-never-full','burst-lost-at-publisher',
    'no-rate-limit','false-commit-under-lock','new-data-slow','accelerated-loop','oldest-starved','history-disappeared'])
def test_restore_load_assessment_rejects_missing_or_false_evidence(mutation):
    root,proof=fixture()
    if mutation=='skip':ET.SubElement(root[-1],'skipped')
    elif mutation=='missing-case':root.remove(root[-1])
    elif mutation=='duplicate-case':root.append(ET.fromstring(ET.tostring(root[-1])))
    elif mutation=='no-real-dump':proof['database-restore']['backup']['backup_bytes']=0
    elif mutation=='no-restore-rollback':proof['database-restore']['restored_counts_before_replay']=[1,1,1]
    elif mutation=='old-ack-accepted':proof['database-restore']['old_ack_accepted']=True
    elif mutation=='generation-not-changed':proof['database-restore']['new_generation']='old'
    elif mutation=='hidden-acked-loss':proof['database-restore']['unrecoverable_acked_after_backup']=[]
    elif mutation=='backup-values-changed':proof['database-restore']['backup_identity_and_projection_matched']=False
    elif mutation=='recovered-values-changed':proof['database-restore']['recovered_original_identity_and_projection_matched']=False
    elif mutation=='queue-never-full':proof['receiver-overload']['peak']=63
    elif mutation=='burst-lost-at-publisher':proof['receiver-overload']['messages']=50
    elif mutation=='no-rate-limit':proof['receiver-overload']['rate_denied']=0
    elif mutation=='false-commit-under-lock':proof['receiver-overload']['no_committed_ack_while_locked']=False
    elif mutation=='new-data-slow':proof['live-backlog-delay']['enqueue_to_commit_seconds']=[1,4,2]
    elif mutation=='accelerated-loop':proof['live-backlog-delay']['sender_wait_seconds']=0
    elif mutation=='oldest-starved':proof['live-backlog-delay']['oldest_backlog_advanced']=False
    else:proof['live-backlog-delay']['pending_history_retained']=900
    assert not assess_restore_load_report(ET.tostring(root,encoding='unicode'),0,proof)['passed'], f'{mutation} falsely passed'


@pytest.mark.parametrize('copied_kind',['symlink','fifo','oversized'])
def test_database_copy_cannot_follow_symlink_block_or_read_unbounded_host_file(tmp_path,monkeypatch,copied_kind):
    private=tmp_path/'private';private.mkdir()
    output=tmp_path/'evidence';output.mkdir()
    outside=tmp_path/'host-secret';outside.write_bytes(b'PRIVATE')
    read_bytes=Path.read_bytes
    def reject_unsafe_read(path):
        if path.name=='central-backup.dump':
            raise AssertionError('host attempted an unbounded path read of container-controlled backup')
        return read_bytes(path)
    monkeypatch.setattr(Path,'read_bytes',reject_unsafe_read)
    def fake_call(args,**kwargs):
        if 'sha256sum' in args:return 'a'*64+'  backup.dump'
        if args[:2]==['docker','cp']:
            dest=Path(args[-1])
            if copied_kind=='symlink':dest.symlink_to(outside)
            elif copied_kind=='fifo':os.mkfifo(dest)
            else:
                with dest.open('wb') as stream:stream.truncate(16*1024*1024+1)
        return ''
    with pytest.raises((OSError,ValueError)):
        lifecycle_control(dict(request_id=str(uuid4()),op='db_backup'),[('database','own-db')],fake_call,private,output)
    assert outside.read_bytes()==b'PRIVATE' and not (output/'central-backup.dump').exists(), 'copied link or unbounded data was exposed as host evidence'
    assert not list(private.glob('dump-copy-*')), 'failed DB-copy temporary directory leaked'
