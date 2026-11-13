"""KC source adapter isolated to pymodbus 3.12; internal updates remain possible."""
import asyncio
import plc_source as source
from pymodbus.constants import ExcCodes
from pymodbus.datastore import ModbusDeviceContext, ModbusServerContext
from pymodbus.server import StartAsyncTcpServer


class ReadOnlyDevice(ModbusDeviceContext):
    async def async_setValues(self, func_code, address, values):
        # All network write handlers use async_setValues, including FC22 and FC23.
        # The trusted local updater/control adapter uses synchronous setValues.
        return ExcCodes.ILLEGAL_FUNCTION

    async def async_getValues(self, func_code, address, count=1):
        if func_code not in (1, 2, 3, 4):
            return ExcCodes.ILLEGAL_FUNCTION
        return self.getValues(func_code, address, count)


def build():
    original = source.build_datastore()
    store = ReadOnlyDevice(di=original.store["d"], co=original.store["c"],
                           ir=original.store["i"], hr=original.store["h"])
    context = ModbusServerContext(devices={1: store}, single=False)

    def read():
        return dict(motor_speed=store.getValues(3, 4, 1)[0],
                    pump_on=bool(store.getValues(1, 0, 1)[0]),
                    valve_open=bool(store.getValues(1, 1, 1)[0]))

    def apply(changes):
        for key, value in changes.items():
            fc, address = {"motor_speed": (3, 4), "pump_on": (1, 0),
                           "valve_open": (1, 1)}[key]
            store.setValues(fc, address, [value])

    async def run():
        await asyncio.gather(source.update_simulated_data(context),
                             StartAsyncTcpServer(context=context, address=("0.0.0.0", 5020)))
    return "plc-001", read, apply, run
