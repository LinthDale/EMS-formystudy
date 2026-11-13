"""Production Publisher + Outbox against a real isolated Mosquitto TLS broker."""
import socket
import ssl
import threading
import time
import pytest
from delta_device.delivery import Outbox, drain, encode_line
from delta_device.publisher import Publisher
from bench_network import Gate
from conftest import config, until, PKI, EVIDENCE, T0, SNAPSHOT

pytestmark = pytest.mark.integration


def spool(name):
    box = Outbox(EVIDENCE/name/'outbox.db',10,'tls-probe')
    payload = encode_line('tls-probe',SNAPSHOT,T0)
    box.enqueue(T0,payload,SNAPSHOT)
    return box,payload


def positive(settings, name, receiver):
    publisher = Publisher(settings,'tls-probe')
    box,payload = spool(name)
    try:
        publisher.start()
        assert publisher.ready.wait(8), 'authenticated TLS client did not connect'
        assert drain(box,publisher.publish,10,threading.Event()) == 1, 'missing real PUBACK'
        until(lambda:len(receiver)==1)
        assert receiver == [('ems/devices/tls-probe/measurements',payload)], 'payload or source timestamp changed'
        assert box.pending_count()==0, 'PUBACK did not remove private pending row'
        return dict(received=1,pending=0,source_time_ns=T0)
    finally:
        publisher.close()


def rejected(settings, name, receiver):
    publisher = Publisher(settings,'tls-probe')
    box,payload = spool(name)
    observed = threading.Event()
    reasons = []
    connect,disconnect = publisher.client.on_connect,publisher.client.on_disconnect
    def on_connect(c,u,f,reason,p):
        connect(c,u,f,reason,p)
        reasons.append('connack:'+str(reason))
        observed.set()
    def on_disconnect(*args):
        disconnect(*args)
        reasons.append('disconnect')
        observed.set()
    publisher.client.on_connect = on_connect
    publisher.client.on_disconnect = on_disconnect
    publisher.client.on_connect_fail = lambda *a:(reasons.append('connect_fail'),observed.set())
    try:
        publisher.start()
        assert observed.wait(8), 'no attempted TLS/MQTT connection observed'
        assert not publisher.ready.is_set(), 'invalid authentication became ready'
        assert drain(box,publisher.publish,10,threading.Event())==0, 'untrusted connection removed pending data'
        assert box.pending(10)[0][2]==payload and box.pending_count()==1, 'original pending row changed'
        assert receiver==[], 'rejected publisher unexpectedly delivered telemetry'
        return dict(connection_events=reasons,pending=1,received=0)
    finally:
        publisher.close()


def test_valid_password_tls_delivers_original_payload(receiver,record):
    record(**positive(config(),'tls-valid',receiver))


@pytest.mark.parametrize('case,port,ca,verify_code',[
    ('untrusted-ca',1883,'rogue-ca.crt',19),
    ('wrong-host',8884,'ca.crt',64),
    ('expired',8885,'ca.crt',10),
])
def test_invalid_server_certificate_preserves_pending(case,port,ca,verify_code,receiver,record):
    context = ssl.create_default_context(cafile=str(PKI/ca))
    with socket.create_connection(('127.0.0.1',port),timeout=3) as raw:
        with pytest.raises(ssl.SSLCertVerificationError) as error:
            context.wrap_socket(raw,server_hostname='127.0.0.1')
    assert error.value.verify_code==verify_code, 'certificate was not rejected for the expected reason'
    record(verify_code=verify_code,**rejected(config(port=port,ca=ca),'tls-'+case,receiver))


def test_wrong_password_rejected_without_deleting_pending(monkeypatch,receiver,record):
    monkeypatch.setenv('FIELD_QA_PASSWORD','deliberately-wrong-private-fixture')
    record(**rejected(config(),'tls-wrong-password',receiver))


def test_missing_auth_rejected_without_deleting_pending(receiver,record):
    record(**rejected(config(auth='none'),'tls-missing-auth',receiver))


def test_valid_mtls_without_password_delivers(receiver,record):
    record(**positive(config(port=8886,auth='certificate'),'mtls-valid',receiver))


@pytest.mark.parametrize('auth,client',[('none','client'),('certificate','rogue-client')])
def test_missing_or_untrusted_client_certificate_preserves_pending(auth,client,receiver,record):
    record(**rejected(config(port=8886,auth=auth,client=client),'mtls-'+client+'-'+auth,receiver))


def test_same_tls_publisher_reconnects_and_replays_original_data(receiver,record):
    gate = Gate()  # Opaque relay to private loopback:1883, which uses TLS here.
    publisher = Publisher(config(port=gate.port),'tls-probe')
    connected=[]
    original = publisher.client.on_connect
    def on_connect(c,u,f,reason,p):
        original(c,u,f,reason,p)
        if reason==0: connected.append(time.monotonic())
    publisher.client.on_connect = on_connect
    box,payload = spool('tls-reconnect')
    try:
        publisher.start()
        assert publisher.ready.wait(8), 'initial TLS connection failed'
        gate.set_blocked(True)
        until(lambda:not publisher.ready.is_set())
        assert drain(box,publisher.publish,10,threading.Event())==0, 'disconnected sender removed data'
        assert box.pending_count()==1 and receiver==[], 'pending data changed during outage'
        restored = time.monotonic()
        gate.set_blocked(False)
        until(lambda:len(connected)>=2 and publisher.ready.is_set(),timeout=12)
        reconnect_seconds = connected[-1]-restored
        assert drain(box,publisher.publish,10,threading.Event())==1, 'reconnected sender did not drain'
        until(lambda:len(receiver)==1)
        assert receiver==[('ems/devices/tls-probe/measurements',payload)], 'replay changed source time/payload'
        assert box.pending_count()==0, 'pending queue did not drain'
        record(publisher_instances=1,reconnect_seconds=reconnect_seconds,received=1,pending=0)
    finally:
        try:
            publisher.close()
        finally:
            gate.close()
