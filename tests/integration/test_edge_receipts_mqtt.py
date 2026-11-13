"""Private real Mosquitto -> receiver -> PostgreSQL -> application ACK tests."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'services/delta'), str(ROOT / 'services/edge-receiver')]
from delta_device.reliable_sender import ReliableSender
from delta_device.reliable_store import ReliableOutbox
from delta_device.reliable_wire import canonical
from edge_receiver.receiver import Receiver
from edge_receiver.store import ReceiptStore

pytestmark = pytest.mark.integration


def wait_for(predicate, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.02)
    raise AssertionError('private MQTT observation deadline')


def source_time():
    return time.time_ns() // 1000 * 1000


def configured(tmp_path, gateway=None):
    dsn = os.environ.get('EDGE_V2_TEST_DSN')
    if not dsn or not os.environ.get('EMS_V2_DEMO_NETNS'):
        pytest.skip('requires explicitly owned network-none MQTT and DB')
    gateway = gateway or 'g-' + uuid4().hex[:12]
    box = ReliableOutbox(tmp_path / 'queue' / 'q.db', 100, gateway, 'd1', str(uuid4()), 'r1', 'delta-v135')
    gen = tmp_path / 'generation'
    gen.write_text(str(uuid4()))
    binding = {k: box.identity[k] for k in ('stream_id', 'config_revision', 'profile_version')}
    binding.update(not_before_us=1, not_after_us=2**63 - 1)
    mqtt = dict(host='127.0.0.1', port=1883, client_id='receiver-' + gateway)
    config = dict(mode='demo', mqtt=mqtt, generation_file=str(gen), dsn_env='EDGE_V2_TEST_DSN',
                  db_timeout_seconds=1, bindings={gateway: {'d1': binding}})
    pki=os.environ.get('EDGE_V2_TEST_PKI')
    if pki and (Path(pki)/'pg-client/ca.crt').exists():
        config['db_tls']=dict(ca_file=pki+'/pg-client/ca.crt',cert_file=pki+'/pg-client/postgres.crt',
                              key_file=pki+'/pg-client/postgres.key')
    sender_mqtt = dict(mqtt, client_id='sender-' + gateway)
    return box, config, sender_mqtt


@contextmanager
def running_receiver(config):
    receiver = Receiver(config)
    errors = []
    def run():
        try:
            asyncio.run(receiver.run())
        except Exception as exc:
            errors.append(type(exc).__name__)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        wait_for(receiver.ready.is_set)
        yield receiver
    finally:
        receiver.stop.set()
        thread.join(8)
        assert not thread.is_alive() and not errors, f'receiver failed: {errors}'


@contextmanager
def running_sender(box, conf, mode='demo'):
    sender = ReliableSender(box, conf, mode, ack_timeout=1)
    sender.start()
    try:
        wait_for(sender.subscribed.is_set)
        yield sender
    finally:
        sender.close()


def establish(sender):
    stop = threading.Event()
    wait_for(lambda: sender.session_ready.is_set() or (sender.step(stop) and sender.session_ready.is_set()))


def deliver(sender, box, seconds=10):
    stop = threading.Event()
    wait_for(lambda: not box.pending_count() or (sender.step(stop) and not box.pending_count()), seconds)


def db_rows(config, item):
    async def fetch():
        from edge_receiver.database_tls import verified_database_tls
        dsn=os.environ[config['dsn_env']]
        store = ReceiptStore(dsn,tls=verified_database_tls(dsn,config['db_tls']) if 'db_tls' in config else None)
        async with store.connection() as db:
            return await db.fetch('''SELECT time,device_id,voltage,current,power_kw,energy_kwh FROM electricity_measurements
                                  WHERE edge_gateway_id=$1 AND edge_sample_id=$2::uuid''',
                                  item['gateway_id'], item['sample_id'])
    return asyncio.run(fetch())


def test_receiver_stopped_after_session_puback_keeps_sample_and_producer_restart_recovers(tmp_path):
    box, config, mqtt = configured(tmp_path)
    with running_sender(box, mqtt) as sender:
        with running_receiver(config):
            establish(sender)
        item = box.enqueue(source_time(), dict(voltage=230, current=5, power_kw=1, energy_kwh=100))
        before = sender.broker_acks
        assert not sender.step(threading.Event()), 'missing receiver produced application commit'
        wait_for(lambda: sender.broker_acks > before)
        assert box.pending_count() == 1 and not db_rows(config, item), 'PUBACK deleted source or DB unexpectedly contains sample'
    # Re-open both processes' state; original ID/hash must be sent, not regenerated.
    reopened = ReliableOutbox(box.path, 100, **box.identity)
    assert reopened.pending()[0] == item, 'producer restart changed pending identity'
    with running_receiver(config), running_sender(reopened, mqtt) as resumed:
        deliver(resumed, reopened)
    rows = db_rows(config, item)
    assert len(rows) == 1 and rows[0]['voltage'] == 230, 'recovered sample duplicated or wrong'


def test_commit_then_lost_ack_and_duplicate_publish_recover_with_one_database_row(tmp_path):
    box, config, mqtt = configured(tmp_path)
    item = box.enqueue(source_time(), dict(voltage=231, current=6, power_kw=2, energy_kwh=101))
    with running_receiver(config) as receiver, running_sender(box, mqtt) as sender:
        establish(sender)
        publish = receiver.client.publish
        captured = []
        def drop_ack(topic, payload, **kwargs):
            if topic.endswith('/acks'):
                captured.append(json.loads(payload))
                return SimpleNamespace(rc=0)
            return publish(topic, payload, **kwargs)
        receiver.client.publish = drop_ack
        assert not sender.step(threading.Event()), 'dropped ACK deleted sample'
        assert captured and captured[0]['results'][0]['status'] == 'committed', 'DB did not commit before dropped ACK'
        assert box.pending_count() == 1 and len(db_rows(config, item)) == 1, 'lost-ACK window not retained'
        # Reproduce an actual identical MQTT republish under the original server session.
        envelope = {k: v for k, v in captured[0].items() if k != 'results'}
        envelope['samples'] = [item]
        sender.client.publish(sender.prefix + 'samples', canonical(envelope), qos=1, retain=False)
        wait_for(lambda: len(captured) >= 2)
        assert len(db_rows(config, item)) == 1, 'identical MQTT repeat duplicated central row'
        receiver.client.publish = publish
        deliver(sender, box)
    assert len(db_rows(config, item)) == 1 and box.audit_count() == 1, 'retry failed to converge'


def test_hostile_integer_and_retained_messages_do_not_stop_receiver(tmp_path):
    box, config, mqtt = configured(tmp_path)
    item = box.enqueue(source_time(), dict(voltage=232, current=7, power_kw=3, energy_kwh=102))
    with running_receiver(config) as receiver, running_sender(box, mqtt) as sender:
        establish(sender)
        with sender.lock:
            envelope = sender.state.prepare(item)
        envelope['samples'][0]['measurements']['voltage'] = 10**1000
        sender.client.publish(sender.prefix + 'samples', canonical(envelope), qos=1, retain=False)
        sender.on_message(sender.client, None, SimpleNamespace(topic=sender.prefix + 'acks', retain=True,
            payload=canonical(dict(schema_version=2))))
        time.sleep(.7)
        assert receiver.ready.is_set() and box.pending_count() == 1, 'malformed input killed receiver or deleted queue'
        deliver(sender, box)
    assert len(db_rows(config, item)) == 1, 'valid sample failed after malformed input'


def test_real_current_session_ack_after_capacity_retirement_keeps_newest_source(tmp_path):
    box,config,mqtt=configured(tmp_path)
    box=ReliableOutbox(box.path,1,**box.identity)
    old=box.enqueue(source_time(),dict(voltage=230,current=5,power_kw=1,energy_kwh=100))
    replacement=[]
    with running_receiver(config) as receiver,running_sender(box,mqtt) as sender:
        establish(sender)
        publish=receiver.client.publish
        def replace_before_actual_ack(topic,payload,**kwargs):
            if topic.endswith('/acks') and not replacement:
                result=json.loads(payload)['results'][0]
                assert result['sample_id']==old['sample_id'] and result['status']=='committed', 'old sample not committed before race'
                replacement.append(box.enqueue(source_time(),dict(voltage=231,current=6,power_kw=2,energy_kwh=101)))
            return publish(topic,payload,**kwargs)
        receiver.client.publish=replace_before_actual_ack
        assert not sender.step(threading.Event()), 'ACK for evicted row falsely resolved source'
        assert len(replacement)==1 and box.pending()==replacement, 'late valid ACK removed newest sample'
        assert len(db_rows(config,old))==1, 'retirement incorrectly changed central history'
        receiver.client.publish=publish
        deliver(sender,box)
    assert len(db_rows(config,replacement[0]))==1 and box.pending_count()==0, 'latest sample did not reach DB once'
    status=box.retention_status()
    assert status['unconfirmed_evicted_total']==1, 'capacity retirement falsely marked ACKed'
    evidence=os.environ.get('EDGE_V2_EVIDENCE')
    if evidence:
        Path(evidence,'capacity-late-ack.json').write_text(json.dumps(dict(passed=True,
            old_sample_id=old['sample_id'],new_sample_id=replacement[0]['sample_id'],
            old_central_rows=1,new_central_rows=1,pending_end=0,retention=status),indent=2))


def test_offline_capacity_rotation_sends_only_latest_retained_samples_once(tmp_path):
    box,config,mqtt=configured(tmp_path)
    box=ReliableOutbox(box.path,3,**box.identity,audit_limit=3)
    samples=[box.enqueue(source_time(),dict(voltage=230+i,current=5,power_kw=1,energy_kwh=100+i)) for i in range(12)]
    with running_receiver(config),running_sender(box,mqtt) as sender:
        deliver(sender,box)
    counts=[len(db_rows(config,item)) for item in samples]
    assert counts==[0]*9+[1]*3, 'rotation sent retired sources or duplicated latest samples'
    assert box.retention_status()['unconfirmed_evicted_total']==9 and box.pending_count()==0, 'retirement count or drain wrong'
    evidence=os.environ.get('EDGE_V2_EVIDENCE')
    if evidence:
        Path(evidence,'capacity-offline-recovery.json').write_text(json.dumps(dict(passed=True,
            enqueued=12,retired_local_unconfirmed=9,central_rows_by_sequence=counts,pending_end=0),indent=2))


def test_real_mtls_acl_rejects_gateway_ack_and_cross_gateway_publish(tmp_path):
    import ssl
    import paho.mqtt.client as mqtt_client
    pki = os.environ.get('EDGE_V2_TEST_PKI')
    if not pki:
        pytest.skip('requires provisioned private mTLS broker')
    pki = Path(pki)
    observed, ready = [], threading.Event()
    observer = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2, client_id='qa-observer')
    def tls(client, name):
        ctx = ssl.create_default_context(cafile=str(pki / 'ca.crt'))
        ctx.load_cert_chain(str(pki / (name + '.crt')), str(pki / (name + '.key')))
        client.tls_set_context(ctx)
    tls(observer, 'qa-observer')
    observer.on_connect = lambda c, *_: c.subscribe('ems/v2/#', qos=1)
    observer.on_subscribe = lambda *_: ready.set()
    observer.on_message = lambda c, u, msg: observed.append((msg.topic, bytes(msg.payload)))
    observer.connect('127.0.0.1', 8886)
    observer.loop_start()
    gateway = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2, client_id='acl-attacker')
    tls(gateway, 'client')
    gateway.connect('127.0.0.1', 8886)
    gateway.loop_start()
    try:
        wait_for(ready.is_set)
        gateway.publish('ems/v2/gateways/qa-edge/samples', b'positive-control', qos=1).wait_for_publish(3)
        wait_for(lambda: any(body == b'positive-control' for _, body in observed))
        forbidden = ['ems/v2/gateways/qa-edge/acks', 'ems/v2/gateways/other/samples',
                     'ems/v2/gateways/qa-edge/session/response', 'ems/v2/gateways/other/acks']
        for topic in forbidden:
            gateway.publish(topic, b'forbidden-qa-message', qos=1).wait_for_publish(3)
        time.sleep(.5)
        assert not any(body == b'forbidden-qa-message' for _, body in observed), 'gateway bypassed principal ACL'
        box, config, sender_conf = configured(tmp_path, gateway='qa-edge')
        config.update(mode='field')
        config['mqtt'].update(port=8886, tls=True, ca_file=str(pki/'ca.crt'),
                              cert_file=str(pki/'edge-receiver.crt'), key_file=str(pki/'edge-receiver.key'))
        sender_conf.update(port=8886, tls=True, ca_file=str(pki/'ca.crt'),
                           cert_file=str(pki/'client.crt'), key_file=str(pki/'client.key'))
        item = box.enqueue(source_time(), dict(voltage=233, current=8, power_kw=4, energy_kwh=103))
        with running_receiver(config), running_sender(box, sender_conf, mode='field') as sender:
            deliver(sender, box)
        assert len(db_rows(config, item)) == 1 and box.pending_count() == 0, 'authenticated end-to-end commit failed'
    finally:
        gateway.disconnect()
        gateway.loop_stop()
        observer.disconnect()
        observer.loop_stop()


def test_real_tcp_edge_process_sigkill_keeps_committed_samples_and_v2_resends_once(tmp_path):
    import subprocess
    from datetime import timedelta
    box, config, mqtt = configured(tmp_path)
    edge_config = dict(mode='demo', device_id='d1', outbox_path=str(box.path), queue_limit=100,
        poll_interval=1, batch_size=1, mqtt=mqtt,
        modbus=dict(transport='tcp', host='127.0.0.1', port=15025, unit_id=1, timeout=1),
        delivery=dict(protocol=2, ack_timeout_seconds=1,
                      **{k: box.identity[k] for k in ('gateway_id','stream_id','config_revision','profile_version')}))
    path = tmp_path / 'edge.json'
    path.write_text(json.dumps(edge_config))
    sim_log, edge_log = (tmp_path / 'sim.log').open('w'), (tmp_path / 'edge.log').open('w')
    simulator = subprocess.Popen([sys.executable, '-m', 'delta_device', 'simulator', '--host', '127.0.0.1',
        '--port', '15025', '--scenario', 'day'], stdout=sim_log, stderr=subprocess.STDOUT)
    edge = None
    try:
        import socket
        def simulator_ready():
            try:
                with socket.create_connection(('127.0.0.1', 15025), timeout=.2):
                    return True
            except OSError:
                return False
        wait_for(simulator_ready)
        edge = subprocess.Popen([sys.executable, '-m', 'delta_device', 'edge', '--config', str(path)],
                                stdout=edge_log, stderr=subprocess.STDOUT)
        wait_for(lambda: box.pending_count() >= 3, seconds=8)
        edge.kill()
        edge.wait(3)
        with box.connect() as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'SIGKILL damaged queue'
            expected = [json.loads(r[0]) for r in db.execute('SELECT payload FROM queue ORDER BY capture_seq')]
            assert all(json.loads(r[0])['state'] == 2 for r in db.execute('SELECT snapshot FROM queue')), 'raw snapshots lost'
        assert len(expected) >= 3, 'committed source samples lost'
        with running_receiver(config), running_sender(box, mqtt) as sender:
            deliver(sender, box, seconds=12)
        actual = []
        for item in expected:
            rows = db_rows(config, item)
            assert len(rows) == 1, 'SIGKILL recovery lost or duplicated sample'
            row = rows[0]
            assert row['time'] == datetime(1970,1,1,tzinfo=timezone.utc) + timedelta(microseconds=item['sampled_at_us']), 'timestamp changed'
            assert all(row[k] == value for k, value in item['measurements'].items()), 'projection value changed'
            actual.append(dict(sample_id=item['sample_id'], time=row['time'].isoformat(),
                               **{k: row[k] for k in item['measurements']}))
        evidence = os.environ.get('EDGE_V2_EVIDENCE')
        if evidence:
            Path(evidence, 'tcp-edge-crash-ledger.json').write_text(json.dumps(dict(expected=expected, actual=actual,
                producer_exit=edge.returncode, pending_end=box.pending_count()), indent=2))
    finally:
        if edge and edge.poll() is None:
            edge.kill()
            edge.wait(3)
        simulator.terminate()
        try:
            simulator.wait(3)
        except subprocess.TimeoutExpired:
            simulator.kill()
            simulator.wait(3)
        sim_log.close()
        edge_log.close()
