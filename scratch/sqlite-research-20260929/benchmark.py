"""Isolated SQLite sizing and crash probe; NOT a Raspberry Pi benchmark."""
import json, os, platform, sqlite3, statistics, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, "/source")
from delta_device.delivery import Outbox, encode_line

snapshot = {"profile":"delta-three-phase-v1.35","scale_word":1,"voltage":230.0,
            "current":13.04,"power_kw":9.0,"energy_kwh":1234.56,
            "today_energy_kwh":15.0,"state":2,"phases":[
                {"voltage":230.0,"current":13.04,"power_kw":3.0,"frequency_hz":60.0}
                for _ in range(3)],"temperature_c":35}
start_ns = 1790640000000000000
payload = encode_line("delta-site-001",snapshot,start_ns)
encoded = json.dumps(snapshot,allow_nan=False,separators=(",",":"))
result={"environment":{"python":platform.python_version(),"sqlite":sqlite3.sqlite_version,
                       "platform":platform.platform(),
                       "storage":"Docker temporary filesystem on WSL host; not Pi/SD"},
        "sample":{"ilp_bytes":len(payload.encode()),"snapshot_bytes":len(encoded.encode())},
        "occupancy":[],"cycles":[],"process_crash":[]}

def p95(values):
    return sorted(values)[int((len(values)-1)*.95)]

with tempfile.TemporaryDirectory(prefix="delta-sqlite-research-") as temp:
    root=Path(temp)
    box=Outbox(root/"sizing"/"outbox.db",1000000,"delta-site-001")
    total=0
    for target in (10000,60480,483840):
        with box.connect() as db:
            for offset in range(total,target,5000):
                rows=[(start_ns+i*10000000000,payload,encoded)
                      for i in range(offset,min(offset+5000,target))]
                db.executemany("INSERT INTO outbox(sampled_ns,payload,snapshot) VALUES(?,?,?)",rows)
                db.commit()
        total=target
        elapsed=[]
        for _ in range(10):
            t=time.perf_counter();assert box.pending_count()==target
            elapsed.append((time.perf_counter()-t)*1000)
        with box.connect() as db:
            page_count=db.execute("PRAGMA page_count").fetchone()[0]
            page_size=db.execute("PRAGMA page_size").fetchone()[0]
        result["occupancy"].append({"rows":target,"db_bytes":box.path.stat().st_size,
                "allocated_bytes_per_row":round(page_count*page_size/target,2),
                "count_p95_ms":round(p95(elapsed),3)})
    # Exercise current Outbox enqueue and ACK transactions, not bulk sizing code.
    for mode,sync in (("DELETE","FULL"),("DELETE","EXTRA"),("WAL","FULL")):
        probe=Outbox(root/("cycle-"+mode+"-"+sync)/"outbox.db",10000,"delta-site-001")
        times=[]
        # For alternatives explicitly set each connection's synchronous value.
        from contextlib import contextmanager
        @contextmanager
        def connection(path=probe.path):
            c=sqlite3.connect(path,timeout=5)
            try:
                c.execute("PRAGMA synchronous="+sync)
                with c: yield c
            finally:c.close()
        probe.connect=connection
        with probe.connect() as db: db.execute("PRAGMA journal_mode="+mode)
        for i in range(250):
            t=time.perf_counter()
            probe.enqueue(start_ns+i*10000000000,payload,snapshot)
            row=probe.pending(1)[0]
            probe.ack(row[0])
            times.append((time.perf_counter()-t)*1000)
        result["cycles"].append({"mode":mode,"synchronous":sync,"cycles":250,
                "enqueue_select_ack_p50_ms":round(statistics.median(times),3),
                "enqueue_select_ack_p95_ms":round(p95(times),3),
                "note":"No WAN RTT; open/close per operation, no concurrent writers; not Pi throughput"})
    for mode,sync in (("DELETE","EXTRA"),("WAL","FULL")):
        dbfile=root/("crash-"+mode+".db")
        child = """import os,sqlite3,sys
c=sqlite3.connect(sys.argv[1])
c.execute('PRAGMA journal_mode='+sys.argv[2])
c.execute('PRAGMA synchronous='+sys.argv[3])
c.execute('CREATE TABLE samples(id INTEGER PRIMARY KEY)')
c.commit()
for n in range(100):
 c.execute('INSERT INTO samples VALUES(?)',(n,));c.commit()
c.execute('BEGIN IMMEDIATE')
c.execute('INSERT INTO samples VALUES(999)')
os._exit(9)
"""
        p=subprocess.run([sys.executable,"-c",child,str(dbfile),mode,sync],check=False)
        with sqlite3.connect(dbfile) as db:
            rows=db.execute("SELECT count(*) FROM samples").fetchone()[0]
            check=db.execute("PRAGMA integrity_check").fetchone()[0]
            assert rows==100 and check=="ok" and p.returncode==9
            result["process_crash"].append({"mode":mode,"sync":sync,"committed_rows_survived":rows,
                                            "uncommitted_row_absent":True,"integrity":check,
                                            "limitation":"Process exit only; not loss of OS cache or physical power"})
Path("/results/results.json").write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))

