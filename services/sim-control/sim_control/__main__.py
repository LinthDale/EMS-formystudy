"""One simulator and one internal agent share a single event-loop thread."""
import asyncio
import contextlib
import importlib
import os
from contextlib import asynccontextmanager
import uvicorn
from .agent import ControlAgent, make_app


def main():
    kind = os.environ["SIMULATOR_KIND"]
    if kind not in ("meter", "plc", "sensor", "delta"):
        raise ValueError("unknown simulator kind")
    simulator_id, read, apply, run = importlib.import_module("." + kind, __package__).build()
    agent = ControlAgent(simulator_id, read, apply, os.getenv("SIM_CONTROL_TOKEN", ""))

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(run())
        # Fatal telemetry task failure must not leave a healthy-looking control-only service.
        def failed(done):
            if not done.cancelled():
                os._exit(1)
        task.add_done_callback(failed)
        try:
            yield
        finally:
            task.remove_done_callback(failed)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
    uvicorn.run(make_app(agent, lifespan), host="0.0.0.0", port=9000, access_log=False)


if __name__ == "__main__":
    main()
