"""EMS MQTT wrapper preserves KC's wire topic/payload and waveform."""
import asyncio
import json
import logging
import math
import os
import random
import time
import aiomqtt
from .contracts import SensorSettings


def sample(elapsed):
    return {"temp": round(25 + 5 * math.sin(elapsed * .1) + random.uniform(-.5, .5), 2),
            "hum": round(max(0, min(100, 50 + 10 * math.sin(elapsed * .07)
                                    + random.uniform(-2, 2))), 2)}


def build():
    settings = SensorSettings().model_dump()

    async def run():
        started = time.monotonic()
        while True:
            try:
                async with aiomqtt.Client(os.getenv("MQTT_BROKER", "mosquitto"),
                                          int(os.getenv("MQTT_PORT", "1883"))) as client:
                    while True:
                        if settings["enabled"]:
                            await client.publish("factory/sensor/temp_01",
                                                 json.dumps(sample(time.monotonic() - started)))
                        await asyncio.sleep(settings["interval_seconds"])
            except aiomqtt.MqttError:
                logging.warning("sensor MQTT unavailable; reconnecting")
                await asyncio.sleep(5)
    return "sensor-001", lambda: dict(settings), settings.update, run
