"""Owned broker lifecycle and actual mTLS certificate rotation/revocation."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from uuid import uuid4

import pytest
import test_edge_receipts_mqtt as base
from delta_device.reliable_sender import ReliableSender

pytestmark=pytest.mark.integration


@pytest.fixture(autouse=True)
def private_gate():
    expected=os.environ.get('EMS_V2_DEMO_NETNS')
    if not expected or os.environ.get('EDGE_V2_LIFECYCLE')!='1':
        pytest.skip('requires explicitly owned lifecycle bench')
    assert os.readlink('/proc/self/ns/net')==expected and {p.name for p in Path('/sys/class/net').iterdir()}=={'lo'}, 'wrong namespace'
    assert os.environ.get('EDGE_V2_TEST_DSN')=='postgresql://postgres@127.0.0.1:5432/ems', 'wrong private DB'


def emit(name,**value):
    Path(os.environ['EDGE_V2_EVIDENCE'],name+'.json').write_text(json.dumps(dict(passed=True,**value),indent=2))


def control(op):
    directory=Path(os.environ['EDGE_V2_EVIDENCE'])
    token=str(uuid4())
    request=directory/('control-'+token+'.request.json')
    temporary=request.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(request_id=token,op=op)))
    os.replace(temporary,request)
    response=directory/('control-'+token+'.response.json')
    base.wait_for(response.exists,seconds=15)
    result=json.loads(response.read_text())
    assert result.get('passed') is True and result.get('request_id')==token and result.get('op')==op, 'owned controller operation failed'
    return result


@contextmanager
def tcp_edge(tmp_path,box,mqtt):
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    config=dict(mode='demo',device_id='d1',outbox_path=str(box.path),queue_limit=100,poll_interval=1,batch_size=1,
        mqtt=mqtt,modbus=dict(transport='tcp',host='127.0.0.1',port=port,unit_id=1,timeout=1),
        delivery=dict(protocol=2,ack_timeout_seconds=1,**{k:box.identity[k] for k in ('gateway_id','stream_id','config_revision','profile_version')}))
    file=tmp_path/'edge.json';file.write_text(json.dumps(config))
    children=[]
    with (tmp_path/'sim.log').open('w') as simlog,(tmp_path/'edge.log').open('w') as edgelog:
        try:
            sim=subprocess.Popen([sys.executable,'-m','delta_device','simulator','--host','127.0.0.1','--port',str(port),'--scenario','day'],stdout=simlog,stderr=subprocess.STDOUT);children.append(sim)
            def ready():
                assert sim.poll() is None, 'owned simulator died'
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.2):return True
                except OSError:return False
            base.wait_for(ready)
            edge=subprocess.Popen([sys.executable,'-m','delta_device','edge','--config',str(file)],stdout=edgelog,stderr=subprocess.STDOUT);children.append(edge)
            yield edge
        finally:
            for process in reversed(children):
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
    for name in ('sim','edge'):
        Path(os.environ['EDGE_V2_EVIDENCE'],'broker-restart-'+name+'.log').write_bytes((tmp_path/(name+'.log')).read_bytes())


def all_samples(box):
    with box.connect() as db:
        return [json.loads(row[0]) for row in db.execute('SELECT payload FROM queue ORDER BY capture_seq')]


def test_real_broker_restart_keeps_tcp_acquisition_and_same_process_reconnects(tmp_path):
    box,config,mqtt=base.configured(tmp_path)
    with base.running_receiver(config) as receiver,tcp_edge(tmp_path,box,mqtt) as edge:
        base.wait_for(lambda:box.audit_count()>=2,seconds=8)
        def committed_before_outage():
            with box.connect() as db:
                return db.execute("SELECT COUNT(*) FROM audit WHERE state='committed'").fetchone()[0]>0
        base.wait_for(committed_before_outage,seconds=8)
        stopped=control('broker_stop')
        base.wait_for(lambda:not receiver.ready.is_set(),seconds=5)
        before=box.audit_count();pid=edge.pid
        with box.connect() as db:
            seq_at_stop=int(db.execute("SELECT value FROM metadata WHERE key='sequence'").fetchone()[0])
        base.wait_for(lambda:box.audit_count()>=before+3,seconds=8)
        assert edge.poll() is None and box.audit_count()>=before+3, 'broker outage stopped actual TCP acquisition'
        expected=[s for s in all_samples(box) if s['capture_seq']>seq_at_stop]
        assert len(expected)>=3 and all(not base.db_rows(config,s) for s in expected), 'outage did not preserve pending-only samples'
        started=control('broker_start')
        assert stopped['container_id']==started['container_id'] and stopped['started_at']!=started['started_at'], 'broker was not actually restarted'
        base.wait_for(lambda:all(len(base.db_rows(config,s))==1 for s in expected),seconds=18)
        assert edge.poll() is None and edge.pid==pid, 'edge was replaced to fake reconnect'
        # Gracefully stop only this producer, then drain any final in-flight sample.
        edge.terminate();edge.wait(timeout=5)
        remaining=all_samples(box)
        with base.running_sender(box,dict(mqtt,client_id='final-drain-'+box.identity['gateway_id'])) as drain:
            base.deliver(drain,box)
        assert all(len(base.db_rows(config,s))==1 for s in expected+remaining), 'restart duplicated or lost original sample'
    emit('broker-restart',broker_container_id=started['container_id'],stopped=stopped,started=started,
         edge_pid=pid,same_edge_process=True,tcp_samples_during_outage=len(expected),
         original_sample_ids=[s['sample_id'] for s in expected],projections_each=1,pending_end=box.pending_count())


def field_config(config,mqtt,certificate):
    pki=Path(os.environ['EDGE_V2_TEST_PKI'])
    config['mode']='field'
    config['mqtt'].update(port=8886,tls=True,ca_file=str(pki/'ca.crt'),cert_file=str(pki/'edge-receiver.crt'),key_file=str(pki/'edge-receiver.key'))
    mqtt.update(port=8886,tls=True,ca_file=str(pki/'ca.crt'),cert_file=str(pki/(certificate+'.crt')),key_file=str(pki/(certificate+'.key')))


def test_same_gateway_new_certificate_rotates_then_revoked_old_certificate_is_denied(tmp_path):
    box,config,mqtt=base.configured(tmp_path,gateway='qa-edge')
    field_config(config,mqtt,'client')
    value=dict(voltage=230,current=5,power_kw=1,energy_kwh=100)
    first=box.enqueue(base.source_time(),value)
    with base.running_receiver(config),base.running_sender(box,mqtt,mode='field') as old:
        base.deliver(old,box)
    assert len(base.db_rows(config,first))==1, 'old commissioned certificate never worked'
    second=box.enqueue(base.source_time(),value)
    field_config(config,mqtt,'rotated-client')
    with base.running_receiver(config),base.running_sender(box,mqtt,mode='field') as new:
        base.deliver(new,box)
    assert len(base.db_rows(config,second))==1, 'rotated same-gateway certificate failed'
    field_config(config,mqtt,'client')
    active_disconnect=threading.Event()
    with base.running_sender(box,dict(mqtt,client_id='old-active-before-revoke'),mode='field') as active:
        original=active.client.on_disconnect
        def observed_disconnect(*args):
            original(*args);active_disconnect.set()
        active.client.on_disconnect=observed_disconnect
        revoked=control('revoke_old_client')
        assert active_disconnect.wait(5), 'existing old TLS session was not disconnected at revocation gate'
    assert revoked['serial_revoked'] and revoked['crl_verified'] and revoked['revocation_verify_error']==23, 'no actual signed CRL revocation'
    pending=box.enqueue(base.source_time(),value)
    field_config(config,mqtt,'client')
    failed=threading.Event()
    old=ReliableSender(box,mqtt,'field',ack_timeout=1)
    original_disconnect=old.client.on_disconnect
    def disconnect(*args):
        original_disconnect(*args);failed.set()
    old.client.on_disconnect=disconnect
    old.client.on_connect_fail=lambda *_:failed.set()
    old.start()
    try:
        assert failed.wait(6), 'revoked certificate was never rejected on connection'
        assert not old.subscribed.is_set() and not old.session_ready.is_set() and box.pending()==[pending], 'revoked client connected or deleted pending'
        assert not base.db_rows(config,pending), 'revoked client reached DB'
    finally:old.close()
    field_config(config,mqtt,'rotated-client')
    with base.running_receiver(config),base.running_sender(box,mqtt,mode='field') as new:
        base.deliver(new,box)
    assert len(base.db_rows(config,pending))==1 and box.pending_count()==0, 'non-revoked certificate failed to recover original sample'
    emit('certificate-rotation-revocation',old_worked_before=True,new_worked_before=True,
        same_gateway='qa-edge',revocation=revoked,old_rejected_after=True,original_pending_id=pending['sample_id'],
        active_old_session_disconnected=active_disconnect.is_set(),new_worked_after=True,projections_each=1,pending_end=0)
