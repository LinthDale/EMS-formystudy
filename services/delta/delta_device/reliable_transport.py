"""Shared v2 MQTT connection policy; demo restricted to private network-none."""
import os
from pathlib import Path
import ssl


def connection_policy(client, config, mode):
    if mode == 'demo':
        expected = os.environ.get('EMS_V2_DEMO_NETNS')
        if (not expected or os.readlink('/proc/self/ns/net') != expected
                or {p.name for p in Path('/sys/class/net').iterdir()} != {'lo'}):
            raise ValueError('v2 demo requires explicitly owned network-none namespace')
    elif mode != 'field' or not config.get('tls') or not all(config.get(k) for k in ('ca_file', 'cert_file', 'key_file')):
        raise ValueError('v2 field requires verified mTLS')
    if config.get('tls'):
        context = ssl.create_default_context(cafile=config.get('ca_file'))
        if config.get('cert_file'):
            context.load_cert_chain(config['cert_file'], config['key_file'])
        client.tls_set_context(context)
    if config.get('username_env'):
        username, password = (os.environ.get(config[k]) for k in ('username_env', 'password_env'))
        if not username or not password:
            raise ValueError('MQTT credentials missing')
        client.username_pw_set(username, password)
    client.max_inflight_messages_set(1)
    client.max_queued_messages_set(8)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
