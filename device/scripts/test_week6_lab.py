#!/usr/bin/env python3
"""Smoke tests of week6_lab.py wiring without hardware: a fake CDC answers like the firmware
and a fake peer becomes ready at once. Catches asyncio/threading mistakes in drive_run() and
the Cdc wait/send bookkeeping. Run: device/host/.venv/Scripts/python.exe -B device/scripts/test_week6_lab.py
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import week6_lab as lab  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="week6_lab_"))


class FakeCdc(lab.Cdc):
    """Answers commands from a background thread, like the device over USB CDC."""

    def __init__(self, path: Path, refuse_first_run: bool = False):
        super().__init__(None, path)
        self.refuse_first_run = refuse_first_run
        self.sent = []

    def send(self, command: str, log_as=None) -> int:
        with self.cond:
            mark = len(self.lines)
        self.note(f"SEND {log_as or command}")
        self.sent.append(command)
        threading.Thread(target=self.answer, args=(command,), daemon=True).start()
        return mark + 1

    def answer(self, command: str) -> None:
        time.sleep(0.05)
        if command.startswith("MODE"):
            self._append(f"MODE {command.split()[1]}")
        elif command == "I2 ARM":
            self._append("I2 ARM=1 status=READY")
        elif command.startswith("RUN"):
            if self.refuse_first_run:
                self.refuse_first_run = False
                self._append("ERROR link not ready (connect the central and enable notifications)")
                return
            self._append("RUN BEGIN run=1 count=2 pattern=MIX mode=ECHO build=b variant=default att_mtu=247")
            time.sleep(0.2)
            self._append("RUN END run=1 requested=2 aborted=0 reason= att_mtu=247")
            self._append("COUNTERS planned=2 completed=2")
            self._append("REASM malformed_fragment=0")


class FakePeer:
    def __init__(self):
        self.ready = asyncio.Event()
        self.stop = asyncio.Event()
        self.client = None

    async def run(self):
        self.ready.set()
        await self.stop.wait()


class DriveRunTests(unittest.TestCase):
    def test_run_flow_with_retry_after_link_not_ready(self):
        cdc = FakeCdc(TMP / "cdc1.log", refuse_first_run=True)
        peer = FakePeer()
        asyncio.run(lab.drive_run(cdc, peer, "echo", "RUN 2 MIX", True, 10, pre=["CONNPARAM 6 12"]))
        self.assertEqual([c for c in cdc.sent if c.startswith("RUN")], ["RUN 2 MIX", "RUN 2 MIX"])
        self.assertIn("I2 ARM", cdc.sent)
        self.assertIn("CONNPARAM 6 12", cdc.sent)
        self.assertTrue(peer.stop.is_set())
        cdc.log.close()
        text = (TMP / "cdc1.log").read_text(encoding="utf-8")
        self.assertIn("#HOST SEND RUN 2 MIX", text)
        self.assertIn("\tCOUNTERS planned=2", text)

    def test_wait_times_out(self):
        cdc = FakeCdc(TMP / "cdc2.log")
        with self.assertRaises(TimeoutError):
            cdc.wait(r"^NEVER", 0, 0.3)
        cdc.log.close()

    def test_redacted_command_is_not_logged(self):
        cdc = FakeCdc(TMP / "cdc3.log")
        cdc.send("PROV KEY 65537 131073 " + "ab" * 32, log_as="PROV KEY 65537 131073 <key redacted>")
        time.sleep(0.1)
        cdc.log.close()
        self.assertNotIn("ab" * 32, (TMP / "cdc3.log").read_text(encoding="utf-8"))

    def test_parser_accepts_runbook_commands(self):
        for argv in (["selftest", "--out", "x"], ["provision", "--out", "x", "--key-file", "k"],
                     ["nonce-reboot", "--out", "x", "--cycles", "110"], ["nonce-unplug", "--out", "x"],
                     ["nonce-hooks", "--out", "x"], ["sentinel", "--out", "x", "--op", "write"],
                     ["loopback", "--out", "x", "--count", "1000", "--pattern", "MIX", "--expect-mtu", "247",
                      "--require-sizes", "113,153,6124,6380"],
                     ["negative", "--out", "x", "--only", "crc,stale"]):
            old = sys.argv
            sys.argv = ["week6_lab.py"] + argv
            try:
                captured = {}
                original = lab.argparse.ArgumentParser.parse_args

                def grab(parser, *a, **k):
                    captured["args"] = original(parser, *a, **k)
                    raise SystemExit(0)
                lab.argparse.ArgumentParser.parse_args = grab
                with self.assertRaises(SystemExit):
                    lab.main()
                self.assertEqual(captured["args"].command, argv[0])
            finally:
                lab.argparse.ArgumentParser.parse_args = original
                sys.argv = old


if __name__ == "__main__":
    unittest.main(verbosity=2)
