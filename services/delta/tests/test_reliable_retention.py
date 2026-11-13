"""ADR-045: keep newest telemetry without confusing retirement with delivery."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest

from delta_device.reliable_store import ReliableOutbox

NOW = 1794474000000000000
VALUES = dict(voltage=230, current=5, power_kw=1, energy_kwh=100)


def make_box(tmp_path, limit=3, audit_limit=20, byte_limit=1048576):
    return ReliableOutbox(tmp_path/'q'/'q.db', limit, 'g1', 'd1', str(uuid4()), 'r1', 'v135',
                          byte_limit=byte_limit, audit_limit=audit_limit)


def rows(box):
    with box.connect() as db:
        return [json.loads(row[0]) for row in db.execute('SELECT payload FROM queue ORDER BY capture_seq')]


def test_full_queue_keeps_newest_prefix_retirement_survives_restart(tmp_path):
    box = make_box(tmp_path)
    samples = [box.enqueue(NOW+i*1000, VALUES) for i in range(9)]
    assert rows(box) == samples[-3:], 'full queue failed to retain latest three immutable samples'
    reopened = ReliableOutbox(box.path,3,**box.identity,audit_limit=20,byte_limit=1048576)
    assert rows(reopened) == samples[-3:], 'restart lost newest samples or changed identity'
    status = reopened.retention_status()
    assert status['unconfirmed_evicted_total'] == status['audit_evicted_total'] == 6, 'loss summary missing'
    assert status['last']['first_seq'] == status['last']['last_seq'] == 6, 'last retirement span wrong'
    assert reopened.latest_timestamp() == NOW+8000, 'clock high water regressed'


def test_full_audit_recycles_committed_history_and_accepts_new_sample(tmp_path):
    box = make_box(tmp_path,audit_limit=1)
    old = box.enqueue(NOW,VALUES)
    box.committed(old['sample_id'],old['payload_hash'])
    new = box.enqueue(NOW+1000,VALUES)
    assert rows(box) == [new] and new['capture_seq'] == 2, 'ACK history blocked acquisition'
    status = box.retention_status()
    assert status['audit_evicted_total'] == status['committed_audit_evicted_total'] == 1, 'committed retirement unrecorded'
    assert status['unconfirmed_evicted_total'] == 0, 'committed audit prune reported payload loss'


def test_full_audit_evicts_oldest_pending_even_when_queue_has_room(tmp_path):
    box = make_box(tmp_path,limit=10,audit_limit=2)
    samples = [box.enqueue(NOW+i*1000,VALUES) for i in range(3)]
    assert rows(box) == samples[-2:] and box.audit_count() == 2, 'audit full still rejects or deletes wrong row'
    assert box.retention_status()['unconfirmed_evicted_total'] == 1, 'pending retirement hidden'


def test_oldest_order_uses_capture_sequence_not_timestamp_or_ack_order(tmp_path):
    box = make_box(tmp_path,limit=10,audit_limit=2)
    first = box.enqueue(NOW+9000,VALUES)
    second = box.enqueue(NOW,VALUES)
    box.committed(second['sample_id'],second['payload_hash'])
    new = box.enqueue(NOW+10000,VALUES)
    assert rows(box) == [new], 'oldest capture sequence not evicted'
    assert box.retention_status()['last']['sample_id'] == first['sample_id'], 'ACK order overrode acquisition order'


def test_quarantine_can_be_retired_but_is_not_counted_committed(tmp_path):
    box = make_box(tmp_path,limit=1)
    old = box.enqueue(NOW,VALUES)
    box.quarantine(old['sample_id'],old['payload_hash'],'conflict')
    new = box.enqueue(NOW+1000,VALUES)
    assert rows(box) == [new], 'quarantine permanently blocked latest telemetry'
    status = box.retention_status()
    assert status['quarantine_evicted_total'] == status['unconfirmed_evicted_total'] == 1, 'quarantine counted delivered'
    assert status['committed_audit_evicted_total'] == 0, 'retirement manufactured ACK'


@pytest.mark.parametrize('resolution',['committed','quarantine'])
def test_late_resolution_of_retired_id_cannot_delete_or_modify_newest(tmp_path,resolution):
    box = make_box(tmp_path,limit=1)
    old = box.enqueue(NOW,VALUES)
    new = box.enqueue(NOW+1000,VALUES)
    resolve = getattr(box,resolution)
    args = (old['sample_id'],old['payload_hash']) + (('rejected',) if resolution=='quarantine' else ())
    assert resolve(*args) is False, 'retired source falsely resolved'
    assert rows(box) == [new], 'late ACK touched replacement sample'
    with pytest.raises(ValueError):
        box.committed(new['sample_id'],old['payload_hash'])
    assert rows(box) == [new], 'mismatched hash touched newest row'


@pytest.mark.parametrize('values',[dict(VALUES,voltage=True),dict(VALUES,pad='x'*16385)])
def test_invalid_incoming_sample_never_evicts_old_data(tmp_path,values):
    box = make_box(tmp_path,limit=1)
    old = box.enqueue(NOW,VALUES)
    with pytest.raises(ValueError):
        box.enqueue(NOW+1000,values)
    assert rows(box) == [old], 'invalid input evicted valid source'
    assert box.retention_status()['audit_evicted_total'] == 0, 'invalid input advanced retirement counter'


@pytest.mark.parametrize('bad_time',[-1000,9223372036854776000,10**100*1000,1,True])
def test_invalid_source_time_never_retires_data_or_breaks_restart(tmp_path,bad_time):
    box=make_box(tmp_path,limit=1)
    old=box.enqueue(NOW,VALUES)
    with pytest.raises(ValueError):
        box.enqueue(bad_time,VALUES)
    reopened=ReliableOutbox(box.path,1,**box.identity)
    assert rows(reopened)==[old] and reopened.retention_status()['audit_evicted_total']==0, 'invalid time lost source or restart state'


def test_maximum_aligned_local_timestamp_remains_restartable(tmp_path):
    box=make_box(tmp_path,limit=1)
    sample=box.enqueue((2**63-1)//1000*1000,VALUES)
    reopened=ReliableOutbox(box.path,1,**box.identity)
    assert rows(reopened)==[sample], 'valid local int64 time boundary not durable'


def test_new_insert_failure_rolls_back_eviction_counters_sequence_and_window(tmp_path):
    box = make_box(tmp_path,limit=1)
    old = box.enqueue(NOW,VALUES)
    with box.connect() as db:
        db.execute("CREATE TRIGGER reject_insert BEFORE INSERT ON queue BEGIN SELECT RAISE(ABORT,'test insert failed'); END")
        before = dict(db.execute('SELECT key,value FROM metadata'))
    with pytest.raises(sqlite3.IntegrityError):
        box.enqueue(NOW+600000000000,VALUES)
    with box.connect() as db:
        assert dict(db.execute('SELECT key,value FROM metadata')) == before, 'failed insert committed retirement metadata'
        assert db.execute('SELECT COUNT(*) FROM windows').fetchone()[0] == 1, 'failed insert left orphan window'
    assert rows(box) == [old], 'failed new write lost prior sample'


def test_real_sqlite_full_rotates_oldest_prefix_and_keeps_newest_hashes(tmp_path):
    box = make_box(tmp_path,limit=100,audit_limit=100,byte_limit=65536)
    expected = [box.enqueue(NOW+i*1000,dict(VALUES,pad='x'*12000)) for i in range(20)]
    actual = rows(box)
    assert actual and len(actual)<20 and actual == expected[-len(actual):], 'byte pressure did not keep latest suffix'
    assert box.retention_status()['unconfirmed_evicted_total'] == 20-len(actual), 'FULL loss count incorrect'
    assert box.path.stat().st_size <= 65536, 'SQLite exceeded byte budget'
    with box.connect() as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'FULL retry corrupted queue'
        assert dict(db.execute('SELECT key,value FROM metadata'))['sequence'] == '20', 'FULL retry consumed extra seq'


def test_unused_window_history_is_bounded_with_rolling_queue(tmp_path):
    box = make_box(tmp_path,limit=2,audit_limit=2)
    for i in range(35):
        box.enqueue(NOW+i*300000000000,VALUES)
    with box.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM windows').fetchone()[0] == 2, 'windows grew independently of history budget'


def test_unreclaimable_sqlite_full_rolls_back_all_attempted_retirements(tmp_path):
    box=make_box(tmp_path,limit=1,byte_limit=65536)
    old=box.enqueue(NOW,VALUES)
    with box.connect() as db:
        db.execute("INSERT INTO metadata VALUES ('reserved-test',?)",('x'*20000,))
        before=dict(db.execute('SELECT key,value FROM metadata'))
    with pytest.raises(sqlite3.OperationalError) as failure:
        box.enqueue(NOW+1000,dict(VALUES,pad='x'*16000))
    assert failure.value.sqlite_errorcode==sqlite3.SQLITE_FULL, 'failure did not exercise actual FULL rollback'
    with box.connect() as db:
        assert dict(db.execute('SELECT key,value FROM metadata'))==before, 'FULL committed counters or sequence'
    assert rows(box)==[old], 'unsavable new sample destroyed old sample'


def test_concurrent_enqueue_serializes_retirement_and_never_reuses_sequence(tmp_path):
    box = make_box(tmp_path,limit=3,audit_limit=3)
    with ThreadPoolExecutor(max_workers=3) as pool:
        samples = list(pool.map(lambda i:box.enqueue(NOW+i*1000,VALUES),range(15)))
    samples.sort(key=lambda item:item['capture_seq'])
    assert [s['capture_seq'] for s in samples] == list(range(1,16)), 'parallel acquisition reused seq'
    assert rows(box) == samples[-3:], 'parallel capacity update kept wrong suffix'
    assert box.retention_status()['unconfirmed_evicted_total'] == 12, 'parallel retirement counter lost updates'


def test_legacy_schema_two_upgrades_without_losing_sample(tmp_path):
    old=make_box(tmp_path)
    sample=old.enqueue(NOW,VALUES)
    with old.connect() as db:
        db.execute("DELETE FROM metadata WHERE key='retention'")
        db.execute('PRAGMA user_version=2')
    new=ReliableOutbox(old.path,3,**old.identity,byte_limit=1048576,audit_limit=20)
    assert rows(new)==[sample] and new.retention_status()['audit_evicted_total']==0, 'upgrade lost source identity'
    with new.connect() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==3, 'new policy lacks downgrade guard'


def test_schema_three_missing_retirement_summary_fails_closed(tmp_path):
    box=make_box(tmp_path)
    with box.connect() as db:
        db.execute("DELETE FROM metadata WHERE key='retention'")
    with pytest.raises(ValueError):
        ReliableOutbox(box.path,3,**box.identity)


def test_real_full_schema_two_upgrades_without_room_for_indexes_and_keeps_collecting(tmp_path,caplog):
    fixture=Path(__file__).parent/'fixtures/schema2-full.db'
    path=tmp_path/'legacy'/'q.db';path.parent.mkdir()
    path.write_bytes(fixture.read_bytes())
    with sqlite3.connect(path) as db:
        identity=json.loads(db.execute("SELECT value FROM metadata WHERE key='identity'").fetchone()[0])
        before=[json.loads(r[0]) for r in db.execute('SELECT payload FROM queue ORDER BY capture_seq')]
        assert db.execute('PRAGMA user_version').fetchone()[0]==2, 'fixture is not real old schema'
        assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name LIKE 'audit_%'").fetchone()[0]==0, 'fixture already has new indexes'
    box=ReliableOutbox(path,100,**identity,byte_limit=65536,audit_limit=100)
    assert rows(box)==before, 'index upgrade deleted old source before new write'
    assert 'retention_indexes_deferred' in caplog.text, 'fixture failed to exercise index space exhaustion'
    newest=box.enqueue(NOW+2000,dict(VALUES,pad='x'*12000))
    actual=rows(box)
    assert actual and actual[-1]==newest and newest['capture_seq']==3, 'full legacy queue cannot continue latest collection'
    assert actual==(before+[newest])[-len(actual):], 'legacy rotation lost chronological suffix'
    assert box.path.stat().st_size<=65536, 'deferred index path exceeded quota'
