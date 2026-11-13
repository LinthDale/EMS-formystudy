"""Short real process/storage failures for ADR-045; never a time-based soak."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time
from uuid import uuid4

import pytest

from delta_device.reliable_store import ReliableOutbox

pytestmark = pytest.mark.integration
NOW = 1794474000000000000
VALUES = dict(voltage=230,current=5,power_kw=1,energy_kwh=100)


def emit(name, **result):
    directory=os.environ.get('EDGE_V2_EVIDENCE')
    if directory:
        Path(directory,name+'.json').write_text(json.dumps(dict(passed=True,**result),indent=2))


def box_at(tmp_path,limit=1):
    return ReliableOutbox(tmp_path/'queue'/'q.db',limit,'g1','d1',str(uuid4()),'r1','v135',
                          byte_limit=1048576,audit_limit=10)


def rows(box):
    with box.connect() as db:
        return [json.loads(row[0]) for row in db.execute('SELECT payload FROM queue ORDER BY capture_seq')]


def child(path,stage,marker,original_digest):
    """Pause an owned real SQLite transaction so its parent can SIGKILL it."""
    with closing(sqlite3.connect(path)) as db:
        identity=json.loads(db.execute("SELECT value FROM metadata WHERE key='identity'").fetchone()[0])
    box=ReliableOutbox(path,1,**identity,byte_limit=1048576,audit_limit=10)
    # Exclude constructor commits from proof that this transaction spilled pages.
    baseline_digest=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    original_connect=box.connect
    def pause(db=None,committed_sample=None):
        journal=Path(str(path)+'-journal')
        observed_digest=hashlib.sha256(Path(path).read_bytes()).hexdigest()
        temporary=Path(str(marker)+'.tmp')
        temporary.write_text(json.dumps(dict(pid=os.getpid(),stage=stage,
            journal_bytes=journal.stat().st_size if journal.exists() else 0,
            baseline_stage='after_constructor',baseline_sha256=baseline_digest,observed_sha256=observed_digest,
            constructor_changed_file=baseline_digest!=original_digest,
            main_file_changed=observed_digest!=baseline_digest,committed_sample=committed_sample)))
        os.replace(temporary,marker)
        while True:
            time.sleep(.1)
    @contextmanager
    def crash_connect():
        with original_connect() as db:
            db.execute('PRAGMA cache_size=1')  # Force dirty-page spill, not just RAM loss.
            yield db
            if stage=='before_commit':
                pause(db)
    box.connect=crash_connect
    retire=box._retire
    def retire_then_pause(db,*args):
        result=retire(db,*args)
        if stage=='after_retire':
            pause(db)
        return result
    box._retire=retire_then_pause
    sample=box.enqueue(NOW+1000,dict(VALUES,voltage=231))
    pause(committed_sample=sample)


@pytest.mark.parametrize('stage',['after_retire','before_commit','after_commit'])
def test_sigkill_during_rotation_recovers_exact_transaction_boundary(tmp_path,stage):
    box=box_at(tmp_path)
    old=box.enqueue(NOW,VALUES)
    before=hashlib.sha256(box.path.read_bytes()).hexdigest()
    marker=tmp_path/'ready.json'
    process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--child',str(box.path),stage,str(marker),before],
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        deadline=time.monotonic()+8
        while not marker.exists() and process.poll() is None and time.monotonic()<deadline:
            time.sleep(.01)
        assert marker.exists(), 'owned child did not reach the required transaction boundary'
        observed=json.loads(marker.read_text())
        assert observed['pid']==process.pid and observed['stage']==stage, 'wrong process or transaction marker'
        if stage!='after_commit':
            assert observed['journal_bytes']>0 and observed['main_file_changed'], 'no actual dirty-page/journal crash window'
        process.kill()
        stdout,stderr=process.communicate(timeout=5)
        assert process.returncode==-signal.SIGKILL, 'child did not actually terminate by SIGKILL'
    finally:
        if process.poll() is None:
            process.kill();process.communicate(timeout=5)
    reopened=ReliableOutbox(box.path,1,**box.identity,byte_limit=1048576,audit_limit=10)
    actual=rows(reopened)
    status=reopened.retention_status()
    if stage=='after_commit':
        assert actual==[observed['committed_sample']] and actual[0]['capture_seq']==2 and actual[0]['measurements']['voltage']==231, 'committed replacement identity/hash lost after crash'
        assert status['unconfirmed_evicted_total']==1, 'committed retirement metadata lost'
    else:
        assert actual==[old] and status['unconfirmed_evicted_total']==0, 'uncommitted rotation survived crash or old sample was lost'
    with reopened.connect() as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok', 'crash corrupted queue'
        assert db.execute('SELECT COUNT(*) FROM windows').fetchone()[0]==1, 'crash orphaned a window'
    next_sample=reopened.enqueue(NOW+2000,VALUES)
    assert next_sample['capture_seq']==actual[0]['capture_seq']+1, 'recovery skipped or reused sequence'
    emit('crash-'+stage,child_exit=process.returncode,observed=observed,
         recovered_ids=[s['sample_id'] for s in actual],recovered_sequence=actual[0]['capture_seq'],
         retirement=status,next_sequence=next_sample['capture_seq'],integrity='ok',
         committed_identity_preserved=actual==[observed['committed_sample']] if stage=='after_commit' else None)
    directory=os.environ.get('EDGE_V2_EVIDENCE')
    if directory:
        Path(directory,'crash-'+stage+'-child.log').write_text(stdout+stderr)


def test_sqlite_busy_retains_old_sample_and_recovers_without_false_retirement(tmp_path):
    box=box_at(tmp_path);old=box.enqueue(NOW,VALUES)
    lock=sqlite3.connect(box.path)
    lock.execute('BEGIN IMMEDIATE')
    started=time.monotonic()
    try:
        with pytest.raises(sqlite3.OperationalError) as error:
            box.enqueue(NOW+1000,VALUES)
        assert error.value.sqlite_errorcode==sqlite3.SQLITE_BUSY, 'not an actual SQLite writer lock timeout'
    finally:
        lock.rollback();lock.close()
    elapsed=time.monotonic()-started
    assert rows(box)==[old] and box.retention_status()['audit_evicted_total']==0, 'BUSY deleted source or recorded retirement'
    new=box.enqueue(NOW+2000,VALUES)
    assert rows(box)==[new] and new['capture_seq']==2, 'failed writer lock attempt consumed sequence'
    emit('sqlite-busy',sqlite_error='SQLITE_BUSY',elapsed_seconds=elapsed,old_preserved=True,
         next_sequence=2,retirement_after_recovery=box.retention_status())


def test_readonly_database_retains_old_sample_then_recovers(tmp_path):
    box=box_at(tmp_path);old=box.enqueue(NOW,VALUES)
    box.path.chmod(0o400)
    try:
        with pytest.raises(sqlite3.OperationalError) as error:
            box.enqueue(NOW+1000,VALUES)
        assert error.value.sqlite_errorcode&255==sqlite3.SQLITE_READONLY, 'not a real filesystem permission failure'
    finally:
        box.path.chmod(0o600)
    assert rows(box)==[old] and box.retention_status()['audit_evicted_total']==0, 'readonly failure destroyed source'
    new=box.enqueue(NOW+2000,VALUES)
    assert rows(box)==[new] and new['capture_seq']==2, 'permission recovery did not preserve sequence'
    emit('sqlite-readonly',sqlite_error='SQLITE_READONLY',old_preserved=True,next_sequence=2)


def test_online_backup_remains_coherent_while_rotation_commits_during_copy(tmp_path):
    box=box_at(tmp_path,limit=5)
    for index in range(12):
        box.enqueue(NOW+index*1000,VALUES)
    backup=tmp_path/'backup.db'
    advanced=[]
    def rotate():
        for index in range(12,20):
            box.enqueue(NOW+index*1000,VALUES)
        return True
    with ThreadPoolExecutor(max_workers=1) as pool:
        def progress(status,remaining,total):
            if not advanced and status==sqlite3.SQLITE_OK:
                advanced.append(pool.submit(rotate).result(timeout=8))
        with closing(sqlite3.connect(box.path.as_uri()+'?mode=ro',uri=True)) as source,closing(sqlite3.connect(backup)) as target:
            source.backup(target,pages=1,progress=progress,sleep=.01)
    assert advanced==[True], 'rotation did not actually commit during the backup operation'
    copy=ReliableOutbox(backup,5,**box.identity,byte_limit=1048576,audit_limit=10)
    copied=rows(copy)
    assert [s['capture_seq'] for s in copied]==[16,17,18,19,20], 'online backup mixed transaction generations'
    status=copy.retention_status()
    assert status['unconfirmed_evicted_total']==15 and copy.audit_count()==5, 'backup mixed retirement summary and samples'
    with copy.connect() as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok', 'online backup damaged SQLite'
        assert int(dict(db.execute('SELECT key,value FROM metadata'))['sequence'])==20, 'backup sequence not coherent'
    emit('online-backup',rotation_committed_during_copy=True,retained_sequences=[16,17,18,19,20],
         retirement=status,integrity='ok',scope='SQLite online backup consistency; not a restore stream/PITR drill')


if __name__=='__main__' and len(sys.argv)==6 and sys.argv[1]=='--child':
    child(Path(sys.argv[2]),sys.argv[3],sys.argv[4],sys.argv[5])
