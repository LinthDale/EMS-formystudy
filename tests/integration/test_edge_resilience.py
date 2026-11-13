"""Real v2 mTLS server rejection and recovery on an owned private namespace."""
import json
import os
from pathlib import Path
import socket
import ssl
import threading

import pytest

import test_edge_receipts_mqtt as base
from delta_device.reliable_sender import ReliableSender

pytestmark=pytest.mark.integration


@pytest.mark.parametrize('case,port,ca,verify_code',[
    ('untrusted-ca',8886,'rogue-ca.crt',19),
    ('wrong-host',8887,'ca.crt',64),
    ('expired',8888,'ca.crt',10),
])
def test_v2_invalid_server_certificate_keeps_original_then_recovers_once(tmp_path,case,port,ca,verify_code):
    expected=os.environ.get('EMS_V2_DEMO_NETNS')
    if not expected:
        pytest.skip('requires explicitly owned network-none v2 TLS/DB bench')
    assert os.readlink('/proc/self/ns/net')==expected and {p.name for p in Path('/sys/class/net').iterdir()}=={'lo'}, 'wrong private namespace'
    assert os.environ.get('EDGE_V2_TEST_DSN')=='postgresql://postgres@127.0.0.1:5432/ems', 'unexpected database target'
    box,config,mqtt=base.configured(tmp_path,gateway='qa-edge')
    item=box.enqueue(base.source_time(),dict(voltage=230,current=5,power_kw=1,energy_kwh=100))
    pki=Path(os.environ['EDGE_V2_TEST_PKI'])
    context=ssl.create_default_context(cafile=str(pki/ca))
    context.load_cert_chain(pki/'client.crt',pki/'client.key')
    with socket.create_connection(('127.0.0.1',port),timeout=3) as raw:
        with pytest.raises(ssl.SSLCertVerificationError) as failure:
            context.wrap_socket(raw,server_hostname='127.0.0.1')
    assert failure.value.verify_code==verify_code, 'certificate rejection had the wrong cause'
    mqtt.update(port=port,tls=True,ca_file=str(pki/ca),cert_file=str(pki/'client.crt'),key_file=str(pki/'client.key'))
    sender=ReliableSender(box,mqtt,'field',ack_timeout=1)
    rejected=threading.Event()
    sender.client.on_connect_fail=lambda *_:rejected.set()
    sender.start()
    try:
        assert rejected.wait(5), 'production v2 client did not attempt and reject TLS'
        assert not sender.subscribed.is_set() and not sender.session_ready.is_set(), 'bad TLS established a usable v2 session'
        assert box.pending()==[item] and not base.db_rows(config,item), 'invalid server changed source or wrote DB'
    finally:
        sender.close()
    mqtt.update(port=8886,ca_file=str(pki/'ca.crt'))
    config.update(mode='field')
    config['mqtt'].update(port=8886,tls=True,ca_file=str(pki/'ca.crt'),
                          cert_file=str(pki/'edge-receiver.crt'),key_file=str(pki/'edge-receiver.key'))
    with base.running_receiver(config),base.running_sender(box,mqtt,mode='field') as resumed:
        base.deliver(resumed,box)
    assert len(base.db_rows(config,item))==1 and box.pending_count()==0, 'corrected TLS failed to recover original sample once'
    evidence=os.environ.get('EDGE_V2_EVIDENCE')
    if evidence:
        Path(evidence,'tls-server-'+case+'.json').write_text(json.dumps(dict(passed=True,
            verify_code=verify_code,real_client_rejection=True,original_sample_id=item['sample_id'],
            original_payload_hash=item['payload_hash'],source_preserved_during_failure=True,
            projections=1,pending_end=0),indent=2))
