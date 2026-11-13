"""Never reset a damaged existing v2/v3 queue into a new empty database."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest
from delta_device.reliable_store import ReliableOutbox

pytestmark=pytest.mark.integration


@pytest.mark.parametrize('damage',['header','truncated','zero-length','empty-sqlite'])
def test_damaged_existing_queue_fails_without_reset_or_modification(tmp_path,damage):
    path=tmp_path/'source'/'q.db'
    identity=dict(gateway_id='g1',device_id='d1',stream_id=str(uuid4()),config_revision='r1',profile_version='v135')
    box=ReliableOutbox(path,5,**identity)
    original=box.enqueue(1794474000000000000,dict(voltage=230,current=5,power_kw=1,energy_kwh=100))
    good=path.read_bytes()
    if damage=='header':
        path.write_bytes(b'BROKEN-SQLITE!!!'+good[16:])
    elif damage=='truncated':
        path.write_bytes(good[:len(good)//2])
    elif damage=='zero-length':
        path.write_bytes(b'')
    else:
        replacement=tmp_path/'replacement.db'
        with closing(sqlite3.connect(replacement)) as db:
            db.execute('PRAGMA user_version=0');db.commit()
        path.write_bytes(replacement.read_bytes())
    damaged=path.read_bytes()
    with pytest.raises((ValueError,sqlite3.DatabaseError)) as error:
        ReliableOutbox(path,5,**identity)
    assert path.read_bytes()==damaged, 'opening damaged queue changed bytes or created fresh schema'
    assert not Path(str(path)+'-journal').exists(), 'failed initialization left a new journal'
    evidence=os.environ.get('EDGE_V2_EVIDENCE')
    if evidence:
        Path(evidence,'corruption-'+damage+'.json').write_text(json.dumps(dict(passed=True,
            damage=damage,original_sample_id=original['sample_id'],damaged_bytes=len(damaged),
            before_sha256=hashlib.sha256(damaged).hexdigest(),after_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            error_kind=type(error.value).__name__,empty_database_recreated=False),indent=2))


def test_genuinely_new_path_still_initializes_and_sequences_from_one(tmp_path):
    path=tmp_path/'new'/'q.db'
    box=ReliableOutbox(path,5,'g1','d1',str(uuid4()),'r1','v135')
    sample=box.enqueue(1794474000000000000,dict(voltage=230,current=5,power_kw=1,energy_kwh=100))
    assert sample['capture_seq']==1 and box.pending()==[sample], 'new-path initialization was broken by corruption guard'
