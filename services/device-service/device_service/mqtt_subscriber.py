"""MQTT subscription loop (PRD-0003 §8.5). aiomqtt is imported lazily so the rest
of the service (and its tests) does not require the dependency unless the
subscriber is actually started. Reconnects on broker disconnect so a transient
blip does not silently kill auto-discovery."""
from __future__ import annotations

import asyncio
import logging
import time

from .discovery import AdmissionGate, process_message

_log = logging.getLogger("device_service.discovery")

SUBSCRIPTIONS = ("ems/+/+/measurements", "factory/sensor/+")
RECONNECT_DELAY = 5.0


async def run_subscriber(db, classifier, settings, *, stop_event=None) -> None:
    import aiomqtt  # lazy

    gate = AdmissionGate()
    while True:
        try:
            async with aiomqtt.Client(hostname=settings.mqtt_host, port=settings.mqtt_port) as client:
                for topic in SUBSCRIPTIONS:
                    await client.subscribe(topic, qos=1)
                async for message in client.messages:
                    try:
                        await process_message(
                            str(message.topic), message.payload,
                            db=db, classifier=classifier, gate=gate, settings=settings,
                            now=time.monotonic(),
                        )
                    except Exception:  # one bad message must not kill the loop
                        _log.exception("auto-discovery message processing failed")
                    if stop_event is not None and stop_event.is_set():
                        return
        except asyncio.CancelledError:
            raise
        except Exception:  # broker disconnect / connect failure -> retry
            _log.exception("MQTT subscriber disconnected; reconnecting in %.0fs", RECONNECT_DELAY)
            if stop_event is not None and stop_event.is_set():
                return
            await asyncio.sleep(RECONNECT_DELAY)