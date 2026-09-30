"""Read-only TCP/RTU simulator; supports only the phase-1 input register profile."""
from __future__ import annotations

import logging
import math
import os
import random
import re
import time
from pymodbus.datastore import ModbusServerContext, ModbusSlaveContext, ModbusSparseDataBlock
from pymodbus.server import ModbusSerialServer, StartAsyncTcpServer
from .protocol import pdu_address, scales


class DeltaRegisters(ModbusSparseDataBlock):
    def __init__(self, scenario="day", scale_word=1, address_base=1, *, noise=None, seed=20260929):
        self.scenario, self.scale_word, self.address_base = scenario, scale_word, address_base
        if noise is None:
            setting = os.environ.get("DELTA_SIM_NOISE", "0")
            if setting not in ("0", "1"):
                raise ValueError("DELTA_SIM_NOISE must be 0 or 1")
            noise = setting == "1"
        if type(noise) is not bool or type(seed) is not int:
            raise ValueError("noise requires a boolean and an integer seed")
        self.noise, self.seed = noise, seed
        self._sample_key = None
        self.started = time.monotonic()
        self._sampled_at = self.started
        self.segment_started = self.started
        self.accumulated_wh = 0.0
        self.factor = scales(scale_word)
        # The zero-scale sample model is 1000: today defaults to 10 Wh.
        refs = [40962, 53259, *range(49152, 49165), *range(53248, 53257)]
        if scale_word is not None:
            refs.append(40995)
        super().__init__({pdu_address(ref, address_base): 0 for ref in refs})

    def _segment_wh(self, now):
        if self.scenario != "day":
            return 0.0
        a, b = self.segment_started - self.started, now - self.started
        return (9000 * (b - a) + 12000 * (math.cos(a / 20) - math.cos(b / 20))) / 3600

    def set_scenario(self, scenario):
        """Settle the previous interval before changing the generation mode."""
        if scenario not in ("day", "night", "alarm"):
            raise ValueError("unknown scenario")
        now = time.monotonic()
        self.accumulated_wh += self._segment_wh(now)
        self.segment_started, self.scenario = now, scenario
        self._sample_key = None

    def getValues(self, address, count=1):
        now = time.monotonic()
        if self.noise:
            # One frame per second, independent of how many register groups are read.
            key = (int(now - self.started), self.scenario)
            if key != self._sample_key:
                self._sample_key, self._sampled_at = key, now
            now = self._sampled_at
        elapsed = now - self.started
        signal_time = int(elapsed) if self.noise else elapsed
        total_w = 0 if self.scenario != "day" else 9000 + 600 * math.sin(signal_time / 20)
        phases = [(230.0, total_w / 690, total_w / 3)] * 3
        if self.noise:
            rng = random.Random(self.seed + int(elapsed))
            def error(sigma):
                return max(-3 * sigma, min(3 * sigma, rng.gauss(0, sigma)))
            phases = []
            for _ in range(3):
                voltage = 230 + error(1.5)
                current = max(0.0, total_w / 690 + error(.15)) if self.scenario == "day" else 0.0
                phases.append((voltage, current, voltage * current))
            total_w = sum(phase[2] for phase in phases)
        # Piecewise integral: night/alarm neither erase nor backfill generation.
        added_wh = self.accumulated_wh + self._segment_wh(now)
        factor = self.factor
        refs = {40962: 1000, 53259: 35,
                49152: int(total_w / factor.power),
                53256: {"day": 2, "night": 0, "alarm": 4}[self.scenario]}
        if self.scale_word is not None:
            refs[40995] = self.scale_word
        for a, (voltage, current, power) in zip((49153, 49157, 49161), phases):
            refs.update({a: int(voltage / factor.voltage),
                         a + 1: int(current / factor.ac_current),
                         a + 2: int(power / factor.power), a + 3: 6000})
        for a, wh in ((53248, 15000 + added_wh), (53252, 1234560 + added_wh)):
            raw = int(wh / factor.energy)
            refs.update({a: raw & 65535, a + 1: (raw >> 16) & 65535})
        refs.update({53250: int(elapsed) & 65535, 53251: int(elapsed) >> 16,
                     53254: 3600, 53255: 0})
        for ref, value in refs.items():
            if not 0 <= value <= 65535:
                raise ValueError("scenario exceeds selected scale range")
            self.values[pdu_address(ref, self.address_base)] = value
        return super().getValues(address, count)


class ReadOnlyContext(ModbusSlaveContext):
    def validate(self, fc_as_int, address, count=1):
        return fc_as_int == 4 and 1 <= count <= 125 and super().validate(fc_as_int, address, count)


def simulator_context(unit_id: int, scenario: str, scale_word: int | None,
                      address_base: int) -> ModbusServerContext:
    """Build one read-only station shared by both simulator transports."""
    block = DeltaRegisters(scenario, scale_word, address_base)
    # Fail startup for scales that cannot represent the chosen demonstration.
    block.getValues(pdu_address(49152, address_base))
    return ModbusServerContext(
        slaves={unit_id: ReadOnlyContext(ir=block, zero_mode=True)}, single=False)


async def serve(host="127.0.0.1", port=5021, unit_id=1, scenario="day",
                scale_word=1, address_base=1):
    context = simulator_context(unit_id, scenario, scale_word, address_base)
    await StartAsyncTcpServer(context=context, address=(host, port))


class FailFastSerialServer(ModbusSerialServer):
    """pymodbus 3.6.9 otherwise waits forever after an unsuccessful listen."""

    async def listen(self) -> bool:
        if not await super().listen():
            raise OSError("RTU serial listener unavailable")
        logging.info("simulator_ready transport=rtu")
        return True


def local_serial_port(value: str) -> str:
    """Accept local Windows COM or Linux device paths, never serial URLs."""
    if re.fullmatch(r"COM[1-9][0-9]*", value, flags=re.IGNORECASE):
        return value.upper()
    if (value.startswith("/dev/") and "://" not in value
            and ".." not in value.split("/") and "\x00" not in value):
        return value
    raise ValueError("serial port must be COMn or a local /dev/ device")


async def serve_rtu(serial_port: str, baudrate: int = 19200, unit_id: int = 1,
                    scenario: str = "day", scale_word: int | None = 1,
                    address_base: int = 1) -> None:
    """Serve one local serial station until cancelled, releasing its port."""
    port = local_serial_port(serial_port)
    if baudrate not in (9600, 19200, 38400) or not 1 <= unit_id <= 247:
        raise ValueError("unsupported RTU baudrate or unit ID")
    context = simulator_context(unit_id, scenario, scale_word, address_base)
    server = FailFastSerialServer(
        context=context, port=port, baudrate=baudrate, bytesize=8,
        parity="N", stopbits=1, ignore_missing_slaves=True,
        broadcast_enable=False,
    )
    try:
        await server.serve_forever()
    finally:
        await server.shutdown()
