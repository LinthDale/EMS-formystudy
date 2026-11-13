"""Bounded v2 MQTT receiver. Only commit success can produce committed ACK."""
import asyncio
import json
import logging
import os
from pathlib import Path
import queue
import re
import threading
import time

import paho.mqtt.client as mqtt

from delta_device.reliable_transport import connection_policy
from delta_device.reliable_wire import (ENVELOPE_KEYS, canonical, decode, identifier,
                                        uuid_text, validate_sample)
from .store import ReceiptStore, Conflict, OutsideWindow
from .database_tls import validate_tls_files,verified_database_tls

LOG = logging.getLogger(__name__)


def load_generation(path):
    return uuid_text(Path(path).read_text().strip())


def authority(sample, bindings):
    allowed = bindings.get(sample['gateway_id'], {}).get(sample['device_id'])
    return bool(allowed and all(sample[k] == allowed[k] for k in
                ('stream_id', 'config_revision', 'profile_version'))
                and allowed['not_before_us'] <= sample['sampled_at_us'] < allowed['not_after_us'])


def validate_config(config):
    from delta_device.config import ENV
    allowed = {'mode', 'mqtt', 'dsn_env', 'generation_file', 'bindings', 'db_timeout_seconds',
               'ack_durability', 'wal_standby_name', 'db_tls'}
    if not isinstance(config, dict) or set(config) - allowed:
        raise ValueError('receiver configuration')
    mqtt_config = config.get('mqtt')
    mqtt_keys = {'host', 'port', 'client_id', 'tls', 'ca_file', 'cert_file', 'key_file', 'username_env', 'password_env'}
    if not isinstance(mqtt_config, dict) or set(mqtt_config) - mqtt_keys:
        raise ValueError('MQTT configuration')
    identifier(mqtt_config.get('client_id'))
    if (not isinstance(mqtt_config.get('host'), str) or not mqtt_config['host'].strip()
            or type(mqtt_config.get('port')) is not int or not 1 <= mqtt_config['port'] <= 65535
            or type(mqtt_config.get('tls', False)) is not bool):
        raise ValueError('MQTT endpoint')
    for key in ('username_env', 'password_env'):
        if key in mqtt_config and (not isinstance(mqtt_config[key], str) or not ENV.fullmatch(mqtt_config[key])):
            raise ValueError('MQTT credential reference')
    if bool(mqtt_config.get('username_env')) != bool(mqtt_config.get('password_env')):
        raise ValueError('paired MQTT credentials required')
    if not isinstance(config.get('dsn_env'), str) or not ENV.fullmatch(config['dsn_env']):
        raise ValueError('database credential reference')
    if config.get('mode')=='field' or 'db_tls' in config:
        validate_tls_files(config.get('db_tls'))
    bindings = config.get('bindings')
    if not isinstance(bindings, dict) or not 1 <= len(bindings) <= 128:
        raise ValueError('bounded gateway registry required')
    for gateway, devices in bindings.items():
        identifier(gateway)
        if not isinstance(devices, dict) or not 1 <= len(devices) <= 8:
            raise ValueError('bounded device registry required')
        for device, binding in devices.items():
            identifier(device)
            if set(binding) != {'stream_id', 'config_revision', 'profile_version', 'not_before_us', 'not_after_us'}:
                raise ValueError('authority schema')
            uuid_text(binding['stream_id'])
            identifier(binding['config_revision'])
            identifier(binding['profile_version'])
            if any(type(binding[k]) is not int for k in ('not_before_us', 'not_after_us')) or not 0 < binding['not_before_us'] < binding['not_after_us'] < 2**63:
                raise ValueError('authority time range')
    timeout = config.setdefault('db_timeout_seconds', 5)
    if type(timeout) not in (int, float) or not 1 <= timeout <= 30:
        raise ValueError('database timeout')
    durability = config.setdefault('ack_durability', 'sync_wal' if config.get('mode') == 'field' else 'local')
    if durability not in ('local', 'sync_wal') or (config.get('mode') == 'field' and durability != 'sync_wal'):
        raise ValueError('field requires synchronous WAL durability')
    standby = config.setdefault('wal_standby_name', 'ems_archive')
    if not isinstance(standby, str) or not re.fullmatch('[a-z][a-z0-9_]{0,62}', standby):
        raise ValueError('one named WAL standby required')
    load_generation(config['generation_file'])
    return config


