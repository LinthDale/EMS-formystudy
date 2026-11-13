"""Production sample over actual pymodbus, using memory serial instead of USB."""
import struct

import pytest

from delta_device import poller as module
from delta_device.poller import Poller, ReadError
from test_protocol import fixture
from test_rtu import crc


class MemoryDevice:
    def __init__(self):
        self.round = 0
        self.requests = []
        self.handles = []
        self.old_ac = None
        self.old_on_next_ac = True
        self.queued_input = b''

    def open(self, *args, **kwargs):
        handle = MemoryPort(self, kwargs['timeout'])
        self.handles.append(handle)
        return handle

    def reply(self, packet):
        assert packet[-2:] == crc(packet[:-2]), 'request CRC invalid'
        unit, fc, address, count = struct.unpack('>BBHH', packet[:6])
        assert unit == 1 and fc == 4, 'unexpected request identity'
        self.requests.append((address, count))
        registers = fixture()
        registers.update({40995: 1, 53250: 0, 53251: 0, 53254: 0, 53255: 0})
        if address == 40994:
            self.round += 1
        if self.round >= 2:
            for address_v in (49153, 49157, 49161):
                registers[address_v] = 2400
            registers[49152] = 9360
        data = b''.join(struct.pack('>H', registers[a+1]) for a in range(address, address+count))
        body = bytes((unit, fc, len(data))) + data
        response = body + crc(body)
        if address == 49151:
            if self.round == 1:
                self.old_ac = response
                return b''  # Sample 1 must time out and close its COM handle.
            # Sample 2 receives the prior AC frame only after sending its own AC
            # request. Closing/reopening and flushing before send cannot remove it.
            if self.old_on_next_ac:
                return self.old_ac
        return response


class MemoryPort:
    def __init__(self, device, timeout):
        self.device, self.timeout = device, timeout
        self.pending, device.queued_input = device.queued_input, b''
        self.is_open = True
        self.inter_byte_timeout = None
        self.resets = 0

    @property
    def in_waiting(self):
        return len(self.pending)

    def write(self, data):
        self.pending += self.device.reply(data)
        return len(data)

    def read(self, size):
        data, self.pending = self.pending[:size], self.pending[size:]
        return data

    def reset_input_buffer(self):
        self.pending = b''
        self.resets += 1

    def close(self):
        self.is_open = False


def rtu_config():
    return dict(transport='rtu', serial_port='MEMORY', baudrate=19200,
                timeout=.01, unit_id=1, address_base=1)


def test_timeout_then_new_sample_cannot_accept_prior_ac_frame_without_bound(monkeypatch):
    device = MemoryDevice()
    monkeypatch.setattr(module, 'platform', 'win32')
    monkeypatch.setattr('serial.serial_for_url', device.open)
    poller = Poller(rtu_config())
    with pytest.raises(ReadError):
        poller.sample()
    assert not device.handles[0].is_open, 'failed sample left old handle open'
    first_requests = len(device.requests)
    try:
        with pytest.raises(ReadError):
            poller.sample()
        assert len(device.requests) == first_requests, 'uncertain bus sent another request'
    finally:
        poller.client.close()


def install_device(monkeypatch):
    device = MemoryDevice()
    monkeypatch.setattr(module, 'platform', 'win32')
    monkeypatch.setattr('serial.serial_for_url', device.open)
    now = [100.0]
    monkeypatch.setattr(module, 'monotonic', lambda: now[0], raising=False)
    return device, now


def bounded_config():
    return dict(rtu_config(), response_lifetime_seconds=.5,
                response_lifetime_source='memory fixture: all delayed bytes delivered within .5s')


def test_unknown_bound_lock_survives_reconnect_and_elapsed_time(monkeypatch):
    device, now = install_device(monkeypatch)
    poller = Poller(rtu_config())
    with pytest.raises(ReadError):
        poller.sample()
    before = len(device.requests)
    now[0] += 86400
    assert poller.client.connect(), 'fixture could not reopen the handle'
    try:
        with pytest.raises(ReadError):
            poller.read(49152, 13)
        assert len(device.requests) == before, 'reconnect or elapsed time bypassed unknown bound'
    finally:
        poller.client.close()


