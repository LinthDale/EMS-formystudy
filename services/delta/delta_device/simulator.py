"""Read-only TCP/RTU simulator; supports only the phase-1 input register profile."""
from __future__ import annotations

import logging
import math
import re
import time
from pymodbus.datastore import ModbusServerContext, ModbusSlaveContext, ModbusSparseDataBlock
from pymodbus.server import ModbusSerialServer, StartAsyncTcpServer
from .protocol import pdu_address, scales


class DeltaRegisters(ModbusSparseDataBlock):
    def __init__(self, scenario="day", scale_word=1, address_base=1):
        self.scenario, self.scale_word, self.address_base = scenario, scale_word, address_base
        self.started = time.monotonic()
        self.factor = scales(scale_word)
        # The zero-scale sample model is 1000: today defaults to 10 Wh.
        refs = [40962, 53259, *range(49152, 49165), *range(53248, 53257)]
        if scale_word is not None:
            refs.append(40995)
        super().__init__({pdu_address(ref, address_base): 0 for ref in refs})

    def getValues(self, address, count=1):
        elapsed = time.monotonic() - self.started
        total_w = 0 if self.scenario != "day" else 9000 + 600 * math.sin(elapsed / 20)
        # Exact integral of the above sine; energy remains monotonic.
        added_wh = (9000 * elapsed + 12000 * (1 - math.cos(elapsed / 20))) / 3600
        if self.scenario != "day":
            added_wh = 0
        factor = self.factor
        refs = {40962: 1000, 53259: 35,
                49152: int(total_w / factor.power),
                53256: {"day": 2, "night": 0, "alarm": 4}[self.scenario]}
        if self.scale_word is not None:
            refs[40995] = self.scale_word
        for a in (49153, 49157, 49161):
            refs.update({a: int(230 / factor.voltage),
                         a + 1: int(total_w / 3 / 230 / factor.ac_current),
                         a + 2: int(total_w / 3 / factor.power), a + 3: 6000})
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
