import argparse
import asyncio
import json
import logging
import os
from .config import load_config
from .edge import run
from .poller import Poller
from .simulator import local_serial_port, serve, serve_rtu


def serial_argument(value: str) -> str:
    """Report local serial port validation failures as CLI usage errors."""
    try:
        return local_serial_port(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def main():
    os.umask(0o077)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Delta V1.35 read-only telemetry")
    sub = parser.add_subparsers(dest="command", required=True)
    sim = sub.add_parser("simulator")
    sim.add_argument("--transport", choices=("tcp", "rtu"), default="tcp")
    sim.add_argument("--host", help="TCP only; default 127.0.0.1")
    sim.add_argument("--port", type=int, help="TCP only; default 5021")
    sim.add_argument("--serial-port", type=serial_argument, help="RTU only: COM5 or /dev/ttyUSB0")
    sim.add_argument("--baudrate", type=int, choices=(9600, 19200, 38400),
                     help="RTU only; default 19200 (8N1)")
    sim.add_argument("--unit-id", type=int, default=1, choices=range(1, 248))
    sim.add_argument("--scenario", choices=("day", "night", "alarm"), default="day")
    sim.add_argument("--scale", default="1", help="integer/hex, or absent")
    sim.add_argument("--address-base", type=int, choices=(0, 1), default=1)
    edge = sub.add_parser("edge")
    edge.add_argument("--config", required=True)
    edge.add_argument("--once", action="store_true", help="Read and print; do not publish")
    args = parser.parse_args()
    try:
        if args.command == "simulator":
            word = None if args.scale == "absent" else int(args.scale, 0)
            if args.transport == "rtu":
                if args.serial_port is None:
                    parser.error("--transport rtu requires --serial-port")
                if args.host is not None or args.port is not None:
                    parser.error("--host/--port apply only to TCP")
                asyncio.run(serve_rtu(args.serial_port, args.baudrate or 19200,
                                      args.unit_id, args.scenario, word, args.address_base))
            else:
                if args.serial_port is not None or args.baudrate is not None:
                    parser.error("--serial-port/--baudrate require --transport rtu")
                asyncio.run(serve(args.host if args.host is not None else "127.0.0.1",
                                  args.port if args.port is not None else 5021,
                                  args.unit_id, args.scenario, word, args.address_base))
        else:
            config = load_config(args.config)
            if args.once:
                print(json.dumps(Poller(config["modbus"]).sample(), indent=2))
            else:
                run(config)
    except (ValueError, OSError) as exc:
        # Sanitize configuration errors: file paths may reference secret material.
        logging.error("startup_failed kind=%s", type(exc).__name__)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        logging.info("stopped")


if __name__ == "__main__":
    main()
