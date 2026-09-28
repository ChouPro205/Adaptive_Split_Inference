"""One-command CDC direction probe with the NCS toolchain's pyserial."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import serial


def stamp() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--command", default="BAD")
    parser.add_argument("--rts", action="store_true")
    parser.add_argument("--log", type=Path, default=Path("device/artifacts/week3_capture_pyserial_diag.txt"))
    args = parser.parse_args()
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("w", encoding="ascii") as log:
        def record(message: str) -> None:
            line = f"{stamp()} {message}"
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()

        port = serial.Serial(port=None, baudrate=115200, timeout=5, write_timeout=10,
                             rtscts=False, dsrdtr=False)
        port.dtr = True
        port.rts = args.rts
        port.port = args.port
        try:
            record(f"OPEN {args.port} dtr={port.dtr} rts={port.rts}")
            port.open()
            record(f"OPENED is_open={port.is_open}")
            for _ in range(10):
                line = port.readline().decode("ascii", errors="replace").strip()
                record(f"RX {line!r}")
                if line.startswith("READY WEEK3 "):
                    break
            else:
                raise RuntimeError("READY not received")
            line = port.readline().decode("ascii", errors="replace").strip()
            record(f"RX {line!r}")
            payload = (args.command + "\n").encode("ascii")
            record(f"PRE_WRITE payload={payload!r} waiting={port.in_waiting}")
            count = port.write(payload)
            record(f"WRITE_OK count={count}")
            for _ in range(10):
                line = port.readline().decode("ascii", errors="replace").strip()
                record(f"RX {line!r}")
                if line.startswith("ERROR ") or line.startswith("BEGIN "):
                    break
        except Exception as exc:
            record(f"EXCEPTION {type(exc).__name__}: {exc}")
            raise
        finally:
            if port.is_open:
                port.close()


if __name__ == "__main__":
    main()
