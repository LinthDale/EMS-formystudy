"""Single-inflight v2 sender: broker PUBACK never authorizes local deletion."""
import logging
import random
import threading
import time

import paho.mqtt.client as mqtt

from .reliable_transport import connection_policy
from .reliable_wire import AckState, canonical, decode

LOG = logging.getLogger(__name__)


class ReliableSender:
    def __init__(self, box, config, mode, ack_timeout=30):
        self.box, self.config, self.ack_timeout = box, config, ack_timeout
        self.state = AckState(box.identity['gateway_id'])
        self.prefix = f"ems/v2/gateways/{self.state.gateway_id}/"
        self.lock = threading.RLock()
        self.diagnostic_lock = threading.Lock()
        self.subscribed = threading.Event()
        self.session_ready = threading.Event()
        self.received = threading.Event()
        self.accepted = None
        self.broker_acks = 0
        self.next_handshake = self.next_send = 0.0
        self.failures = 0
        self.prefer_latest = True
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=config['client_id'], clean_session=True)
        connection_policy(self.client, config, mode)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_subscribe = self.on_subscribe
        self.client.on_message = self.on_message
        self.client.on_publish = self.on_publish

    def reset(self, connected=False):
        self.session_ready.clear()
        self.accepted = None
        self.received.set()
        self.next_handshake = 0
        if connected:
            self.state.connect()
        else:
            self.state.disconnect()

    def on_connect(self, client, userdata, flags, reason, properties):
        with self.lock:
            self.subscribed.clear()
            self.reset(reason == 0)
            if reason == 0:
                client.subscribe([(self.prefix + 'acks', 1), (self.prefix + 'session/response', 1)])

    def on_subscribe(self, client, userdata, mid, reasons, properties):
        with self.lock:
            if reasons and all(not reason.is_failure for reason in reasons) and self.state.challenge:
                self.subscribed.set()

    def on_disconnect(self, client, userdata, flags, reason, properties):
        with self.lock:
            self.subscribed.clear()
            self.reset()

    def on_publish(self, client, userdata, mid, reason, properties):
        if reason == 0:
            # Paho invokes this under its outgoing-message mutex. Never acquire
            # the session lock here: step() holds it while calling publish().
            with self.diagnostic_lock:
                self.broker_acks += 1  # Diagnostic only; never touches queue state.

    def on_message(self, client, userdata, message):
        if message.retain or len(message.payload) > 65536:
            return
        try:
            obj = decode(message.payload, 1024 if message.topic.endswith('/session/response') else 65536)
            with self.lock:
                if message.topic == self.prefix + 'session/response' and self.subscribed.is_set():
                    if self.state.establish(obj):
                        self.session_ready.set()
                elif message.topic == self.prefix + 'acks':
                    status = self.state.accept(obj)
                    if status:
                        self.accepted = (self.state.challenge, self.state.batch_id, status)
                        self.received.set()
        except (ValueError, TypeError, KeyError):
            LOG.warning('application_ack_rejected')

    def start(self):
        self.client.connect_async(self.config['host'], self.config['port'], keepalive=30)
        self.client.loop_start()

    def step(self, stop):
        now = time.monotonic()
        with self.lock:
            if stop.is_set() or now < self.next_send or not self.subscribed.is_set():
                return False
            if not self.session_ready.is_set():
                if now >= self.next_handshake and self.state.challenge:
                    self.client.publish(self.prefix + 'session/request', canonical(dict(schema_version=2,
                        gateway_id=self.state.gateway_id, session_challenge=self.state.challenge)), qos=1, retain=False)
                    self.next_handshake = now + 1
                return False
            pending = self.box.pending(newest=self.prefer_latest)
            if not pending:
                return False
            sample = pending[0]
            envelope = self.state.prepare(sample)
            challenge, batch_id = self.state.challenge, self.state.batch_id
            self.accepted = None
            self.received.clear()
            info = self.client.publish(self.prefix + 'samples', canonical(envelope), qos=1, retain=False)
            if info.rc not in (mqtt.MQTT_ERR_SUCCESS, mqtt.MQTT_ERR_NO_CONN):
                self.state.batch_id = self.state.sample = None
                self.next_send = now + 1
                return False
        deadline = time.monotonic() + self.ack_timeout
        while not stop.is_set() and time.monotonic() < deadline:
            if self.received.wait(min(.1, max(0, deadline - time.monotonic()))):
                break
        with self.lock:
            # Disconnect/reconnect cannot race the pending deletion transaction.
            valid = (self.state.challenge == challenge and self.state.batch_id == batch_id
                     and self.accepted is not None and self.accepted[:2] == (challenge, batch_id))
            status = self.accepted[2] if valid else None
            if status == 'committed' and not stop.is_set():
                resolved = self.box.committed(sample['sample_id'], sample['payload_hash'])
                self.state.batch_id = self.state.sample = None
                self.failures = 0
                if resolved:
                    self.prefer_latest = not self.prefer_latest
                self.next_send = time.monotonic() + .5
                LOG.info('%s sample_id=%s', 'central_committed' if resolved else 'ack_for_retired_sample', sample['sample_id'])
                return resolved
            if status == 'rejected':
                if self.box.quarantine(sample['sample_id'], sample['payload_hash'], 'rejected'):
                    LOG.error('sample_quarantined sample_id=%s', sample['sample_id'])
            self.failures = min(self.failures + 1, 6)
            self.next_send = time.monotonic() + min(60, 2**self.failures) * random.uniform(.75, 1)
            if self.subscribed.is_set():
                # Receiver may have restarted without a broker reconnect; reopen handshake.
                self.reset(connected=True)
            return False

    def close(self):
        with self.lock:
            self.subscribed.clear()
            self.reset()
        self.client.disconnect()
        self.client.loop_stop()
