from types import SimpleNamespace
import pytest
from delta_device.poller import Poller, ReadError, make_client
from test_protocol import fixture

class Client:
    def __init__(self, scale=1, exception=None):
        self.scale, self.exception = scale, exception
        self.calls, self.closed = [], False
    def connect(self):
        return True
    def close(self):
        self.closed = True
    def read_input_registers(self, address, count, slave):
        self.calls.append((address,count,slave))
        if address == 40994 and self.exception:
            return SimpleNamespace(isError=lambda: True, exception_code=self.exception)
        regs = dict(fixture(), **{})
        regs.update({40995:self.scale,40962:42,53250:0,53251:0,53254:0,53255:0})
        return SimpleNamespace(isError=lambda: False,
                               registers=[regs[a+1] for a in range(address,address+count)])

def config():
    return dict(transport="tcp",host="localhost",port=5021,timeout=1,
                address_base=1,unit_id=7)

def test_wire_address_and_illegal_address_fallback():
    client = Client(exception=2)
    assert Poller(config(), client).sample()["power_kw"] == 9
    assert client.calls == [(40994,1,7),(49151,13,7),(53247,9,7)]
    assert client.closed
    assert Poller(config(), Client(scale=0)).sample()["today_energy_kwh"] == 65.659

def test_other_exception_and_short_response_not_default():
    with pytest.raises(ReadError):
        Poller(config(), Client(exception=4)).sample()
    c = Client()
    c.read_input_registers = lambda *a, **k: SimpleNamespace(isError=lambda:False,registers=[])
    with pytest.raises(ReadError):
        Poller(config(), c).sample()
    c.connect = lambda:False
    with pytest.raises(ReadError):
        Poller(config(), c).sample()

def test_rtu_constructor_has_8n1_defaults():
    c = make_client(dict(config(),transport="rtu",serial_port="/dev/test",baudrate=19200))
    assert c.comm_params.baudrate == 19200
    assert c.comm_params.bytesize == 8
    assert c.comm_params.parity == "N"
    assert c.comm_params.stopbits == 1
