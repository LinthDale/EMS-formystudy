"""Production RTU slave over PTY; these tests do not certify RS485 hardware."""
import os
import select
import struct
import subprocess
import sys
import time
from contextlib import contextmanager

import pytest

from test_rtu import crc


def receive(fd, timeout=0.3):
    data = b""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if select.select([fd], [], [], max(0, deadline - time.monotonic()))[0]:
            data += os.read(fd, 4096)
            # Responses here fit in one serial frame; allow fragmented delivery.
            if len(data) >= 5:
                length = 5 if data[1] & 0x80 else 5 + data[2]
                if len(data) >= length:
                    break
    return data


def request(fd, fc=4, address=49152, count=1, unit=7, body=None):
    payload = body or struct.pack(">BBHH", unit, fc, address, count)
    os.write(fd, payload + crc(payload))
    response = receive(fd)
    if response:
        assert response[-2:] == crc(response[:-2])
    return response


@contextmanager
def simulator(*args, voltage_address=49152):
    import tty
    master, slave = os.openpty()
    tty.setraw(slave)
    process = subprocess.Popen(
        [sys.executable, "-m", "delta_device", "simulator", "--transport", "rtu",
         "--serial-port", os.ttyname(slave), "--unit-id", "7", *args],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 5
        while True:
            assert process.poll() is None, "RTU simulator exited before responding"
            response = request(master, address=voltage_address)
            if response == b"\x07\x04\x02\x08\xfc" + crc(b"\x07\x04\x02\x08\xfc"):
                break
            assert time.monotonic() < deadline, "RTU simulator did not become ready"
            time.sleep(0.03)
        yield master
    finally:
        process.terminate()
        process.wait(timeout=5)
        os.close(slave)
        os.close(master)


@pytest.mark.skipif(not hasattr(os, "openpty"), reason="Linux PTY required")
@pytest.mark.parametrize("scenario,state", [("day", 2), ("night", 0), ("alarm", 4)])
def test_rtu_slave_raw_registers_and_readonly(scenario, state):
    with simulator("--scenario", scenario) as fd:
        # Independent literal voltage: 230.0 V is raw 2300 = 0x08fc.
        assert request(fd)[:5] == b"\x07\x04\x02\x08\xfc"
        assert request(fd, address=53255)[3:5] == struct.pack(">H", state)
        watts = int.from_bytes(request(fd, address=49151)[3:5], "big")
        assert 8400 <= watts <= 9600 if scenario == "day" else watts == 0
        assert request(fd, address=123)[1:3] == b"\x84\x02"
        for fc in (3, 6):
            response = request(fd, fc=fc, count=123)
            assert response[1] == fc | 0x80
        body = struct.pack(">BBHHBH", 7, 16, 49152, 1, 2, 123)
        assert request(fd, body=body)[1] == 0x90
        assert request(fd)[:5] == b"\x07\x04\x02\x08\xfc"


@pytest.mark.skipif(not hasattr(os, "openpty"), reason="Linux PTY required")
def test_rtu_slave_bad_crc_wrong_unit_broadcast_and_recovery():
    with simulator() as fd:
        for unit in (0, 8):
            assert request(fd, unit=unit) == b""
            assert request(fd, unit=unit, fc=6, count=123) == b""
        payload = struct.pack(">BBHH", 7, 4, 49152, 1)
        checksum = crc(payload)
        os.write(fd, payload + bytes([checksum[0] ^ 1, checksum[1]]))
        assert receive(fd) == b""
        assert request(fd)[:5] == b"\x07\x04\x02\x08\xfc"


@pytest.mark.parametrize("arguments", [
    ["--transport", "rtu"],
    ["--transport", "rtu", "--serial-port", "socket://localhost:502"],
    ["--transport", "rtu", "--serial-port", "COM5", "--baudrate", "0"],
    ["--transport", "rtu", "--serial-port", "COM5", "--port", "5021"],
    ["--serial-port", "COM5"],
    ["--baudrate", "19200"],
    ["--transport", "rtu", "--serial-port", "COM5", "--unit-id", "0"],
    ["--transport", "rtu", "--serial-port", "/dev/../tmp/test"],
])
def test_simulator_rejects_invalid_transport_arguments(arguments):
    result = subprocess.run(
        [sys.executable, "-m", "delta_device", "simulator", *arguments],
        capture_output=True, timeout=5,
    )
    assert result.returncode != 0


def test_unavailable_rtu_port_exits_instead_of_hanging():
    result = subprocess.run(
        [sys.executable, "-m", "delta_device", "simulator", "--transport", "rtu",
         "--serial-port", "/dev/ems-delta-no-such-port"],
        capture_output=True, timeout=5,
    )
    assert result.returncode == 1
    assert b"startup_failed" in result.stderr


@pytest.mark.skipif(not hasattr(os, "openpty"), reason="Linux PTY required")
@pytest.mark.parametrize("scale,base,baud", [("0", 0, "9600"), ("absent", 1, "38400")])
def test_rtu_polling_through_two_serial_endpoints(scale, base, baud):
    """Real Poller -> PTY cable bridge -> production RTU CLI -> pure decoder."""
    import threading
    import tty
    from delta_device.poller import Poller

    client_master, client_slave = os.openpty()
    tty.setraw(client_slave)
    stop = threading.Event()
    failures = []
    try:
        with simulator("--scenario", "night", "--scale", scale,
                       "--address-base", str(base), "--baudrate", baud,
                       voltage_address=49153-base) as server_master:
            def bridge():
                try:
                    while not stop.is_set():
                        ready, _, _ = select.select([client_master, server_master], [], [], 0.05)
                        for fd in ready:
                            other = server_master if fd == client_master else client_master
                            os.write(other, os.read(fd, 4096))
                except OSError as exc:
                    failures.append(exc)
            worker = threading.Thread(target=bridge)
            worker.start()
            try:
                sample = Poller(dict(transport="rtu", serial_port=os.ttyname(client_slave),
                                     baudrate=int(baud), unit_id=7, address_base=base,
                                     timeout=1, read_temperature=True)).sample()
                assert sample["voltage"] == 230
                assert sample["power_kw"] == 0
                assert sample["energy_kwh"] == 1234.56
                assert sample["temperature_c"] == 35
                assert not failures
            finally:
                stop.set()
                worker.join(timeout=2)
                assert not worker.is_alive()
    finally:
        os.close(client_slave)
        os.close(client_master)


def test_serial_server_cleanup_and_no_tcp_listener(monkeypatch):
    import asyncio
    from delta_device import simulator as module

    events = []

    class Serial:
        def __init__(self, **kwargs):
            events.append(kwargs["port"])

        async def serve_forever(self):
            events.append("listening")
            raise asyncio.CancelledError()

        async def shutdown(self):
            events.append("closed")

    async def forbidden_tcp(**kwargs):
        pytest.fail("RTU mode started a TCP listener")

    monkeypatch.setattr(module, "FailFastSerialServer", Serial)
    monkeypatch.setattr(module, "StartAsyncTcpServer", forbidden_tcp)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(module.serve_rtu("com5"))
    assert events == ["COM5", "listening", "closed"]
