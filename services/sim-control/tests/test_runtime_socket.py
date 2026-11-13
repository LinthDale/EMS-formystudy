"""Actual TCP/HTTP wrapper tests, isolated in one container per simulator."""
import json
import os
import socket
import struct
import subprocess
import sys
import time
from uuid import uuid4
import httpx
import pytest

KIND = os.environ.get("SIMULATOR_KIND")
pytestmark = pytest.mark.skipif(KIND not in ("meter", "plc", "delta"), reason="socket adapter only")


@pytest.fixture(scope="module")
def runtime():
    token = "isolated-test-service-token-1234567890"
    env = {**os.environ, "SIM_CONTROL_TOKEN": token}
    process = subprocess.Popen([sys.executable, "-m", "sim_control"], env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    client = httpx.Client(base_url="http://127.0.0.1:9000",
                          headers={"Authorization": "Bearer " + token}, timeout=2)
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                if client.get("/state").status_code == 200:
                    break
            except httpx.TransportError:
                pass
            if process.poll() is not None:
                pytest.fail(process.stderr.read().decode())
            time.sleep(.05)
        else:
            pytest.fail("runtime failed to start")
        yield client
    finally:
        client.close()
        process.terminate()
        process.communicate(timeout=5)


def packet(pdu):
    port = 5021 if KIND == "delta" else 5020
    with socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
        sock.sendall(struct.pack(">HHHB", 7, 0, len(pdu) + 1, 1) + pdu)
        header = bytearray()
        while len(header) < 7:
            data = sock.recv(7 - len(header))
            assert data
            header.extend(data)
        count = struct.unpack(">HHHB", header)[2] - 1
        result = bytearray()
        while len(result) < count:
            data = sock.recv(count - len(result))
            assert data
            result.extend(data)
        return bytes(result)


@pytest.mark.parametrize("pdu", [
    bytes.fromhex("050000ff00"), bytes.fromhex("060004007b"),
    bytes.fromhex("0f000000010101"), bytes.fromhex("100004000102007b"),
    bytes.fromhex("1600040000ffff"), bytes.fromhex("17000400010004000102007b"),
])
def test_network_write_function_codes_are_rejected(runtime, pdu):
    reply = packet(pdu)
    assert reply[0] == pdu[0] + 128, reply.hex()
    assert reply[1] in (1, 2), reply.hex()


def test_typed_control_changes_actual_registers_and_legacy_rest_is_absent(runtime):
    changes = {"meter": {"fault_mode": "zero"}, "plc": {"motor_speed": 1234, "pump_on": True},
               "delta": {"scenario": "night"}}[KIND]
    before = runtime.get("/state").json()
    body = dict(request_id=str(uuid4()), expected_instance_id=before["instance_id"],
                expected_revision=before["revision"], changes=changes,
                reason="isolated wire test", deadline=time.time() + 10)
    response = runtime.post("/apply", json=body)
    assert response.status_code == 200, response.text
    assert runtime.post("/apply", json=body).json() == response.json()
    for key, value in changes.items():
        assert response.json()["after"]["settings"][key] == value
    if KIND == "meter":
        time.sleep(1.1)
        assert packet(bytes.fromhex("0300000002")) == bytes.fromhex("030400000000")
    elif KIND == "plc":
        assert packet(bytes.fromhex("0300040001")) == bytes.fromhex("030204d2")
        assert packet(bytes.fromhex("0100000001")) == bytes.fromhex("010101")
    else:
        assert packet(bytes.fromhex("04bfff0001")) == bytes.fromhex("04020000")
    assert runtime.post("/config", params={"noise_voltage_v": 9}).status_code == 404
    assert runtime.post("/inject-fault", params={"mode": "zero"}).status_code == 404
    assert runtime.get("/state", headers={"Authorization": "Bearer wrong"}).status_code == 401
