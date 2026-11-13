"""Logical SQLite damage must not pass structural quick_check as safe data."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest

from delta_device.reliable_store import ReliableOutbox
from delta_device.reliable_wire import canonical,sample_hash

pytestmark=pytest.mark.integration
NOW=1794474000000000000
VALUES=dict(voltage=230,current=5,power_kw=1,energy_kwh=100)


def make_box(tmp_path):
    box=ReliableOutbox(tmp_path/'state'/'q.db',10,'g1','d1',str(uuid4()),'r1','delta-v135')
    return box,box.enqueue(NOW,VALUES)


def damage(box,kind):
    with closing(sqlite3.connect(box.path)) as db:
        if kind=='sequence-rollback':db.execute("UPDATE metadata SET value='0' WHERE key='sequence'")
        elif kind=='clock-rollback':db.execute("UPDATE metadata SET value='0' WHERE key='latest_timestamp'")
        elif kind=='missing-audit':db.execute('DELETE FROM audit')
        elif kind=='audit-hash':db.execute("UPDATE audit SET payload_hash=?",('0'*64,))
        elif kind=='audit-state':db.execute("UPDATE audit SET state='committed',acknowledged_us=1")
        elif kind=='orphan-audit':db.execute('DELETE FROM queue')
        elif kind=='audit-sequence':db.execute('UPDATE audit SET capture_seq=capture_seq+1')
        else:raise ValueError('unknown damage')
        db.commit()
        assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok', 'test damaged structure instead of logical contents'


@pytest.mark.parametrize('kind',['sequence-rollback','clock-rollback','missing-audit','audit-hash','audit-state','orphan-audit','audit-sequence'])
def test_existing_logically_inconsistent_queue_is_rejected_without_modifying_evidence(tmp_path,kind):
    box,item=make_box(tmp_path);damage(box,kind);before=box.path.read_bytes()
    with pytest.raises(ValueError):ReliableOutbox(box.path,10,**box.identity)
    after=box.path.read_bytes()
    assert before==after, 'logical corruption was repaired or overwritten without authority'
    directory=os.environ.get('EDGE_V2_EVIDENCE')
    if directory:
        Path(directory,'logical-'+kind+'.json').write_text(json.dumps(dict(passed=True,damage=kind,
            quick_check='ok',rejected=True,original_sample_id=item['sample_id'],
            before_sha256=hashlib.sha256(before).hexdigest(),after_sha256=hashlib.sha256(after).hexdigest()),indent=2))


@pytest.mark.parametrize('kind',['hash-mismatch','valid-different-id','valid-different-sequence','valid-different-device','wrong-window','invalid-json'])
def test_selected_pending_payload_must_match_persisted_identity_before_sending(tmp_path,kind):
    box,item=make_box(tmp_path);changed=json.loads(canonical(item))
    if kind=='hash-mismatch':changed['measurements']['voltage']=999
    elif kind=='valid-different-id':changed['sample_id']=str(uuid4())
    elif kind=='valid-different-sequence':changed['capture_seq']+=1
    elif kind=='valid-different-device':changed['device_id']='other'
    elif kind=='wrong-window':changed['window_id']=str(uuid4())
    if kind not in ('hash-mismatch','invalid-json'):changed['payload_hash']=sample_hash(changed)
    payload='{' if kind=='invalid-json' else canonical(changed).decode()
    with box.connect() as db:db.execute('UPDATE queue SET payload=?',(payload,))
    before=box.path.read_bytes()
    with pytest.raises(ValueError):box.pending()
    assert box.path.read_bytes()==before, 'pending reader modified damaged source'


@pytest.mark.parametrize('kind',['missing-audit','audit-hash','audit-state','audit-sequence'])
def test_ack_after_live_audit_damage_cannot_delete_pending_or_fabricate_audit(tmp_path,kind):
    box,item=make_box(tmp_path);damage(box,kind);before=box.path.read_bytes()
    with pytest.raises(ValueError):box.committed(item['sample_id'],item['payload_hash'])
    assert box.path.read_bytes()==before and box.pending_count()==1, 'ACK removed source despite broken audit identity'


def test_valid_committed_and_quarantined_rows_survive_reopen_and_continue_sequence(tmp_path):
    box,first=make_box(tmp_path);box.committed(first['sample_id'],first['payload_hash'])
    second=box.enqueue(NOW+1000,VALUES);box.quarantine(second['sample_id'],second['payload_hash'],'conflict')
    reopened=ReliableOutbox(box.path,10,**box.identity)
    third=reopened.enqueue(NOW+2000,VALUES)
    assert third['capture_seq']==3 and reopened.pending()==[third] and reopened.audit_count()==3, 'healthy state rejected or sequence reset'


@pytest.mark.parametrize('kind',['sequence-rollback','clock-rollback'])
@pytest.mark.parametrize('committed',[False,True])
def test_live_high_water_rollback_cannot_retire_source_or_reuse_sequence(tmp_path,kind,committed):
    box,item=make_box(tmp_path);box.limit=1
    if committed:box.committed(item['sample_id'],item['payload_hash'])
    damage(box,kind);before=box.path.read_bytes();status=box.retention_status()
    with pytest.raises(ValueError):box.enqueue(NOW+1000,VALUES)
    assert box.path.read_bytes()==before and box.retention_status()==status, 'live rollback changed or retired source before failing'
    assert box.pending_count()==(0 if committed else 1) and box.audit_count()==1, 'counter rollback reused sequence or erased audit'


def test_duplicate_retained_audit_sequence_is_rejected_on_reopen(tmp_path):
    box,first=make_box(tmp_path);box.committed(first['sample_id'],first['payload_hash'])
    box.enqueue(NOW+1000,VALUES)
    with box.connect() as db:db.execute('UPDATE audit SET capture_seq=1 WHERE sample_id=?',(first['sample_id'],));db.execute('UPDATE audit SET capture_seq=1 WHERE sample_id!=?',(first['sample_id'],));db.execute('UPDATE queue SET capture_seq=1')
    before=box.path.read_bytes()
    with pytest.raises(ValueError):ReliableOutbox(box.path,10,**box.identity)
    assert box.path.read_bytes()==before, 'duplicate sequence was silently repaired'


def test_retention_counter_overflow_rolls_back_entire_replacement(tmp_path):
    box,_=make_box(tmp_path);box.limit=1;box.enqueue(NOW+1000,VALUES)
    status=box.retention_status();status['audit_evicted_total']=status['unconfirmed_evicted_total']=2**63-1
    with box.connect() as db:db.execute("UPDATE metadata SET value=? WHERE key='retention'",(json.dumps(status),))
    before=box.path.read_bytes()
    with pytest.raises(ValueError):box.enqueue(NOW+2000,VALUES)
    assert box.path.read_bytes()==before and box.retention_status()==status, 'overflow committed an unreadable summary or retired source'


def test_pending_uses_one_read_snapshot_during_real_capacity_rotation(tmp_path,monkeypatch):
    import threading
    box,item=make_box(tmp_path);box.limit=1
    other=ReliableOutbox(box.path,1,**box.identity)
    retired=threading.Event();done=threading.Event();errors=[];new=[]
    retire=other._retire
    def observe_retire(*args):
        result=retire(*args);retired.set();return result
    monkeypatch.setattr(other,'_retire',observe_retire)
    def rotate():
        try:new.append(other.enqueue(NOW+1000,VALUES))
        except Exception as exc:errors.append(type(exc).__name__)
        finally:done.set()
    writer=threading.Thread(target=rotate)
    validate=box._validated_pending
    def interleave(db,row):
        writer.start()
        assert retired.wait(2), 'writer did not actually reach retirement inside the read window'
        done.wait(.05)
        return validate(db,row)
    monkeypatch.setattr(box,'_validated_pending',interleave)
    try:assert box.pending()==[item], 'reader failed to preserve its original snapshot'
    finally:writer.join(6)
    assert not writer.is_alive() and not errors and len(new)==1, 'concurrent rotation failed'
    monkeypatch.setattr(box,'_validated_pending',validate)
    assert box.pending()==new, 'new source disappeared after read snapshot released'
