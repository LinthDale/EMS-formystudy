"""Local OT only. No Modbus write operation is exposed."""
from sys import platform
from time import monotonic

from pymodbus.client import ModbusSerialClient, ModbusTcpClient
from pymodbus.pdu import ExceptionResponse
from .config import response_lifetime
from .protocol import decode, pdu_address


class ReadError(RuntimeError):
    pass


class IllegalAddress(ReadError):
    pass


class SynchronizationUncertain(ReadError):
    pass


class RecoveryPending(ReadError):
    pass


def make_client(config):
    common = {"timeout": config["timeout"], "retries": 0}
    if config["transport"] == "rtu":
        # Windows USB delivery gaps exceed RTU character timing: pyserial's
        # interval timeout can return a partial read. Keep the overall timeout
        # and pymodbus length/unit/CRC checks; retain strict timing on Linux.
        return ModbusSerialClient(config["serial_port"], baudrate=config["baudrate"],
                                  bytesize=8, parity="N", stopbits=1,
                                  strict=platform != "win32", **common)
    return ModbusTcpClient(config["host"], port=config["port"], **common)


class Poller:
    def __init__(self, config, client=None, *, mode='demo'):
        self.config = dict(config)
        self._rtu = config['transport'] == 'rtu'
        self._lifetime = response_lifetime(config)
        if mode not in ('demo', 'field'):
            raise ValueError('explicit poller mode required')
        if mode == 'field' and self._rtu and self._lifetime is None:
            raise ValueError('field RTU requires a qualified response lifetime')
        self._uncertain_since = monotonic() if mode == 'field' and self._rtu else None
        self.client = client if client is not None else make_client(config)

    @property
    def recovery_remaining(self):
        if self._uncertain_since is None:
            return 0.0
        if self._lifetime is None:
            return None
        return max(0.0, self._uncertain_since + self._lifetime - monotonic())

    def _poison(self):
        if self._rtu:
            if self._uncertain_since is None:
                self._uncertain_since = monotonic()
            self.client.close()

    def _ensure_ready(self):
        if self._uncertain_since is None:
            return
        remaining = self.recovery_remaining
        if remaining is None:
            raise SynchronizationUncertain('RTU response lifetime is unqualified')
        if remaining > 0:
            raise RecoveryPending('RTU response lifetime guard is active')
        self.client.close()
        self.client = make_client(self.config)
        try:
            if not self.client.connect():
                raise ReadError('RTU recovery port unavailable')
            self.client.socket.reset_input_buffer()
            self.client.framer.resetFrame()
        except Exception:
            self.client.close()
            raise
        self._uncertain_since = None

    def read(self, reference, count):
        self._ensure_ready()
        address = pdu_address(reference, self.config['address_base'])
        try:
            response = self.client.read_input_registers(
                address, count=count, slave=self.config['unit_id'])
        except Exception:
            self._poison()
            raise
        if response.isError():
            completed_exception = isinstance(response, ExceptionResponse)
            if completed_exception and response.function_code == 0x84 and response.exception_code == 2:
                raise IllegalAddress("unsupported input register")
            if not completed_exception or response.function_code != 0x84:
                self._poison()
            raise ReadError("Modbus read failed")
        registers = getattr(response, "registers", [])
        if getattr(response, 'function_code', 4) != 4 or len(registers) != count:
            self._poison()
            raise ReadError("short Modbus response")
        return registers

    def sample(self):
        self._ensure_ready()
        try:
            if not self.client.connect():
                raise ReadError("Modbus connection unavailable")
            try:
                scale_word = self.read(40995, 1)[0]
            except IllegalAddress:
                scale_word = None
            model = self.read(40962, 1)[0] if scale_word == 0 else None
            registers = {}
            for address, count in ((49152, 13), (53248, 9)):
                registers.update(enumerate(self.read(address, count), address))
            if self.config.get("read_temperature", False):
                try:
                    registers[53259] = self.read(53259, 1)[0]
                except IllegalAddress:
                    pass  # Optional signal absent; never invent a temperature.
            return decode(registers, scale_word, model)
        finally:
            self.client.close()
