#!/usr/bin/env python3
"""Capture a PPK2 trace with ppk2-api (Source Meter) into a NEW directory (week 7 onward).

DEVICE STEP. The capture thread only copies the serial byte stream to raw.bin (4-byte words,
100 kS/s); conversion to current and logic bits happens offline in energy_phases.py with the
exact ppk2-api 0.9.2 arithmetic, so no CPU-heavy work competes with the USB reads (risk R1).

Sequence (TC2): open port -> GET_META_DATA right away (calibration modifiers, kept verbatim) ->
DUT power OFF -> Source Meter -> set voltage -> start measuring -> DUT power ON after
--pre-power-s (the boot is recorded) -> run --seconds -> DUT power OFF -> stop -> drain.
Outputs: raw.bin, capture.json (metadata, modifiers, byte offset of DUT ON, host read stats,
SHA-256 of raw.bin and of the tools). Refuses to reuse an existing directory.

  python measure_energy.py list
  python measure_energy.py probe            (first thing at the bench: which port, 100 kS/s, counter)
  python measure_energy.py capture --port COM9 --voltage-mV 5000 --seconds 70 --out D:\\HUST\\ASI_week7\\session-...\\idle-w2 --label idle-week2 --temp-c 27.5
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

SAMPLE_RATE_HZ = 100_000
BYTES_PER_SAMPLE = 4
SCHEMA = "week7-ppk2-capture/1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class Reader(threading.Thread):
    """Copies every byte the PPK2 sends to an open binary file; no parsing."""

    def __init__(self, ser, sink, poll_s: float = 0.0005):
        super().__init__(daemon=True)
        self.ser, self.sink, self.poll_s = ser, sink, poll_s
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.bytes_written = 0
        self.reads = 0
        self.max_chunk = 0
        self.max_gap_s = 0.0
        self.error = None

    def run(self):
        last = time.perf_counter()
        try:
            while not self.stop_event.is_set():
                waiting = self.ser.in_waiting
                if waiting:
                    data = self.ser.read(waiting)
                    now = time.perf_counter()
                    self.sink.write(data)
                    with self.lock:
                        self.bytes_written += len(data)
                        self.reads += 1
                        self.max_chunk = max(self.max_chunk, len(data))
                        self.max_gap_s = max(self.max_gap_s, now - last)
                    last = now
                else:
                    time.sleep(self.poll_s)
        except Exception as error:  # reported in capture.json, capture marked FAIL
            self.error = repr(error)

    def position(self) -> int:
        with self.lock:
            return self.bytes_written


def drain_stale_stream(ppk2, settle_s: float = 0.3) -> int:
    """A PPK2 left measuring by an aborted run keeps streaming binary words; the metadata
    reader of ppk2-api would then fail to decode them. Stop and drop them (0 = nothing stale)."""
    time.sleep(0.05)
    stale = ppk2.ser.in_waiting
    if stale:
        ppk2.stop_measuring()
        time.sleep(settle_s)
        stale += ppk2.ser.in_waiting
        ppk2.ser.reset_input_buffer()
    return stale


def read_metadata(ppk2, attempts: int = 3) -> str:
    """GET_META_DATA and keep the text; same parser as PPK2_API.get_modifiers()."""
    for _ in range(attempts):
        ppk2._write_serial((0x19,))           # PPK2_Command.GET_META_DATA
        try:
            text = ppk2._read_metadata()
        except UnicodeDecodeError:            # measurement words mixed in: drop, ask again
            text = None
            ppk2.ser.reset_input_buffer()
        if text and ppk2._parse_metadata(text):
            return text
        time.sleep(0.2)
    raise RuntimeError("PPK2 metadata (calibration) not received: wrong port or PPK2 busy")


def open_ppk2(port: str):
    import ppk2_api.ppk2_api as api
    ppk2 = api.PPK2_API(port, timeout=0.05, write_timeout=1.0)
    try:
        ppk2.ser.set_buffer_size(rx_size=1 << 20)   # Windows only; 1 MiB = 2.6 s of samples
    except (AttributeError, ValueError, OSError):
        pass
    return ppk2, api


def capture(port: str, voltage_mv: int, seconds: float, out: Path, label: str,
            temp_c: float | None, note: str, pre_power_s: float = 0.5,
            post_off_s: float = 0.2, opener=open_ppk2, clock=time.monotonic) -> dict:
    out = Path(out)
    if out.exists():
        raise SystemExit(f"refusing to reuse existing output {out}")
    if not 800 <= voltage_mv <= 5000:
        raise SystemExit("voltage must be 800..5000 mV")
    out.mkdir(parents=True)
    ppk2, api = opener(port)
    stale_bytes = drain_stale_stream(ppk2)
    meta_text = read_metadata(ppk2)
    ppk2.toggle_DUT_power("OFF")
    ppk2.use_source_meter()
    ppk2.set_source_voltage(voltage_mv)
    time.sleep(0.2)
    ppk2.ser.reset_input_buffer()
    raw_path = out / "raw.bin"
    started = utc_now()
    with open(raw_path, "xb") as sink:
        reader = Reader(ppk2.ser, sink)
        ppk2.start_measuring()
        t0 = clock()
        reader.start()
        time.sleep(pre_power_s)
        dut_on_byte = reader.position()
        ppk2.toggle_DUT_power("ON")
        t_on = clock()
        while clock() - t_on < seconds and reader.is_alive():
            time.sleep(0.05)
        ppk2.toggle_DUT_power("OFF")
        t_off = clock()
        dut_off_byte = reader.position()
        time.sleep(post_off_s)
        ppk2.stop_measuring()
        time.sleep(0.2)
        reader.stop_event.set()
        reader.join(timeout=5.0)
        t_end = clock()
    finished = utc_now()
    try:
        ppk2.ser.close()
    except Exception:
        pass
    total = raw_path.stat().st_size
    samples = total // BYTES_PER_SAMPLE
    wall_s = t_end - t0
    here = Path(__file__).resolve().parent
    tools = {name: sha256_file(here / name) for name in ("measure_energy.py", "energy_phases.py")
             if (here / name).exists()}
    tools["ppk2_api.py"] = sha256_file(Path(api.__file__))
    expected = (dut_off_byte - dut_on_byte) / BYTES_PER_SAMPLE
    meta = {
        "schema": SCHEMA,
        "label": label,
        "note": note,
        "port": port,
        "started_utc": started,
        "finished_utc": finished,
        "seconds_requested": seconds,
        "pre_power_s": pre_power_s,
        "v_supply_mV": voltage_mv,
        "mode": "SOURCE_METER",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "raw_file": raw_path.name,
        "raw_bytes": total,
        "raw_sha256": sha256_file(raw_path),
        "samples": samples,
        "trailing_bytes": total % BYTES_PER_SAMPLE,
        "dut_power_on_byte": dut_on_byte,
        "dut_power_off_byte": dut_off_byte,
        "host_wall_s": wall_s,
        "samples_per_host_second": samples / wall_s if wall_s > 0 else None,
        "dut_on_host_s": t_off - t_on,
        "dut_on_samples": expected,
        "dut_on_samples_expected": (t_off - t_on) * SAMPLE_RATE_HZ,
        "host_reads": reader.reads,
        "host_max_read_bytes": reader.max_chunk,
        "host_max_gap_between_reads_s": reader.max_gap_s,
        "reader_error": reader.error,
        "stale_bytes_dropped_at_open": stale_bytes,
        "metadata_text": meta_text,
        "modifiers": {k: v for k, v in ppk2.modifiers.items() if isinstance(v, dict)},
        "modifiers_scalar": {k: v for k, v in ppk2.modifiers.items() if not isinstance(v, dict)},
        "temp_room_C": temp_c,
        "ppk2_api_version": package_version("ppk2-api"),
        "python": sys.version,
        "platform": platform.platform(),
        "tools_sha256": tools,
    }
    rate_dev = abs(expected - meta["dut_on_samples_expected"]) / meta["dut_on_samples_expected"] * 100
    meta["dut_on_rate_deviation_pct"] = rate_dev
    import energy_phases as ep   # informational here; the analysis re-checks it from raw.bin
    words = np.fromfile(raw_path, dtype="<u4", count=samples)
    meta["counter"] = ep.counter_check(((words >> ep.COUNTER_SHIFT) & ep.COUNTER_MASK).astype(np.uint8))
    del words
    meta["status"] = "PASS" if reader.error is None and total % BYTES_PER_SAMPLE == 0 and \
        rate_dev <= 0.1 else "CHECK"
    (out / "capture.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def package_version(name: str):
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:
        return None


def cmd_list(_args) -> int:
    import serial.tools.list_ports
    for port in serial.tools.list_ports.comports():
        print(f"{port.device}\t{port.vid and hex(port.vid)}:{port.pid and hex(port.pid)}\t"
              f"{port.description}\t{port.serial_number}")
    print("PPK2 = 'nRF Connect USB CDC ACM' (VID 0x1915, PID 0xc00a); use the data port that answers "
          "GET_META_DATA (capture fails fast on the wrong one).")
    return 0


def ppk2_ports() -> list:
    import serial.tools.list_ports
    return [p.device for p in serial.tools.list_ports.comports()
            if p.vid == 0x1915 and p.pid == 0xC00A]


def probe(port: str, stream_s: float, opener=open_ppk2) -> dict:
    """Metadata + a short stream with DUT power OFF: answers, sample rate, counter continuity.
    Nothing is written to disk and the DUT is never powered."""
    import energy_phases as ep
    ppk2, _ = opener(port)
    try:
        stale = drain_stale_stream(ppk2)
        text = read_metadata(ppk2)
        ppk2.toggle_DUT_power("OFF")
        ppk2.use_source_meter()
        ppk2.set_source_voltage(5000)
        time.sleep(0.2)
        ppk2.ser.reset_input_buffer()
        chunks = []
        ppk2.start_measuring()
        t0 = time.monotonic()
        while time.monotonic() - t0 < stream_s:
            waiting = ppk2.ser.in_waiting
            chunks.append(ppk2.ser.read(waiting) if waiting else b"")
            time.sleep(0.001)
        ppk2.stop_measuring()
        wall = time.monotonic() - t0
        time.sleep(0.2)
        ppk2.ser.reset_input_buffer()
    finally:
        try:
            ppk2.ser.close()
        except Exception:
            pass
    data = b"".join(chunks)
    words = np.frombuffer(data[:len(data) - len(data) % 4], dtype="<u4")
    modifiers = ep.default_modifiers()
    for key, table in ppk2.modifiers.items():
        if key in modifiers and isinstance(table, dict):
            modifiers[key].update({k: float(v) for k, v in table.items()})
    _, bits, ranges, counter = ep.convert_words(words, modifiers, 5000.0, spike_filter=False)
    scalar = {k: v for k, v in ppk2.modifiers.items() if not isinstance(v, dict)}
    return {"port": port, "stale_bytes_dropped": stale, "metadata_ok": bool(text),
            "calibration": scalar, "R": ppk2.modifiers.get("R"),
            "stream_s": wall, "samples": int(words.size),
            "samples_per_s": words.size / wall if wall > 0 else None,
            "trailing_bytes": len(data) % 4, "counter": ep.counter_check(counter),
            "range_counts": np.bincount(ranges, minlength=5).tolist(),
            "logic_high_samples": {f"D{c}": int(np.count_nonzero((bits >> c) & 1)) for c in range(8)}}


def cmd_probe(args) -> int:
    ports = [args.port] if args.port else ppk2_ports()
    if not ports:
        print("no PPK2 port (VID 0x1915 PID 0xC00A); check the USB cable / nRF Connect closed")
        return 1
    result = 1
    for port in ports:
        try:
            info = probe(port, args.stream_s)
        except Exception as error:  # noqa: BLE001 - try the next candidate port
            print(f"{port}: no PPK2 answer ({error!r})")
            continue
        print(json.dumps(info, indent=2))
        counter = info["counter"]
        print(f"PROBE {port}: {info['samples_per_s']:.0f} samples/s, counter "
              f"{'continuous' if counter['available'] and counter['discontinuities'] == 0 else counter}")
        result = 0
    return result


def cmd_capture(args) -> int:
    meta = capture(args.port, args.voltage_mV, args.seconds, args.out, args.label, args.temp_c,
                   args.note, args.pre_power_s)
    print(f"samples {meta['samples']} ({meta['raw_bytes']} B), DUT-on samples {meta['dut_on_samples']:.0f} "
          f"vs {meta['dut_on_samples_expected']:.0f} expected ({meta['dut_on_rate_deviation_pct']:.3f} %), "
          f"max read gap {meta['host_max_gap_between_reads_s'] * 1e3:.1f} ms, reader_error={meta['reader_error']}")
    print(f"sample counter (bits 18-23): {meta['counter']}")
    print(f"CAPTURE {meta['status']} -> {args.out}  (next: energy_phases.py markers --raw ... --counter)")
    return 0 if meta["status"] == "PASS" else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="serial ports").set_defaults(func=cmd_list)
    p = sub.add_parser("probe", help="PPK2 answers? metadata + short stream, DUT power stays OFF")
    p.add_argument("--port", help="default: every port with VID 0x1915 PID 0xC00A")
    p.add_argument("--stream-s", type=float, default=2.0)
    p.set_defaults(func=cmd_probe)
    p = sub.add_parser("capture", help="record a new trace")
    p.add_argument("--port", required=True)
    p.add_argument("--voltage-mV", dest="voltage_mV", type=int, default=5000)
    p.add_argument("--seconds", type=float, required=True, help="time with DUT power ON")
    p.add_argument("--pre-power-s", type=float, default=0.5)
    p.add_argument("--out", type=Path, required=True, help="new directory")
    p.add_argument("--label", default="")
    p.add_argument("--temp-c", type=float, help="room temperature (temp_room_C)")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_capture)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
