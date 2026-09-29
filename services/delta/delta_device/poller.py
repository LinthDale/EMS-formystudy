"""Local OT only. No Modbus write operation is exposed."""
from pymodbus.client import ModbusSerialClient, ModbusTcpClient
from .protocol import decode, pdu_address


class ReadError(RuntimeError):
    pass


class IllegalAddress(ReadError):
    pass


def make_client(config):
    common = {"timeout": config["timeout"], "retries": 0}
    if config["transport"] == "rtu":
        return ModbusSerialClient(config["serial_port"], baudrate=config["baudrate"],
                                  bytesize=8, parity="N", stopbits=1, **common)
    return ModbusTcpClient(config["host"], port=config["port"], **common)


class Poller:
    def __init__(self, config, client=None):
        self.config = config
        self.client = client if client is not None else make_client(config)

    def read(self, reference, count):
        response = self.client.read_input_registers(
            pdu_address(reference, self.config["address_base"]),
            count=count, slave=self.config["unit_id"])
        if response.isError():
            if getattr(response, "exception_code", None) == 2:
                raise IllegalAddress("unsupported input register")
            raise ReadError("Modbus read failed")
        registers = getattr(response, "registers", [])
        if len(registers) != count:
            raise ReadError("short Modbus response")
        return registers

    def sample(self):
        if not self.client.connect():
            raise ReadError("Modbus connection unavailable")
        try:
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
