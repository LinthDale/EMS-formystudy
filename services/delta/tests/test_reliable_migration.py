"""Offline conversion preserves only existing v1 pending samples, once."""
import sqlite3
from uuid import uuid4
import pytest
from delta_device.delivery import Outbox, encode_line
from delta_device.migrate_delivery import migrate
from delta_device.reliable_store import ReliableOutbox


def test_v1_migration_preserves_pending_times_values_and_clock_high_water(tmp_path):
    source = Outbox(tmp_path/'old'/'q.db', 10, 'd1')
    snapshot = dict(voltage=230, current=5, power_kw=1, energy_kwh=100)
    for index in range(3):
        ns = 1794474000000000000 + index * 1000
        source.enqueue(ns, encode_line('d1', snapshot, ns), snapshot)
    source.ack(source.pending(10)[-1][0])
    original = source.path.read_bytes()
    destination = tmp_path/'new'/'q.db'
    identity = dict(gateway_id='g1', device_id='d1', stream_id=str(uuid4()), config_revision='r1', profile_version='v135')
    result = migrate(source.path, destination, 10, identity, source_stopped=True)
    box = ReliableOutbox(destination, 10, **identity)
    with box.connect() as db:
        rows = db.execute('SELECT payload FROM queue ORDER BY capture_seq').fetchall()
    assert result['rows'] == len(rows) == 2, 'migration resurrected ACKed row or lost pending'
    assert box.latest_timestamp() == 1794474000000002000, 'migration lost latest acquisition high water'
    assert source.path.read_bytes() == original, 'migration modified source'
    with pytest.raises(FileExistsError):
        migrate(source.path, destination, 10, identity, source_stopped=True)
    assert box.pending_count() == 2, 'repeat migration duplicated queue'


def test_migration_requires_stopped_source_and_never_publishes_partial_destination(tmp_path):
    source = Outbox(tmp_path/'old'/'q.db', 10, 'd1')
    source.enqueue(1794474000000000000, 'corrupted-ilp', dict(voltage=230, current=5, power_kw=1, energy_kwh=100))
    target = tmp_path/'new'/'q.db'
    identity = dict(gateway_id='g1', device_id='d1', stream_id=str(uuid4()), config_revision='r1', profile_version='v135')
    with pytest.raises(ValueError):
        migrate(source.path, target, 10, identity, source_stopped=False)
    with pytest.raises(ValueError):
        migrate(source.path, target, 10, identity, source_stopped=True)
    assert not target.exists(), 'partial conversion became a runnable queue'


def test_migration_byte_pressure_never_publishes_a_silently_rotated_subset(tmp_path):
    source=Outbox(tmp_path/'old'/'q.db',10,'d1')
    snapshot=dict(voltage=230,current=5,power_kw=1,energy_kwh=100,pad='x'*12000)
    for i in range(5):
        ns=1794474000000000000+i*1000
        source.enqueue(ns,encode_line('d1',snapshot,ns),snapshot)
    before=source.path.read_bytes()
    target=tmp_path/'new'/'q.db'
    identity=dict(gateway_id='g1',device_id='d1',stream_id=str(uuid4()),config_revision='r1',profile_version='v135')
    with pytest.raises(OverflowError):
        migrate(source.path,target,10,identity,source_stopped=True,byte_limit=65536)
    assert not target.exists() and source.path.read_bytes()==before, 'partial migration published or source changed'
