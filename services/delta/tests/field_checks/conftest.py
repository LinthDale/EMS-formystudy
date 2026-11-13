"""Private-network integration fixtures; never usable against shared MQTT."""
import json
import os
from pathlib import Path
import ssl
import sys
import threading
import time
import uuid
import pytest
import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
from bench_field_checks import require_private_namespace

PKI = Path('/qa')
EVIDENCE = Path('/evidence')
T0 = 1800000000000000000
SNAPSHOT = dict(voltage=230, current=13, power_kw=9, energy_kwh=1234)


@pytest.fixture(autouse=True)
def private_network():
    if not os.environ.get('FIELD_QA_NETNS'):
        pytest.skip('dedicated network-none TLS bench required')
    require_private_namespace(os.environ['FIELD_QA_NETNS'], os.readlink('/proc/self/ns/net'))


def config(port=1883, auth='password', ca='ca.crt', client='client'):
    result = dict(host='127.0.0.1',port=port,client_id='qa-'+uuid.uuid4().hex,tls=True,
                  ca_file=str(PKI/ca))
    if auth == 'password':
        result.update(username_env='FIELD_QA_USER',password_env='FIELD_QA_PASSWORD')
    elif auth == 'certificate':
        result.update(cert_file=str(PKI/(client+'.crt')),key_file=str(PKI/(client+'.key')))
    return result


def until(predicate, timeout=8):
    deadline = time.monotonic()+timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError('bounded observation deadline exceeded')
        threading.Event().wait(.02)


@pytest.fixture
def record(request):
    def save(**details):
        path = EVIDENCE/'cases.json'
        rows = json.loads(path.read_text()) if path.exists() else []
        rows.append(dict(case=request.node.name,passed=True,**details))
        path.write_text(json.dumps(rows,indent=2)+'\n')
    return save


@pytest.fixture
def receiver():
    messages = []
    subscribed = threading.Event()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='observer-'+uuid.uuid4().hex)
    client.tls_set_context(ssl.create_default_context(cafile=str(PKI/'ca.crt')))
    client.username_pw_set(os.environ['FIELD_QA_USER'],os.environ['FIELD_QA_PASSWORD'])
    def connected(c, userdata, flags, reason, properties):
        if reason == 0:
            c.subscribe('ems/devices/#',qos=1)
    client.on_connect = connected
    client.on_subscribe = lambda *args: subscribed.set()
    client.on_message = lambda c,u,msg: messages.append((msg.topic,msg.payload.decode()))
    try:
        client.connect('127.0.0.1',1883,30)
        client.loop_start()
        assert subscribed.wait(8), 'private TLS observer did not subscribe'
        yield messages
    finally:
        client.disconnect()
        client.loop_stop()
