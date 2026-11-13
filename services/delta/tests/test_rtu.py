"""Exercise real serial RTU bytes via a Linux pseudo-terminal, not RS-485 hardware."""
import os
import select
import struct
import threading
from delta_device.poller import Poller
from test_protocol import fixture


def crc(data):
    value = 0xffff
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0xa001 if value & 1 else 0)
    return struct.pack("<H", value)


def test_rtu_request_address_crc_and_response():
    master, slave = os.openpty()
    stopped = threading.Event()
    requests, errors = [], []
    regs = fixture()
    regs.update({40995:1,53250:0,53251:0,53254:0,53255:0})

    def device():
        pending = b""
        try:
            while not stopped.is_set():
                if not select.select([master], [], [], .05)[0]:
                    continue
                pending += os.read(master,256)
                if len(pending) < 8:
                    continue
                request, pending = pending[:8], pending[8:]
                assert request[-2:] == crc(request[:-2])
                unit, fc, address, count = struct.unpack(">BBHH", request[:6])
                assert unit == 3 and fc == 4
                requests.append((address,count))
                payload = b"".join(struct.pack(">H",regs[a+1]) for a in range(address,address+count))
                response = bytes([unit,4,len(payload)]) + payload
                os.write(master,response + crc(response))
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=device)
    worker.start()
    try:
        config = dict(transport="rtu",serial_port=os.ttyname(slave),baudrate=19200,
                      timeout=1,unit_id=3,address_base=1)
        sample = Poller(config).sample()
        assert sample["voltage"] == 230 and sample["energy_kwh"] == 655.38
        assert requests == [(40994,1),(49151,13),(53247,9)]
        assert not errors
    finally:
        stopped.set()
        worker.join(timeout=2)
        os.close(slave)
        os.close(master)
