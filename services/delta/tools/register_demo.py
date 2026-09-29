"""Run inside device-service with its existing OPS_API_KEY, before edge startup.

Idempotent only for the exact Delta demo identity; refuse unrelated existing rows.
Does not print keys or create any AI classification request.
"""
import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE = "http://127.0.0.1:8002"
DEVICE = {
    "device_id": "delta-sim-001", "device_type": "electricity",
    "protocol": "modbus_tcp", "vendor": "Delta (SIMULATOR)",
    "model": "Three-phase V1.35 simulator",
    "location": "模擬設備 | V/A=L1；kW=三相總功率；kWh=累計發電",
    "gateway_id": "ems-gateway",
}


def request(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = Request(BASE + path, data=data, method=method,
                  headers={"Content-Type": "application/json",
                           "X-API-Key": os.environ["OPS_API_KEY"]})
    with urlopen(req, timeout=10) as response:
        return json.load(response)


def main():
    path = "/devices/" + DEVICE["device_id"]
    try:
        current = request("GET", path)
    except HTTPError as exc:
        if exc.code != 404:
            raise
        current = request("POST", "/devices", DEVICE)
    if any(current.get(key) != value for key, value in DEVICE.items()):
        raise RuntimeError("existing device differs; inspect identity before proceeding")
    signals = request("GET", path + "/signals")
    existing = {s["signal_name"] for s in signals}
    for name, unit, source in (
        ("voltage","V","Delta IR49153: L1 phase voltage"),
        ("current","A","Delta IR49154: L1 current"),
        ("power_kw","kW","Delta IR49152: three-phase total active power"),
        ("energy_kwh","kWh","Delta IR53252/53253: lifetime energy, low word first"),
    ):
        if name not in existing:
            request("POST", path + "/signals",
                    {"signal_name":name,"unit":unit,"datatype":"float",
                     "direction":"read","source_ref":source})
    if current["status"] == "candidate":
        current = request("POST", path + "/confirm")
    if current["status"] != "confirmed":
        raise RuntimeError("demo device is not confirmed")
    print("delta-sim-001 registered and confirmed; four signal semantics recorded")


if __name__ == "__main__":
    main()