def test_qualified_guard_discards_queued_old_frame_then_reads_fresh_sample(monkeypatch):
    device, now = install_device(monkeypatch)
    poller = Poller(bounded_config())
    with pytest.raises(ReadError):
        poller.sample()
    before = len(device.requests)
    device.queued_input = device.old_ac  # Late response arrives inside declared lifetime.
    device.old_on_next_ac = False
    now[0] += .49
    with pytest.raises(ReadError):
        poller.sample()
    assert len(device.requests) == before, 'guard sent a request before its deadline'
    now[0] += .02
    snapshot = poller.sample()
    assert snapshot['voltage'] == 240, f'old AC reply contaminated sample: {snapshot}'
    assert snapshot['power_kw'] == 9.36, 'fresh AC block was not decoded'
    assert device.handles[-1].resets >= 1, 'recovery did not discard queued serial input'
    assert all(not handle.is_open for handle in device.handles), 'handle leaked after sample'


def test_field_startup_requires_bound_before_opening_serial(monkeypatch):
    device, _ = install_device(monkeypatch)
    with pytest.raises(ValueError):
        Poller(rtu_config(), mode='field')
    assert not device.handles, 'unqualified field profile opened serial'


def test_field_restart_waits_lifetime_before_first_request(monkeypatch):
    device, now = install_device(monkeypatch)
    poller = Poller(bounded_config(), mode='field')
    with pytest.raises(ReadError):
        poller.sample()
    assert not device.requests and not device.handles, 'field startup bypassed quarantine'
    now[0] += .51
    # Start a second process-equivalent object: it must quarantine independently.
    restarted = Poller(bounded_config(), mode='field')
    with pytest.raises(ReadError):
        restarted.sample()
    assert not device.requests, 'new object skipped field startup quarantine'
    now[0] += .51
    device.round = 1
    device.old_on_next_ac = False
    snapshot = restarted.sample()
    assert snapshot['voltage'] == 240, 'field did not resume after qualified startup guard'


@pytest.mark.parametrize('value', [0, -.1, True, float('nan'), float('inf'), 121, '1'])
def test_invalid_response_lifetime_never_opens_serial(monkeypatch, value):
    device, _ = install_device(monkeypatch)
    config = dict(bounded_config(), response_lifetime_seconds=value)
    with pytest.raises(ValueError):
        Poller(config)
    assert not device.handles, 'invalid lifetime opened serial'


@pytest.mark.parametrize('source', [None, '', ' ', 123, 'x'*257])
def test_response_lifetime_requires_traceable_source(monkeypatch, source):
    device, _ = install_device(monkeypatch)
    config = dict(bounded_config(), response_lifetime_source=source)
    with pytest.raises(ValueError):
        Poller(config)
    assert not device.handles, 'missing bound provenance opened serial'


@pytest.mark.parametrize('failure', ['connect', 'buffer'])
def test_recovery_failure_keeps_lock_and_closes_handle(monkeypatch, failure):
    from types import SimpleNamespace
    device, now = install_device(monkeypatch)
    poller = Poller(bounded_config())
    with pytest.raises(ReadError):
        poller.sample()
    now[0] += .51
    closed = []
    def broken_reset():
        raise OSError('fixture reset failed')
    client = SimpleNamespace(connect=lambda: failure != 'connect',
        socket=SimpleNamespace(reset_input_buffer=broken_reset),
        close=lambda: closed.append(True))
    monkeypatch.setattr(module, 'make_client', lambda _: client)
    before = len(device.requests)
    with pytest.raises((ReadError, OSError)):
        poller.sample()
    assert closed and poller._uncertain_since is not None
    assert len(device.requests) == before


def test_guard_starts_at_poison_not_after_slow_close(monkeypatch):
    device, now = install_device(monkeypatch)
    poller = Poller(bounded_config())
    original_close = poller.client.close
    close_starts = []
    def slow_close():
        close_starts.append(now[0])
        now[0] += .1
        original_close()
    poller.client.close = slow_close
    with pytest.raises(ReadError):
        poller.sample()
    assert poller._uncertain_since == close_starts[-2]
    assert now[0] > poller._uncertain_since
    assert now[0] - poller._uncertain_since == pytest.approx(.2)
    assert poller.recovery_remaining == pytest.approx(.3)


@pytest.mark.parametrize('code', [2, 4])
def test_valid_server_exception_does_not_poison_bus(monkeypatch, code):
    from test_poller import Client
    client = Client(exception=code)
    poller = Poller(rtu_config(), client)
    with pytest.raises(ReadError):
        poller.read(40995, 1)
    assert poller._uncertain_since is None
    client.exception = None
    assert poller.read(40995, 1) == [1]


