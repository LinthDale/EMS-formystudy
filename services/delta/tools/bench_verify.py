"""Read-only DB/API comparison for a completed local bench ledger."""
import argparse
from datetime import datetime, timedelta, timezone
import http.cookiejar
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler, HTTPCookieProcessor

from bench_ledger import FIELDS, reconcile, verification_bounds

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from simulator_control import NoRedirect, LocalSessionCookiePolicy

ORIGIN = "http://127.0.0.1:4178"
DEVICE = "delta-rtu-sim-001"
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def iso(ns):
    return (EPOCH + timedelta(microseconds=ns // 1000)).isoformat()


def ns_time(text):
    delta = datetime.fromisoformat(text.replace("Z", "+00:00")) - EPOCH
    return (delta.days * 86400 * 1000000 + delta.seconds * 1000000 + delta.microseconds) * 1000


def expected_samples(directory):
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    return [dict(sampled_ns=e["sampled_ns"], **{k: e["snapshot"][k] for k in FIELDS})
            for e in events if e["kind"] == "committed"]


def db_rows(start, end):
    # Only integers generated from the private test ledger enter fixed SQL.
    sql = ("SELECT COALESCE(json_agg(t),'[]'::json) FROM (SELECT "
           "(extract(epoch FROM time)*1000000000)::bigint AS sampled_ns,"
           "voltage,current,power_kw,energy_kwh FROM electricity_measurements "
           f"WHERE device_id='{DEVICE}' AND time >= '{iso(int(start))}'::timestamptz "
           f"AND time <= '{iso(int(end))}'::timestamptz ORDER BY time) t;")
    result = subprocess.run(
        ["wsl.exe", "-d", "Ubuntu", "--cd", "/home/dalelin/synaiq/EMS", "docker", "exec",
         "ems-timescaledb", "psql", "-U", "postgres", "-d", "ems", "-At", "-c", sql],
        capture_output=True, text=True, check=True, timeout=15)
    return json.loads(result.stdout)


def api_rows(start, end):
    credentials = json.loads((ROOT / ".local/ems-preview-login.json").read_text(encoding="utf-8-sig"))
    jar = http.cookiejar.CookieJar(policy=LocalSessionCookiePolicy(ORIGIN))
    opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPCookieProcessor(jar))
    request = Request(ORIGIN + "/api/auth/login", method="POST",
                      data=json.dumps({k: credentials[k] for k in ("username", "password")}).encode(),
                      headers={"Origin": ORIGIN, "Content-Type": "application/json"})
    with opener.open(request, timeout=15) as response:
        response.read()
    rows = []
    for offset in range(0, 100000, 1000):
        query = urlencode(dict(since=iso(start), until=iso(end + 1000), limit=1000, offset=offset))
        with opener.open(ORIGIN + f"/api/devices/{DEVICE}/records?" + query, timeout=15) as response:
            page = json.load(response)["rows"]
        rows.extend(dict(sampled_ns=ns_time(row["time"]), **{k: row[k] for k in FIELDS}) for row in page)
        if len(page) < 1000:
            return rows
    raise RuntimeError("bench API paging bound exceeded")


def verify(directory, wait_seconds):
    samples = expected_samples(directory)
    if not samples:
        raise ValueError("no committed samples")
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text().splitlines()]
    start, end = verification_bounds(events)
    deadline = time.monotonic() + wait_seconds
    observations = []
    while True:
        database = reconcile(samples, db_rows(start, end))
        observations.append(dict(observed_utc=datetime.now(timezone.utc).isoformat(),
                                 received=database["received"], missing=len(database["missing"])))
        if database["pass"] or time.monotonic() >= deadline:
            break
        time.sleep(min(2, max(0, deadline - time.monotonic())))
    api = reconcile(samples, api_rows(start, end))
    result = dict(database=database, api=api, observations=observations,
                  passed=database["pass"] and api["pass"])
    (directory / "db-comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--wait-seconds", type=int, default=30)
    args = parser.parse_args()
    result = verify(args.directory, args.wait_seconds)
    print(json.dumps(result))
    raise SystemExit(0 if result["passed"] else 1)
