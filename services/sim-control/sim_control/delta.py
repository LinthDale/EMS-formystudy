"""Docker demo control; standalone TCP/RTU CLI remains unchanged."""
from delta_device.simulator import DeltaRegisters, ReadOnlyContext
from pymodbus.datastore import ModbusServerContext
from pymodbus.server import StartAsyncTcpServer


def build():
    block = DeltaRegisters()
    context = ModbusServerContext(
        slaves={1: ReadOnlyContext(ir=block, zero_mode=True)}, single=False)

    def apply(changes):
        if "scenario" in changes:
            block.set_scenario(changes["scenario"])

    async def run():
        await StartAsyncTcpServer(context=context, address=("0.0.0.0", 5021))
    return "delta-sim-001", lambda: {"scenario": block.scenario}, apply, run
