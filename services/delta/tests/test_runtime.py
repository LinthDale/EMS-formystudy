import gc
import json
import os
import signal
import threading
import time
import pytest
from delta_device import edge
from delta_device.config import load_config, validate
from delta_device.delivery import Outbox
from test_delivery import config, snapshot

@pytest.mark.parametrize("section,key,value", [
    (None,"mode","unknown"), (None,"device_id","bad,id"),
    (None,"queue_limit",0), (None,"poll_interval",True),
    (None,"batch_size",101), (None,"outbox_path","relative"),
    (None,"unknown",1), ("modbus","transport","udp"),
    ("modbus","unit_id",0), ("modbus","address_base",2),
    ("modbus","host",""), ("modbus","read_temperature","yes"),
    ("modbus","typo",True), ("mqtt","host",""),
    ("mqtt","client_id","bad client"), ("mqtt","port",0),
    ("mqtt","tls","false"), ("mqtt","username_env","invalid-name"),
    ("mqtt","username_env","MISSING_PAIR"), ("mqtt","cert_file","cert.pem"),
    ("mqtt","typo",True),
])
def test_invalid_config_rejected(tmp_path,section,key,value):
    c = config(tmp_path)
    (c if section is None else c[section])[key] = value
    with pytest.raises(ValueError):
        validate(c)

def test_json_config_rtu_and_field_auth(tmp_path):
    c = config(tmp_path)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(c))
    assert load_config(path)["poll_interval"] == 10
    c["modbus"] = dict(transport="rtu")
    with pytest.raises(ValueError):
        validate(c)
    c["modbus"].update(serial_port="/dev/test",baudrate=123)
    with pytest.raises(ValueError):
        validate(c)
    c = config(tmp_path)
    c.update(mode="field",device_id="site-001")
    c["mqtt"]["tls"] = True
    with pytest.raises(ValueError):
        validate(c)

def test_spool_identity_size_and_connections_closed(tmp_path):
    path = tmp_path/"spool"/"outbox.db"
    box = Outbox(path,10,"device-a")
    with pytest.raises(ValueError):
        Outbox(path,10,"device-b")
    with pytest.raises(ValueError):
        box.enqueue(1,"x"*1025,snapshot())
    with pytest.raises(ValueError):
        box.enqueue(1,"x",{"huge":"x"*16385})
    link = tmp_path/"linked.db"
    link.symlink_to(path)
    with pytest.raises(ValueError):
        Outbox(link,10)
    gc.collect()
    before = len(os.listdir("/proc/self/fd"))
    gc.disable()
    try:
        for _ in range(150):
            box.pending(1)
        assert len(os.listdir("/proc/self/fd")) <= before + 2
    finally:
        gc.enable()

def test_edge_collects_while_sender_offline_and_restart_keeps_samples(tmp_path,monkeypatch):
    c = validate(config(tmp_path))
    c["poll_interval"] = .01  # Accelerate only inside this deterministic runtime test.
    clock = [1800000000000000000]
    shutdown = {}
    accepted, delivered = [], []
    online = threading.Event()
    ended = threading.Event()

    class TestClock:
        def __init__(self,*args):
            pass
        def timestamp(self):
            clock[0] += 1000000
            return clock[0]

    class TestPoller:
        def __init__(self,*args):
            pass
        def sample(self):
            accepted.append(clock[0])
            if len(accepted) == 1:
                raise ValueError("bad sample")
            if len(accepted) >= 4:
                online.set()
            return snapshot()

    class TestPublisher:
        def __init__(self,*args):
            pass
        def start(self):
            pass
        def publish(self,payload):
            if not online.is_set():
                return False
            delivered.append(payload)
            shutdown[signal.SIGTERM](None,None)
            return True
        def close(self):
            ended.set()

    monkeypatch.setattr(edge, "ClockGuard", TestClock)
    monkeypatch.setattr(edge, "Poller", TestPoller)
    monkeypatch.setattr(edge, "Publisher", TestPublisher)
    monkeypatch.setattr(edge.signal,"signal",lambda sig,fn: shutdown.__setitem__(sig,fn))
    worker = threading.Thread(target=edge.run,args=(c,))
    worker.start()
    worker.join(timeout=4)
    if worker.is_alive():
        shutdown[signal.SIGTERM](None,None)
        worker.join(timeout=2)
        pytest.fail("edge sender failed to resume")
    assert ended.is_set() and len(accepted) >= 4 and len(delivered) == 1
    box = Outbox(c["outbox_path"],c["queue_limit"],c["device_id"])
    assert len(box.pending(100)) >= 2
    assert delivered[0].endswith(str(accepted[1]))  # Original time, no restamping.
