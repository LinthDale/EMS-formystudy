"""FR-2104/2106 counterexamples: broker ACK cannot delete durable samples."""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest

from delta_device.reliable_wire import canonical, decode, validate_sample, AckState
from delta_device.reliable_store import ReliableOutbox
from delta_device.delivery import Outbox

NOW_US = 1794474000000000
STREAM = 'f15f8bb9-bb57-4670-8aa9-f42d32a52844'


def box_at(tmp_path, limit=10):
    return ReliableOutbox(tmp_path / 'v2' / 'queue.db', limit, 'gateway-a', 'device-a',
                          STREAM, 'r1', 'delta-v135', byte_limit=1048576, audit_limit=20)


def enqueue(box):
    return box.enqueue(NOW_US * 1000, dict(voltage=230, current=5, power_kw=1, energy_kwh=100))


def response(state, item, status='committed'):
    return dict(schema_version=2, gateway_id='gateway-a', session_challenge=state.challenge,
                recovery_generation=state.generation, batch_id=state.batch_id,
                results=[dict(sample_id=item['sample_id'], payload_hash=item['payload_hash'],
                              status=status, **({'committed_at': '2026-11-12T09:00:00+00:00'}
                                                if status == 'committed' else {'error_code': 'conflict'}))])


def active_state(item):
    state = AckState('gateway-a')
    state.connect()
    state.establish(dict(schema_version=2, gateway_id='gateway-a',
                         session_challenge=state.challenge, recovery_generation=str(uuid4())))
    state.prepare(item)
    return state


def test_restart_preserves_original_identity_hash_and_sequence(tmp_path):
    box = box_at(tmp_path)
    first = enqueue(box)
    again = box_at(tmp_path)
    assert again.pending()[0] == first, 'restart changed immutable sample'
    second = again.enqueue((NOW_US + 1) * 1000, first['measurements'])
    assert second['capture_seq'] == first['capture_seq'] + 1, 'sequence reset after restart'
    assert second['sample_id'] != first['sample_id'], 'sample UUID reused'
    unsigned = {k: v for k, v in first.items() if k != 'payload_hash'}
    assert first['payload_hash'] == hashlib.sha256(canonical(unsigned)).hexdigest(), 'hash differs'
    assert again.latest_timestamp() == (NOW_US + 1) * 1000, 'source clock high water lost'


def test_broker_ack_alone_and_unrelated_commit_never_remove_pending(tmp_path):
    box = box_at(tmp_path)
    item = enqueue(box)
    with pytest.raises(ValueError):
        box.committed(item['sample_id'], '0' * 64)
    assert box.pending_count() == 1, 'unverified row deleted'
    box.committed(item['sample_id'], item['payload_hash'])
    assert box.pending_count() == 0, 'validated commit not removed'
    assert box.audit_count() == 1, 'ACK discarded audit identity'
    with box.connect() as db:
        assert db.execute('SELECT state FROM audit').fetchone()[0] == 'committed', 'audit not atomic'


@pytest.mark.parametrize('changed,value', [('gateway_id', 'gateway-b'), ('stream_id', str(uuid4())),
                                         ('config_revision', 'r2'), ('profile_version', 'other')])
def test_queue_identity_cannot_be_rebound(tmp_path, changed, value):
    box = box_at(tmp_path)
    enqueue(box)
    args = dict(gateway_id='gateway-a', device_id='device-a', stream_id=STREAM,
                config_revision='r1', profile_version='delta-v135')
    args[changed] = value
    with pytest.raises(ValueError):
        ReliableOutbox(box.path, 10, **args, byte_limit=1048576, audit_limit=20)


def test_v1_and_v2_refuse_each_others_database(tmp_path):
    box = box_at(tmp_path)
    enqueue(box)
    with pytest.raises(ValueError):
        Outbox(box.path, 10, 'device-a')
    legacy = Outbox(tmp_path / 'v1' / 'queue.db', 10, 'device-a')
    with pytest.raises(ValueError):
        ReliableOutbox(legacy.path, 10, 'gateway-a', 'device-a', STREAM, 'r1', 'delta-v135')


