"""Actual pymodbus socket tests; no decoder-generated expected values."""
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
import threading
import pytest
from pymodbus.client import ModbusTcpClient
import paho.mqtt.client as mqtt
from delta_device.poller import Poller
from delta_device.publisher import Publisher
from delta_device.simulator import DeltaRegisters, ReadOnlyContext
from test_poller import config

@pytest.mark.parametrize("scenario,expected_state", [("day",2),("night",0),("alarm",4)])
def test_real_tcp_readonly_simulator(scenario, expected_state):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1",0))
        port = probe.getsockname()[1]
    process = subprocess.Popen([sys.executable,"-m","delta_device","simulator",
                                "--port",str(port),"--scenario",scenario],
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    client = ModbusTcpClient("127.0.0.1",port=port,timeout=.3,retries=0)
    try:
        deadline = time.monotonic() + 5
        while not client.connect():
            assert process.poll() is None and time.monotonic() < deadline
            time.sleep(.05)
        sample = Poller(dict(config(),host="127.0.0.1",port=port,unit_id=1,
                             read_temperature=True)).sample()
        assert sample["state"] == expected_state
        assert sample["voltage"] == 230
        assert sample["temperature_c"] == 35
        assert (sample["power_kw"] > 8) if scenario == "day" else (sample["power_kw"] == 0)
        assert client.read_input_registers(123,1,slave=1).exception_code == 2
        assert client.write_register(49151,123,slave=1).isError()
        assert client.read_holding_registers(49151,1,slave=1).isError()
        assert client.read_input_registers(49151,1,slave=1).registers[0] != 123
    finally:
        client.close()
        process.terminate()
        process.wait(timeout=5)

def test_simulator_dynamic_scale_and_absent_scale():
    for scale in (None, 0, 1, 0x019C):
        block = DeltaRegisters("night", scale)
        assert block.getValues(49152)[0] == 2300
        assert block.validate(40994,1) == (scale is not None)
        context = ReadOnlyContext(ir=block, zero_mode=True)
        assert not context.validate(6,49151,1)
    with pytest.raises(ValueError):
        DeltaRegisters("day", 1 << 3).getValues(49151)

@pytest.mark.parametrize("rc", [mqtt.MQTT_ERR_SUCCESS, mqtt.MQTT_ERR_NO_CONN])
def test_early_callback_and_disconnected_publish_ack(rc, monkeypatch):
    p = Publisher({"client_id":"test-edge","host":"localhost","port":1883}, "test")
    p.ready.set()
    callback_threads = []
    def publish(*args,**kwargs):
        thread = threading.Thread(target=p.on_publish,args=(None,None,42,0,None))
        thread.start()
        callback_threads.append(thread)
        info = mqtt.MQTTMessageInfo(42)
        info.rc = rc
        return info
    monkeypatch.setattr(p.client,"publish",publish)
    assert p.publish("literal-payload")
    for thread in callback_threads:
        thread.join()
    assert p.inflight is None

def test_publish_timeout_and_wrong_ack_preserve_row(monkeypatch):
    p = Publisher({"client_id":"test-edge","host":"localhost","port":1883}, "test")
    assert not p.publish("literal")
    p.on_connect(None,None,None,0,None)
    event = threading.Event()
    monkeypatch.setattr(event,"wait",lambda timeout: event.is_set())
    p.inflight = ("literal", 7, event)
    p.on_publish(None,None,8,0,None)
    assert not p.publish("literal")
    with pytest.raises(RuntimeError):
        p.publish("different")
    p.on_publish(None,None,7,0,None)
    assert p.publish("literal")
    p.on_disconnect(None,None,None,None,None)
    assert not p.ready.is_set()
    p.on_connect(None,None,None,5,None)
    assert not p.ready.is_set()

def test_tls_and_missing_credentials(monkeypatch):
    config = dict(client_id="test-edge",host="localhost",port=8883,tls=True,
                  username_env="DELTA_TEST_USER",password_env="DELTA_TEST_PASSWORD")
    with pytest.raises(ValueError):
        Publisher(config,"test")
    monkeypatch.setenv("DELTA_TEST_USER","test")
    monkeypatch.setenv("DELTA_TEST_PASSWORD","test-only")
    p = Publisher(config,"test")
    assert p.client._ssl_context.check_hostname
    assert p.client._ssl_context.verify_mode == 2
