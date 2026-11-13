"""Windows USB delivery gaps must not truncate otherwise valid RTU frames."""
import pytest

from delta_device.poller import Poller, ReadError, make_client
from test_rtu import crc


class FragmentedWindowsSerial:
    """Model ReadFile returning early when an inter-byte timeout is enabled.

    The complete reply arrives within the overall read timeout. With a tiny
    interval timeout Windows may return only the first USB-delivered fragment.
    Without it, read(size) waits for the requested bytes or the overall timeout.
    """

    def __init__(self, response):
        self.response = response
        self.pending = b""
        self.inter_byte_timeout = None
        self.is_open = True
        self.requests = []

    @property
    def in_waiting(self):
        return len(self.pending)

    def write(self, request):
        self.requests.append(request)
        self.pending = self.response
        return len(request)

    def read(self, size):
        if self.inter_byte_timeout is not None:
            size = min(size, 1)
        result, self.pending = self.pending[:size], self.pending[size:]
        return result

    def close(self):
        self.is_open = False


def serial_config():
    return dict(transport="rtu", serial_port="COM4", baudrate=19200,
                unit_id=1, address_base=1, timeout=.02)


def install_serial(monkeypatch, response, platform="win32"):
    from delta_device import poller

    monkeypatch.setattr(poller, "platform", platform, raising=False)
    port = FragmentedWindowsSerial(response)
    monkeypatch.setattr("pymodbus.client.serial.serial.serial_for_url",
                        lambda *args, **kwargs: port)
    return port


def test_windows_usb_fragments_complete_before_timeout_decode(monkeypatch):
    body = bytes.fromhex("01040208fc")  # Independent literal: 2300 -> 230 V.
    port = install_serial(monkeypatch, body + crc(body))
    client = make_client(serial_config())
    try:
        assert client.connect(), "serial fixture failed to connect"
        registers = Poller(serial_config(), client).read(49153, 1)
        assert registers == [2300], f"fragmented response decoded as {registers}"
        assert len(port.requests) == 1, "fix must not resend the request"
    finally:
        client.close()


@pytest.mark.parametrize("kind", ["crc", "wrong_unit", "truncated", "absent"])
def test_windows_invalid_or_missing_frame_still_rejected(monkeypatch, kind):
    body = bytes.fromhex("02040208fc" if kind == "wrong_unit" else "01040208fc")
    response = body + crc(body)
    if kind == "crc":
        response = response[:-1] + bytes([response[-1] ^ 1])
    elif kind == "truncated":
        response = response[:-2]
    elif kind == "absent":
        response = b""
    install_serial(monkeypatch, response)
    client = make_client(serial_config())
    try:
        assert client.connect(), "serial fixture failed to connect"
        with pytest.raises(ReadError):
            Poller(serial_config(), client).read(49153, 1)
    finally:
        client.close()


def test_linux_inter_byte_timing_is_preserved(monkeypatch):
    port = install_serial(monkeypatch, b"", platform="linux")
    client = make_client(serial_config())
    try:
        assert client.connect(), "serial fixture failed to connect"
        assert port.inter_byte_timeout > 0, "Linux RTU timing changed"
        assert client.comm_params.timeout_connect == .02, "overall timeout changed"
    finally:
        client.close()
