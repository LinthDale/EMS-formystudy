"""Unit: MQTT subscriber reconnect + per-message error branches (fake aiomqtt)."""
import asyncio
import sys
import types

import pytest

from device_service import mqtt_subscriber

_S = types.SimpleNamespace(mqtt_host="x", mqtt_port=1883)


def _install_fake_aiomqtt(monkeypatch, client_cls):
    fake = types.ModuleType("aiomqtt")
    fake.Client = client_cls
    monkeypatch.setitem(sys.modules, "aiomqtt", fake)
    monkeypatch.setattr(mqtt_subscriber, "RECONNECT_DELAY", 0.0)


async def test_reconnects_after_broker_failure(monkeypatch):
    attempts = {"n": 0}

    class _Client:
        def __init__(self, **kw):
            pass
        async def __aenter__(self):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("broker down")     # first connect fails -> reconnect
            return self
        async def __aexit__(self, *a):
            return False
        async def subscribe(self, *a, **k):
            pass
        @property
        def messages(self):
            async def _gen():
                raise asyncio.CancelledError()         # simulate task cancel on 2nd connect
                yield  # pragma: no cover
            return _gen()

    _install_fake_aiomqtt(monkeypatch, _Client)
    with pytest.raises(asyncio.CancelledError):
        await mqtt_subscriber.run_subscriber(db=None, classifier=None, settings=_S)
    assert attempts["n"] == 2   # reconnected once


async def test_one_bad_message_does_not_kill_loop(monkeypatch):
    seen = {"n": 0}

    async def _boom(*a, **k):
        seen["n"] += 1
        raise RuntimeError("bad message")

    monkeypatch.setattr(mqtt_subscriber, "process_message", _boom)

    class _Client:
        def __init__(self, **kw):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def subscribe(self, *a, **k):
            pass
        @property
        def messages(self):
            async def _gen():
                yield types.SimpleNamespace(topic="ems/devices/x/measurements", payload=b"e f=1 1")
                raise asyncio.CancelledError()         # end after the bad message
            return _gen()

    _install_fake_aiomqtt(monkeypatch, _Client)
    with pytest.raises(asyncio.CancelledError):
        await mqtt_subscriber.run_subscriber(db=None, classifier=None, settings=_S)
    assert seen["n"] == 1   # the bad message was processed (and swallowed), loop survived to cancel

async def test_settings_subscriptions_reach_broker(monkeypatch):
    import asyncio
    subscribed = []

    class _Client:
        def __init__(self, **kw):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def subscribe(self, topic, **k):
            subscribed.append(topic)
        @property
        def messages(self):
            async def _gen():
                raise asyncio.CancelledError()
                yield  # pragma: no cover
            return _gen()

    _install_fake_aiomqtt(monkeypatch, _Client)
    s = types.SimpleNamespace(mqtt_host="x", mqtt_port=1883, mqtt_subscriptions="custom/topic/+,ems/+/+/measurements")
    with pytest.raises(asyncio.CancelledError):
        await mqtt_subscriber.run_subscriber(db=None, classifier=None, settings=s)
    assert subscribed == ["custom/topic/+", "ems/+/+/measurements"]  # from settings, NOT hardcoded SUBSCRIPTIONS