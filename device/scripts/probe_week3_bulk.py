"""Bounded raw CDC read probe for one Week 3 command."""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

import serial


def log(message: str) -> None:
    print(f"{datetime.now().astimezone().isoformat(timespec='milliseconds')} {message}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--command", default="RUN 10")
    parser.add_argument("--output", type=Path, default=Path("device/artifacts/week3_capture_probe_bulk.txt"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    port = serial.Serial(port=None, baudrate=115200, timeout=0.5, write_timeout=10)
    port.dtr = True
    port.port = args.port
    try:
        port.open()
        log(f"OPEN {args.port} dtr={port.dtr}")
        with args.output.open("wb") as output:
            deadline = time.monotonic() + 10
            banner = bytearray()
            while b"READY WEEK3 " not in banner and time.monotonic() < deadline:
                banner.extend(port.read(4096))
            if b"READY WEEK3 " not in banner:
                raise RuntimeError(f"READY absent, received {len(banner)} bytes")
            output.write(banner)
            payload = (args.command + "\n").encode("ascii")
            log(f"WRITE {payload!r}")
            port.write(payload)
            log("WRITE_OK")
            received = bytearray()
            last_byte = time.monotonic()
            terminal = f"DONE {args.command.split()[-1]}".encode("ascii")
            while time.monotonic() - last_byte < 5:
                chunk = port.read(4096)
                if chunk:
                    output.write(chunk)
                    received.extend(chunk)
                    last_byte = time.monotonic()
                    if terminal in received:
                        break
            output.flush()
            log(f"RESULT bytes={len(received)} done={terminal in received} output={args.output}")
            if terminal not in received:
                raise RuntimeError("No DONE within 5 seconds of last received byte")
    finally:
        port.close()


if __name__ == "__main__":
    main()
