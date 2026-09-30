"""Sensor preserves topic/JSON and respects enable/interval control."""
import asyncio
import json
import os
import pytest

pytestmark = pytest.mark.skipif(os.environ.get("SIMULATOR_KIND") != "sensor", reason="sensor image")


@pytest.mark.parametrize("enabled", [True, False])
def test_sensor_publish_setting_controls_real_loop(monkeypatch, enabled):
    from sim_control import sensor
    messages, intervals = [], []
    class Client:
        def __init__(self, *args):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def publish(self, topic, payload):
            messages.append((topic, json.loads(payload)))
    async def sleep(interval):
        intervals.append(interval)
        raise asyncio.CancelledError()
    monkeypatch.setattr(sensor.aiomqtt, "Client", Client)
    monkeypatch.setattr(sensor.asyncio, "sleep", sleep)
    simulator_id, read, apply, run = sensor.build()
    apply({"enabled": enabled, "interval_seconds": 5})
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run())
    assert read() == {"enabled": enabled, "interval_seconds": 5}
    assert intervals == [5]
    assert len(messages) == int(enabled)
    if enabled:
        assert messages[0][0] == "factory/sensor/temp_01"
        assert set(messages[0][1]) == {"temp", "hum"}
        assert 0 <= messages[0][1]["hum"] <= 100