class Receiver:
    def __init__(self, config):
        self.config = validate_config(config)
        self.generation = load_generation(config['generation_file'])
        self.bindings = config['bindings']
        self.sessions = {}
        self.buckets = {}
        self.incoming = queue.Queue(maxsize=64)
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=config['mqtt']['client_id'], clean_session=True)
        connection_policy(self.client, config['mqtt'], config['mode'])
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_subscribe = self.on_subscribe
        self.client.on_message = self.on_message
        dsn = os.environ.get(config['dsn_env'])
        if not dsn:
            raise ValueError('database credentials missing')
        self.store = ReceiptStore(dsn, config['db_timeout_seconds'],
                                  config['wal_standby_name'] if config['ack_durability'] == 'sync_wal' else None,
                                  verified_database_tls(dsn,config['db_tls']) if 'db_tls' in config else None)

    def on_connect(self, client, userdata, flags, reason, properties):
        self.ready.clear()
        if reason == 0:
            client.subscribe([('ems/v2/gateways/+/samples', 1),
                              ('ems/v2/gateways/+/session/request', 1)])

    def on_subscribe(self, client, userdata, mid, reasons, properties):
        if reasons and all(not reason.is_failure for reason in reasons):
            self.ready.set()

    def on_disconnect(self, client, userdata, flags, reason, properties):
        self.ready.clear()

    def on_message(self, client, userdata, message):
        if message.retain or len(message.payload) > 65536:
            return
        try:
            self.incoming.put_nowait((message.topic, bytes(message.payload)))
        except queue.Full:
            LOG.warning('receiver_queue_full')

    def rate_allowed(self, gateway, op, cost=1):
        # Only known gateways reach this method; dict size is registry bounded.
        key, now = (gateway, op), time.monotonic()
        rate, capacity = {'session': (1, 1), 'batch': (2, 1), 'sample': (40, 64)}[op]
        tokens, previous = self.buckets.get(key, (float(capacity), now))
        tokens = min(capacity, tokens + (now - previous) * rate)
        accepted = tokens >= cost
        self.buckets[key] = (tokens - cost if accepted else tokens, now)
        return accepted

    async def handle(self, topic, raw):
        parts = topic.split('/')
        if len(parts) not in (5, 6) or parts[:3] != ['ems', 'v2', 'gateways']:
            return
        gateway = parts[3]
        if gateway not in self.bindings:
            return
        obj = decode(raw, 1024 if parts[4:] == ['session', 'request'] else 65536)
        if not isinstance(obj, dict) or obj.get('gateway_id') != gateway or type(obj.get('schema_version')) is not int or obj['schema_version'] != 2:
            return
        if parts[4:] == ['session', 'request']:
            if set(obj) != {'schema_version', 'gateway_id', 'session_challenge'} or not self.rate_allowed(gateway, 'session'):
                return
            challenge = uuid_text(obj['session_challenge'])
            self.sessions[gateway] = challenge
            reply = dict(obj, recovery_generation=self.generation)
            self.client.publish(f'ems/v2/gateways/{gateway}/session/response', canonical(reply), qos=1, retain=False)
            return
        if parts[4:] != ['samples'] or set(obj) != ENVELOPE_KEYS:
            return
        if (self.sessions.get(gateway) != obj.get('session_challenge')
                or self.generation != obj.get('recovery_generation')):
            return
        uuid_text(obj['batch_id'])
        samples = obj['samples']
        if not isinstance(samples, list) or not 1 <= len(samples) <= 32:
            return
        validated = [validate_sample(item, gateway) for item in samples]
        if len({s['sample_id'] for s in validated}) != len(validated):
            return
        if not self.rate_allowed(gateway, 'batch') or not self.rate_allowed(gateway, 'sample', len(validated)):
            return  # No committed ACK; edge retains and backs off.
        results = []
        for sample in validated:
            result = dict(sample_id=sample['sample_id'], payload_hash=sample['payload_hash'])
            try:
                if not authority(sample, self.bindings):
                    result.update(status='rejected', error_code='unauthorized')
                else:
                    stamp = await self.store.commit(sample)
                    result.update(status='committed', committed_at=stamp)
            except Conflict:
                result.update(status='rejected', error_code='conflict')
            except OutsideWindow:
                result.update(status='rejected', error_code='outside_window')
            except Exception as exc:
                LOG.error('database_retryable kind=%s', type(exc).__name__)
                result.update(status='retryable', error_code='database')
            results.append(result)
        reply = {k: v for k, v in obj.items() if k != 'samples'}
        reply['results'] = results
        self.client.publish(f'ems/v2/gateways/{gateway}/acks', canonical(reply), qos=1, retain=False)

    async def run(self):
        async with self.store.connection() as db:
            await db.fetchval('SELECT count(*) FROM edge_ingest.receipts')
        conf = self.config['mqtt']
        self.client.connect_async(conf['host'], conf['port'], keepalive=30)
        self.client.loop_start()
        try:
            while not self.stop.is_set():
                try:
                    topic, raw = await asyncio.to_thread(self.incoming.get, True, .2)
                except queue.Empty:
                    continue
                try:
                    await self.handle(topic, raw)
                except (ValueError, TypeError, KeyError) as exc:
                    LOG.warning('receiver_rejected kind=%s', type(exc).__name__)
        finally:
            self.client.disconnect()
            self.client.loop_stop()


def main():
    import argparse
    import signal
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        receiver = Receiver(decode(Path(args.config).read_bytes()))
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: receiver.stop.set())
        asyncio.run(receiver.run())
    except Exception as exc:
        LOG.error('receiver_failed kind=%s', type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
