"""FR-2107: new telemetry must not wait behind an entire historical queue."""
from types import SimpleNamespace
import copy
import json
import threading
from uuid import uuid4

import pytest
from delta_device.reliable_store import ReliableOutbox
from delta_device import reliable_sender

NOW=1794474000000000000
VALUES=dict(voltage=230,current=5,power_kw=1,energy_kwh=100)


def ready_sender(tmp_path,monkeypatch):
    box=ReliableOutbox(tmp_path/'q'/'q.db',200,'g1','d1',str(uuid4()),'r1','v135')
    client=SimpleNamespace()
    monkeypatch.setattr(reliable_sender.mqtt,'Client',lambda *a,**kw:client)
    monkeypatch.setattr(reliable_sender,'connection_policy',lambda *a:None)
    sender=reliable_sender.ReliableSender(box,dict(client_id='qa'),'demo',ack_timeout=.01)
    sender.state.connect()
    sender.state.establish(dict(schema_version=2,gateway_id='g1',session_challenge=sender.state.challenge,
        recovery_generation=str(uuid4())))
    sender.subscribed.set();sender.session_ready.set()
    sent=[]
    def publish(topic,payload,**kwargs):
        envelope=json.loads(payload);sample=envelope['samples'][0];sent.append(sample)
        ack={k:v for k,v in envelope.items() if k!='samples'}
        ack['results']=[dict(sample_id=sample['sample_id'],payload_hash=sample['payload_hash'],
            status='committed',committed_at='2026-11-13T00:00:00+00:00')]
        sender.on_message(client,None,SimpleNamespace(topic=sender.prefix+'acks',retain=False,payload=reliable_sender.canonical(ack)))
        return SimpleNamespace(rc=0)
    client.publish=publish
    return box,sender,sent


def step(sender):
    sender.next_send=0  # Virtual spacing; production throttle remains unchanged.
    return sender.step(threading.Event())


def test_new_sample_arrives_within_two_successes_and_oldest_also_advances(tmp_path,monkeypatch):
    box,sender,sent=ready_sender(tmp_path,monkeypatch)
    old=[box.enqueue(NOW+i*1000,VALUES) for i in range(50)]
    live=box.enqueue(NOW+100000,VALUES)
    assert step(sender) and step(sender), 'valid committed replies did not advance sender'
    assert live in sent, 'new telemetry waits behind the historical backlog'
    assert old[0] in sent and box.pending_count()==49, 'prioritizing newest starved oldest backlog'


def test_continuous_new_samples_cannot_starve_oldest_backlog(tmp_path,monkeypatch):
    box,sender,sent=ready_sender(tmp_path,monkeypatch)
    old=[box.enqueue(NOW+i*1000,VALUES) for i in range(20)]
    for i in range(10):
        box.enqueue(NOW+(100+i)*1000,VALUES)
        assert step(sender), 'fresh source failed to commit'
    assert [s for s in sent if s['sample_id'] in {x['sample_id'] for x in old}]==old[:5], 'oldest backlog not guaranteed progress'


def test_failed_latest_attempt_does_not_consume_oldest_turn_or_delete_data(tmp_path,monkeypatch):
    box,sender,sent=ready_sender(tmp_path,monkeypatch)
    old=box.enqueue(NOW,VALUES);latest=box.enqueue(NOW+1000,VALUES)
    success=sender.client.publish
    sender.client.publish=lambda *a,**kw:SimpleNamespace(rc=0)  # Real application ACK timeout path.
    assert not step(sender) and box.pending_count()==2, 'missing ACK deleted samples'
    sender.client.publish=success
    # step failure reopens the session; complete a new valid handshake.
    sender.state.establish(dict(schema_version=2,gateway_id='g1',session_challenge=sender.state.challenge,
        recovery_generation=str(uuid4())))
    sender.session_ready.set()
    assert step(sender) and step(sender), 'sender failed to recover from ACK timeout'
    assert sent==[latest,old], 'failed attempt consumed fair turn or replaced immutable source'
