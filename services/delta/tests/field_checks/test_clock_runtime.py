"""Full edge/real Modbus TCP/SQLite/TLS flow with only UTC source and phase pacing injected."""
from contextlib import contextmanager
import logging
from pathlib import Path
import queue
import signal
import socket
import subprocess
import sys
import threading
import pytest
from delta_device import edge
from delta_device.config import validate
from delta_device.delivery import ClockGuard, Outbox
from delta_device.poller import Poller
from delta_device.publisher import Publisher
from conftest import config, until, EVIDENCE, T0

pytestmark = pytest.mark.integration


@pytest.fixture
def modbus_server():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0))
        port = probe.getsockname()[1]
    log = (EVIDENCE/'clock-modbus.log').open('a')
    child = subprocess.Popen([sys.executable,'-m','delta_device','simulator','--port',str(port)],
                             stdout=log,stderr=log)
    def listening():
        assert child.poll() is None, 'private Modbus simulator exited'
        try:
            with socket.create_connection(('127.0.0.1',port),timeout=.2): return True
        except OSError:
            return False
    try:
        until(listening)
        yield port
    finally:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)
        log.close()


@contextmanager
def runtime(monkeypatch, port, name, upload=True):
    directory = EVIDENCE/name
    directory.mkdir(exist_ok=True)
    synced = directory/'synchronized'
    settings = validate(dict(mode='field',device_id='clock-probe',
        modbus=dict(transport='tcp',host='127.0.0.1',port=port,unit_id=1,address_base=1,timeout=1),
        mqtt=config(),outbox_path=str(directory/'state/outbox.db'),clock_sync_file=str(synced)))
    settings['poll_interval'] = .01  # Phase pacing only; not a sampling-rate acceptance test.
    requested, permits, progress = queue.Queue(), queue.Queue(), queue.Queue()
    shutdown, errors, polls, commits, publishers = {}, [], [], [], []
    uploading = threading.Event()
    if upload: uploading.set()
    class InjectedClock(ClockGuard):
        def timestamp(self, now=None):
            requested.put(True)
            value = permits.get(timeout=10)
            if value is None: raise StopIteration('test phase complete')
            return super().timestamp(now=value)
    class ObservedPoller(Poller):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw)
            polls.append(self)
        def sample(self):
            value = super().sample()
            polled.append(value)
            return value
    polled=[]
    class ObservedBox(Outbox):
        def enqueue(self,*args):
            super().enqueue(*args)
            commits.append(args)
    class GatedPublisher(Publisher):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw)
            publishers.append(self)
        def publish(self,payload):
            return super().publish(payload) if uploading.is_set() else False
    class Progress(logging.Handler):
        def emit(self, record):
            if record.msg.startswith(('sample_queued','sample_rejected')):
                progress.put(record.getMessage().split()[0])
    handler = Progress()
    previous_level = edge.LOG.level
    edge.LOG.setLevel(logging.INFO)
    edge.LOG.addHandler(handler)
    def worker():
        try: edge.run(settings)
        except BaseException as exc: errors.append(type(exc).__name__)
    thread = threading.Thread(target=worker,name='isolated-clock-edge')
    ledger=[]
    def drive(label, now, synchronized, accepted):
        requested.get(timeout=10)
        if synchronized: synced.touch()
        else: synced.unlink(missing_ok=True)
        before = len(polled), len(commits)
        permits.put(now)
        result = progress.get(timeout=10)
        assert result == ('sample_queued' if accepted else 'sample_rejected'), label
        assert (len(polled)-before[0],len(commits)-before[1]) == ((1,1) if accepted else (0,0)), label
        ledger.append(dict(phase=label,injected_time_ns=now,synchronized=synchronized,
                           accepted=accepted,polls=len(polled)-before[0],commits=len(commits)-before[1]))
    with monkeypatch.context() as patch:
        patch.setattr(edge,'ClockGuard',InjectedClock)
        patch.setattr(edge,'Poller',ObservedPoller)
        patch.setattr(edge,'Outbox',ObservedBox)
        patch.setattr(edge,'Publisher',GatedPublisher)
        patch.setattr(edge.signal,'signal',lambda sig,fn:shutdown.__setitem__(sig,fn))
        thread.start()
        try:
            until(lambda:bool(publishers) and publishers[0].ready.is_set())
            yield drive,uploading,commits,ledger,settings
        finally:
            if signal.SIGTERM in shutdown: shutdown[signal.SIGTERM](None,None)
            permits.put(None)
            thread.join(timeout=12)
            for poller in polls: poller.client.close()
            edge.LOG.removeHandler(handler)
            edge.LOG.setLevel(previous_level)
            assert not thread.is_alive(), 'owned edge thread did not stop'
            assert not errors, 'edge runtime failed: '+repr(errors)


def assert_delivered(receiver, commits):
    until(lambda:len(receiver)==len(commits))
    assert receiver==[('ems/devices/clock-probe/measurements',args[1]) for args in commits], 'source time or snapshot changed'


def test_unsynced_backward_equal_invalid_time_rejects_while_backlog_drains(monkeypatch,modbus_server,receiver,record):
    with runtime(monkeypatch,modbus_server,'clock-phases',upload=False) as (drive,upload,commits,ledger,settings):
        drive('cold-start-unsynchronized',T0,False,False)
        drive('synchronized-valid',T0,True,True)
        box = Outbox(settings['outbox_path'],10000,'clock-probe')
        assert box.pending_count()==1 and receiver==[], 'first pending sample was not retained'
        drive('sync-lost',T0+10**9,False,False)
        upload.set()
        assert_delivered(receiver,commits)
        until(lambda:box.pending_count()==0)
        assert len(commits)==1, 'lost sync created a new sample'
        drive('sync-restored',T0+2*10**9,True,True)
        drive('time-backward',T0+10**9,True,False)
        drive('same-time',T0+2*10**9,True,False)
        drive('pre-2025-time',1600000000000000000,True,False)
        drive('time-recovered',T0+3*10**9,True,True)
        assert_delivered(receiver,commits)
        until(lambda:box.pending_count()==0)
        assert len(commits)==3 and len(receiver)==3, 'incorrect accepted sample set'
        record(phases=ledger,committed=3,received=3,pending=0,
               scope='production edge + real TCP Poller/SQLite/TLS; injected UTC and sender permit')


def test_restart_uses_persisted_last_timestamp(monkeypatch,modbus_server,receiver,record):
    all_commits=[]
    all_phases=[]
    for boot in (1,2):
        with runtime(monkeypatch,modbus_server,'clock-restart') as (drive,upload,commits,ledger,settings):
            if boot==1:
                drive('first-boot',T0+10*10**9,True,True)
            else:
                drive('restart-time-behind-last-commit',T0+9*10**9,True,False)
                drive('restart-time-recovered',T0+11*10**9,True,True)
            all_commits.extend(commits)
            all_phases.extend(ledger)
            assert_delivered(receiver,all_commits)
            until(lambda:Outbox(settings['outbox_path'],10000,'clock-probe').pending_count()==0)
    assert len(receiver)==2 and len(all_commits)==2, 'restart lost or duplicated a sample'
    record(phases=all_phases,boots=2,committed=2,received=2,pending=0)