def test_quarantine_shares_capacity_and_oldest_is_retired_for_newest(tmp_path):
    box = box_at(tmp_path, limit=1)
    item = enqueue(box)
    box.quarantine(item['sample_id'], item['payload_hash'], 'conflict')
    assert box.pending_count() == 1 and not box.pending(), 'quarantine vanished or hot retried'
    newest = enqueue(box)
    assert box.pending() == [newest], 'full quarantine blocked newest sample'
    with box.connect() as db:
        assert db.execute('PRAGMA journal_mode').fetchone()[0] == 'delete', 'unsafe journal mode'
        assert db.execute('PRAGMA synchronous').fetchone()[0] == 3, 'synchronous is not EXTRA'
        assert db.execute('SELECT COUNT(*) FROM queue').fetchone()[0] == 1, 'queue exceeded cap'
    assert box.retention_status()['quarantine_evicted_total'] == 1, 'retired quarantine hidden'


def test_failed_enqueue_does_not_advance_sequence(tmp_path):
    box = box_at(tmp_path)
    with pytest.raises(ValueError):
        box.enqueue(NOW_US * 1000, dict(voltage=True, current=5, power_kw=1, energy_kwh=100))
    assert enqueue(box)['capture_seq'] == 1, 'failed transaction advanced sequence'


@pytest.mark.parametrize('bad', [b'{"a":1,"a":2}', b'{"x":NaN}', b'[' * 40 + b']' * 40,
                                b'"' + b'x' * 65536 + b'"'])
def test_untrusted_json_rejects_duplicates_nonfinite_depth_and_size(bad):
    with pytest.raises(ValueError):
        decode(bad)


def test_sample_recomputes_hash_and_rejects_unknown_fields(tmp_path):
    item = enqueue(box_at(tmp_path))
    assert validate_sample(item, 'gateway-a') == item, 'canonical sample rejected'
    for name, value in [('capture_seq', True), ('unknown', 1), ('sampled_at_us', 2**63),
                        ('payload_hash', '0' * 64), ('gateway_id', 'gateway-b')]:
        bad = dict(item, **{name: value})
        with pytest.raises(ValueError):
            validate_sample(bad, 'gateway-a')
    bad = copy.deepcopy(item)
    bad['measurements']['voltage'] = 240
    with pytest.raises(ValueError):
        validate_sample(bad, 'gateway-a')


@pytest.mark.parametrize('huge', [10**1000, -(10**1000), float('inf'), float('nan')])
def test_hostile_numeric_values_are_bounded_before_float_conversion(tmp_path, huge):
    box = box_at(tmp_path)
    item = enqueue(box)
    item['measurements']['voltage'] = huge
    with pytest.raises(ValueError):
        validate_sample(item, 'gateway-a')
    with pytest.raises(ValueError):
        box.enqueue((NOW_US + 1) * 1000, item['measurements'])


@pytest.mark.parametrize('field,value', [('gateway_id', 'other'), ('session_challenge', str(uuid4())),
    ('recovery_generation', str(uuid4())), ('batch_id', str(uuid4()))])
def test_wrong_ack_envelope_never_accepts_commit(tmp_path, field, value):
    item = enqueue(box_at(tmp_path))
    state = active_state(item)
    ack = response(state, item)
    ack[field] = value
    assert state.accept(ack) is None, 'foreign/stale ACK accepted'


def test_ack_requires_whole_valid_reply_and_current_connection(tmp_path):
    item = enqueue(box_at(tmp_path))
    state = active_state(item)
    ack = response(state, item)
    assert state.accept(ack, retained=True) is None, 'retained ACK accepted'
    bad = copy.deepcopy(ack)
    bad['results'].append(dict(bad['results'][0]))
    assert state.accept(bad) is None, 'duplicate result accepted'
    bad = copy.deepcopy(ack)
    bad['results'][0]['payload_hash'] = '0' * 64
    assert state.accept(bad) is None, 'wrong hash accepted'
    assert state.accept(ack) == 'committed', 'valid commit rejected'
    state.disconnect()
    assert state.accept(ack) is None, 'disconnect left old batch valid'
    state.connect()
    assert state.accept(ack) is None, 'old callback crossed connection boundary'