@pytest.mark.parametrize('kind', ['io', 'short', 'wrong_function'])
def test_ambiguous_reply_locks_subsequent_reads(kind):
    from types import SimpleNamespace
    from test_poller import Client
    client = Client()
    calls = []
    def reply(*args, **kwargs):
        calls.append(True)
        if kind == 'io':
            raise OSError('fixture port lost')
        return SimpleNamespace(isError=lambda: False, registers=[] if kind == 'short' else [1],
                               function_code=3 if kind == 'wrong_function' else 4)
    client.read_input_registers = reply
    poller = Poller(rtu_config(), client)
    with pytest.raises((OSError, ReadError)):
        poller.read(40995, 1)
    with pytest.raises(ReadError):
        poller.read(40995, 1)
    assert len(calls) == 1 and client.closed


def test_pre_request_connect_failure_can_retry():
    from test_poller import Client
    client = Client()
    client.connect = lambda: False
    poller = Poller(rtu_config(), client)
    with pytest.raises(ReadError):
        poller.sample()
    assert not client.calls and poller._uncertain_since is None
    client.connect = lambda: True
    assert poller.sample()['voltage'] == 230


def test_existing_outbox_drains_while_real_poller_is_locked(tmp_path, monkeypatch):
    import signal
    import threading
    import time
    from delta_device import edge
    from delta_device.delivery import Outbox, encode_line
    from test_delivery import config, snapshot
    device, _ = install_device(monkeypatch)
    poller = Poller(rtu_config())
    with pytest.raises(ReadError):
        poller.sample()
    before = len(device.requests)
    c = config(tmp_path)
    c.update(queue_limit=10, batch_size=10, poll_interval=.01)
    c['modbus'] = rtu_config()
    box = Outbox(c['outbox_path'], 10, c['device_id'])
    seeded_ns = time.time_ns() - 1_000_000_000
    payload = encode_line(c['device_id'], snapshot(), seeded_ns)
    box.enqueue(seeded_ns, payload, snapshot())
    shutdown, delivered, errors = {}, [], []
    attempted = threading.Event()
    real_sample = poller.sample
    def sample():
        try:
            return real_sample()
        finally:
            attempted.set()
    poller.sample = sample
    class Publisher:
        def __init__(self, *args): pass
        def start(self): pass
        def close(self): pass
        def publish(self, data):
            if attempted.wait(2):
                delivered.append(data)
            else:
                errors.append('collector never attempted a locked sample')
            shutdown[signal.SIGTERM](None, None)
            return not errors
    monkeypatch.setattr(edge, 'Poller', lambda *a, **kw: poller)
    monkeypatch.setattr(edge, 'Publisher', Publisher)
    monkeypatch.setattr(edge.signal, 'signal', lambda sig, fn: shutdown.__setitem__(sig, fn))
    worker = threading.Thread(target=edge.run, args=(c,), daemon=True)
    worker.start()
    worker.join(timeout=4)
    if worker.is_alive():
        shutdown[signal.SIGTERM](None, None)
        worker.join(timeout=2)
        pytest.fail('edge sender failed to terminate')
    assert not errors and delivered == [payload] and box.pending_count() == 0
    assert len(device.requests) == before, 'sender bypassed the collection lock'


def test_cli_once_passes_mode_and_waits_startup_guard(monkeypatch, capsys):
    from delta_device import __main__ as cli
    c = {'mode': 'field', 'modbus': bounded_config()}
    remaining, sleeps, modes = [.2], [], []
    class FakePoller:
        def __init__(self, config, *, mode): modes.append(mode)
        @property
        def recovery_remaining(self): return remaining[0]
        def sample(self):
            assert remaining[0] == 0
            return {'voltage': 240}
    def sleep(seconds):
        sleeps.append(seconds)
        remaining[0] = max(0, remaining[0] - seconds)
    monkeypatch.setattr('sys.argv', ['delta_device', 'edge', '--config', 'fixture', '--once'])
    monkeypatch.setattr(cli, 'load_config', lambda _: c)
    monkeypatch.setattr(cli, 'Poller', FakePoller)
    monkeypatch.setattr(cli.time, 'sleep', sleep)
    cli.main()
    assert modes == ['field'] and sleeps == [.1, .1]
    assert '240' in capsys.readouterr().out
