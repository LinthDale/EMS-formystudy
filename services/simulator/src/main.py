"""EMS Simulator — a Level 2 Modbus TCP slave that pretends to be a real meter.

Runs two things in one process:
- Modbus TCP slave on port 5020  (gateway-telegraf reads from here)
- FastAPI REST on port 8000      (humans tweak simulation parameters here)

Register map (holding registers):
    [0]    voltage    INT16,   scale 0.1   (volts)
    [1]    current    INT16,   scale 0.1   (amps)
    [2,3]  power_kw   FLOAT32, byte order ABCD
    [4,5]  energy_kwh FLOAT32, byte order ABCD  (cumulative)
"""
from __future__ import annotations

import asyncio
import math
import os
import random
import struct
from contextlib import asynccontextmanager
from dataclasses import dataclass

import uvicorn
from fastapi import FastAPI
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.server import StartAsyncTcpServer


# ---------- Modbus data store (shared with simulation loop) ----------
# Using pymodbus 3.6.x classic API (pinned in requirements.txt).
# pymodbus 3.13 rewrote this with SimData/SimDevice — avoided for MVP.

_store = ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, [0] * 100))
_context = ModbusServerContext(slaves={1: _store}, single=False)


def _float_to_registers(value: float, byte_order: str = "ABCD") -> list[int]:
    """Pack a 32-bit float into two 16-bit Modbus registers."""
    be = struct.pack(">f", value)  # 4 bytes, big-endian (AB CD)
    if byte_order == "ABCD":
        buf = be
    elif byte_order == "CDAB":
        buf = be[2:4] + be[0:2]
    elif byte_order == "BADC":
        buf = bytes([be[1], be[0], be[3], be[2]])
    elif byte_order == "DCBA":
        buf = be[::-1]
    else:
        raise ValueError(f"Unknown byte order: {byte_order}")
    return [
        int.from_bytes(buf[0:2], "big"),
        int.from_bytes(buf[2:4], "big"),
    ]


# ---------- Simulation parameters (mutable via REST) ----------

@dataclass
class SimConfig:
    # Voltage measurement (line voltage V_LL, 3-phase 380V system)
    noise_voltage_v: float = 3.0       # V_LL stddev — PT measurement noise
    # Current measurement (CT secondary, represents main feeder current)
    current_base_a: float = 100.0      # A — midpoint of production cycle
    current_swing_a: float = 40.0      # A — amplitude (60~140 A range)
    noise_current_a: float = 2.0       # A stddev — CT measurement noise
    power_factor: float = 0.85         # cos φ — typical industrial inductive load
    period_seconds: float = 3600.0     # one full production cycle (1 hr)
    fault_mode: str = "none"           # none | zero | freeze


config = SimConfig()


# ---------- Simulation loop ----------

async def _simulation_loop() -> None:
    """Tick once per second, update register values to look like a real meter."""
    t = 0
    energy_kwh = 0.0

    while True:
        if config.fault_mode == "freeze":
            await asyncio.sleep(1)
            t += 1
            continue

        if config.fault_mode == "zero":
            voltage = 0.0
            current = 0.0
            power_kw = 0.0
        else:
            # V and I are independently MEASURED; power is DERIVED from them.
            # Line voltage (V_LL): what 3-phase meters show (380 V system)
            voltage = 380.0 + random.gauss(0, config.noise_voltage_v)
            # Current: sine wave simulating a production shift load cycle
            current = (
                config.current_base_a
                + config.current_swing_a
                * math.sin(t / config.period_seconds * 2 * math.pi)
                + random.gauss(0, config.noise_current_a)
            )
            current = max(0.0, current)
            # Three-phase: P = √3 × V_LL × I × cos(φ)
            power_kw = math.sqrt(3) * voltage * current * config.power_factor / 1000.0

        # Cumulative energy: integrate power over 1 second (hr = s/3600)
        energy_kwh += max(power_kw, 0.0) / 3600.0

        # Write registers
        # Holding registers are function code 3
        _store.setValues(
            3, 0,
            [int(round(voltage * 10)), int(round(current * 10))],
        )
        _store.setValues(3, 2, _float_to_registers(power_kw, "ABCD"))
        _store.setValues(3, 4, _float_to_registers(energy_kwh, "ABCD"))

        await asyncio.sleep(1)
        t += 1


# ---------- FastAPI app + lifespan to start Modbus + sim concurrently ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    sim_task = asyncio.create_task(_simulation_loop())
    modbus_task = asyncio.create_task(
        StartAsyncTcpServer(context=_context, address=("0.0.0.0", 5020))
    )
    try:
        yield
    finally:
        sim_task.cancel()
        modbus_task.cancel()


app = FastAPI(title="EMS Simulator", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/config")
def get_config() -> dict:
    return {
        "noise_voltage_v": config.noise_voltage_v,
        "current_base_a": config.current_base_a,
        "current_swing_a": config.current_swing_a,
        "noise_current_a": config.noise_current_a,
        "power_factor": config.power_factor,
        "period_seconds": config.period_seconds,
        "fault_mode": config.fault_mode,
    }


@app.post("/config")
def set_config(
    noise_voltage_v: float | None = None,
    current_base_a: float | None = None,
    current_swing_a: float | None = None,
    noise_current_a: float | None = None,
    power_factor: float | None = None,
    period_seconds: float | None = None,
) -> dict:
    for key, value in {
        "noise_voltage_v": noise_voltage_v,
        "current_base_a": current_base_a,
        "current_swing_a": current_swing_a,
        "noise_current_a": noise_current_a,
        "power_factor": power_factor,
        "period_seconds": period_seconds,
    }.items():
        if value is not None:
            setattr(config, key, value)
    return get_config()


@app.post("/inject-fault")
def inject_fault(mode: str = "none") -> dict:
    """Set fault_mode to one of: none | zero | freeze."""
    valid = {"none", "zero", "freeze"}
    if mode not in valid:
        return {"error": f"mode must be one of: {sorted(valid)}"}
    config.fault_mode = mode
    return {"fault_mode": mode}


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        log_level="info",
    )