def test_retained_or_wrong_challenge_cannot_establish_session():
    state = AckState('gateway-a')
    state.connect()
    reply = dict(schema_version=2, gateway_id='gateway-a', session_challenge=state.challenge,
                 recovery_generation=str(uuid4()))
    assert not state.establish(reply, retained=True), 'retained session accepted'
    assert not state.establish(dict(reply, session_challenge=str(uuid4()))), 'old challenge accepted'
    assert state.establish(reply), 'fresh authenticated session rejected'


def test_sender_requires_application_ack_after_broker_puback(tmp_path, monkeypatch):
    import threading
    from types import SimpleNamespace
    from delta_device import reliable_sender
    box = box_at(tmp_path)
    item = enqueue(box)
    client = SimpleNamespace(publish=lambda *a, **kw: SimpleNamespace(rc=0))
    monkeypatch.setattr(reliable_sender.mqtt, 'Client', lambda *a, **kw: client)
    monkeypatch.setattr(reliable_sender, 'connection_policy', lambda *a: None)
    sender = reliable_sender.ReliableSender(box, {'client_id': 'qa'}, 'demo', ack_timeout=.01)
    sender.state = active_state(item)
    sender.subscribed.set()
    sender.session_ready.set()
    sender.on_publish(client, None, 1, 0, None)
    assert not sender.step(threading.Event()), 'PUBACK treated as central commit'
    assert box.pending_count() == 1, 'broker-only ACK removed durable sample'


def test_v2_config_requires_registered_identity_and_mtls_in_field(tmp_path):
    from delta_device.config import validate
    from test_delivery import config
    value = config(tmp_path)
    value['delivery'] = dict(protocol=2, gateway_id='gateway-a', stream_id=STREAM,
                             config_revision='r1', profile_version='delta-v135')
    assert validate(value)['batch_size'] == 1, 'v2 did not bound batch to one'
    for field in ('gateway_id', 'stream_id', 'config_revision', 'profile_version'):
        bad = copy.deepcopy(value)
        del bad['delivery'][field]
        with pytest.raises(ValueError):
            validate(bad)
    value.update(mode='field', device_id='real-device')
    value['mqtt'].update(tls=True, username_env='USER', password_env='PASS')
    with pytest.raises(ValueError):
        validate(value)


def test_publish_callback_does_not_wait_for_session_lock(tmp_path, monkeypatch):
    import threading
    from types import SimpleNamespace
    from delta_device import reliable_sender
    monkeypatch.setattr(reliable_sender.mqtt, 'Client', lambda *a, **kw: SimpleNamespace())
    monkeypatch.setattr(reliable_sender, 'connection_policy', lambda *a: None)
    sender = reliable_sender.ReliableSender(box_at(tmp_path), {'client_id': 'qa'}, 'demo')
    with sender.lock:
        callback = threading.Thread(target=sender.on_publish, args=(None, None, 1, 0, None), daemon=True)
        callback.start()
        callback.join(.5)
        assert not callback.is_alive(), 'Paho callback needs session lock, allowing mutex inversion'
    assert sender.broker_acks == 1, 'diagnostic ACK lost'


def test_incompatible_v2_schema_and_missing_identity_fail_at_startup(tmp_path):
    box = box_at(tmp_path)
    with box.connect() as db:
        db.execute('ALTER TABLE queue DROP COLUMN snapshot')
    with pytest.raises(ValueError):
        box_at(tmp_path)
    other = tmp_path / 'other'
    box = box_at(other)
    with box.connect() as db:
        db.execute("DELETE FROM metadata WHERE key='identity'")
    with pytest.raises(ValueError):
        box_at(other)
