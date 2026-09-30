"""Meter adapter, pymodbus 3.6.9; network writes blocked in source context."""
import asyncio
from dataclasses import asdict
import meter_source as source
from pymodbus.server import StartAsyncTcpServer


def build():
    def apply(changes):
        for name, value in changes.items():
            setattr(source.config, name, value)

    async def run():
        await asyncio.gather(
            source._simulation_loop(),
            StartAsyncTcpServer(context=source._context, address=("0.0.0.0", 5020)),
        )
    return "sim-001", lambda: asdict(source.config), apply, run
