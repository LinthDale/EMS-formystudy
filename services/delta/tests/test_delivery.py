import json
import threading
from types import SimpleNamespace
import pytest
from delta_device.delivery import Outbox, ClockGuard, encode_line, drain
from delta_device.config import validate

def config(tmp_path):
    return {"mode":"demo", "device_id":"delta-sim-001",
            "modbus":{"transport":"tcp","host":"localhost"},
            "mqtt":{"host":"localhost","client_id":"edge-demo"},
            "outbox_path":str(tmp_path / "private" / "outbox.db")}

def snapshot():
    return dict(voltage=230, current=13, power_kw=9, energy_kwh=1234)

def test_spool_restart_order_bound_and_exact_replay(tmp_path):
    path = tmp_path / "private" / "outbox.db"
    box = Outbox(path, 2)
    payload = encode_line("delta-sim-001", snapshot(), 1800000000000000000)
    box.enqueue(1800000000000000000, payload, snapshot())
    box.enqueue(1800000001000000000, payload, snapshot())
    with pytest.raises(OverflowError):
        box.enqueue(1800000002000000000, payload, snapshot())
    again = Outbox(path, 2)
    assert again.pending(100)[0][2] == payload
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert again.latest_timestamp() == 1800000001000000000
    again.ack(again.pending(1)[0][0])
    assert len(again.pending(100)) == 1

def test_only_confirmed_row_deleted(tmp_path):
    box = Outbox(tmp_path / "spool" / "outbox.db", 10)
    for i in range(3):
        box.enqueue(i, "bytes-" + str(i), snapshot())
    calls = []
    def publish(payload):
        calls.append(payload)
        return len(calls) == 1
    assert drain(box, publish, 100, threading.Event()) == 1
    assert [r[2] for r in box.pending(100)] == ["bytes-1", "bytes-2"]

def test_invalid_samples_and_clock(tmp_path):
    with pytest.raises(ValueError):
        encode_line("bad,id", snapshot(), 1)
    with pytest.raises(ValueError):
        encode_line("okay", dict(snapshot(), power_kw=float("nan")), 1)
    guard = ClockGuard("field", tmp_path / "synced")
    with pytest.raises(ValueError):
        guard.timestamp(1800000000000000000)
    (tmp_path / "synced").touch()
    assert guard.timestamp(1800000000000000001) == 1800000000000000000
    with pytest.raises(ValueError):
        guard.timestamp(1799999999000000000)
    with pytest.raises(ValueError):
        ClockGuard("demo").timestamp(1)

def test_field_security_and_transport_config(tmp_path):
    c = config(tmp_path)
    validate(c)
    c["mode"] = "field"
    with pytest.raises(ValueError):
        validate(c)
    c["device_id"] = "delta-site-001"
    with pytest.raises(ValueError):
        validate(c)
    c["mqtt"].update(tls=True, username_env="MQTT_USER", password_env="MQTT_PASSWORD")
    validate(c)
    c["modbus"].update(transport="rtu", serial_port="/dev/ttyUSB0")
    validate(c)
    assert c["modbus"]["baudrate"] == 19200
    c["modbus"]["unit_id"] = 0
    with pytest.raises(ValueError):
        validate(c)
