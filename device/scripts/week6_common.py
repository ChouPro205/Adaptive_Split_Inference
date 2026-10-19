"""Shared definitions of the week 6 laptop tools (week6_lab.py) and checkers (check_week6.py).

Capture format (cdc.log): one line per device line, "<host_ms>\t<text>"; host annotations are
"<host_ms>\t#HOST <text>". USB CDC is control/debug only; radio evidence comes from the BLE
peer log (peer.jsonl) and the device counters of frames that travelled over BLE.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "contracts" / "i1v2_ref"
I2REF = ROOT / "contracts" / "i2_ref"
for _p in (REF, I2REF):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

SERVICE = "74e40001-0994-465c-bcd4-b94671a54935"
RX = "74e40002-0994-465c-bcd4-b94671a54935"
TX = "74e40003-0994-465c-bcd4-b94671a54935"
NAME = "ASI-SV1"
APP_VID, APP_PID = 0x2FE3, 0x0004
PACKAGE_ID = "mitdb-week6-p1-50-20261016-v1"
PACKAGE = ROOT / "ml" / "artifacts" / "week6" / PACKAGE_ID
PACKAGE_MANIFEST_SHA256 = "d0914acbece63c9e5ab73801cb1ad1b6a8a20f67cc0aa73a0841d0ef1fd01c36"
REGISTRY = ROOT / "contracts" / "sv3_week5_approved_registry_v2.json"
REQUIRED_SIZES = (113, 153, 6124, 6380)
KEY_ID, SENDER_ID = 65537, 131073

EXCH_COUNTERS = ("planned", "sent_first", "retries", "timeouts", "disconnect_abort", "tx_stall",
                 "completed", "failed", "error_final", "edge_busy", "crc_fail", "byte_mismatch",
                 "duplicate_response", "stale_response", "invalid_response", "wrong_stream")

# Criterion 6: each scenario is a separate short run. The peer applies the fault to the
# first fault_count frames of the first request it sees; the rest of the run is normal.
# expect = exact device counters, reasm_min = minimum reassembly counters.
NEGATIVE_SCENARIOS = {
    "crc": dict(mode="echo", sizes="3076", count=2, fault_count=1,
                expect=dict(completed=2, failed=0, crc_fail=1, timeouts=1, retries=1)),
    "mismatch": dict(mode="echo", sizes="3076", count=2, fault_count=1,
                     expect=dict(completed=2, failed=0, byte_mismatch=1, timeouts=1, retries=1)),
    "drop_fragment": dict(mode="echo", sizes="3076", count=2, fault_count=1,
                          expect=dict(completed=2, failed=0, timeouts=1, retries=1),
                          reasm_min=dict(gap=1)),
    "duplicate_fragment": dict(mode="echo", sizes="3076", count=2, fault_count=1,
                               expect=dict(completed=2, failed=0, timeouts=0, retries=0),
                               reasm_min=dict(duplicate_fragment=1)),
    "reorder": dict(mode="echo", sizes="3076", count=2, fault_count=1,
                    expect=dict(completed=2, failed=0, timeouts=1, retries=1), reasm_min=dict(gap=1)),
    "malformed": dict(mode="echo", sizes="3076", count=2, fault_count=1,
                      expect=dict(completed=2, failed=0, timeouts=0, retries=0),
                      reasm_min=dict(malformed_fragment=1)),
    "orphan": dict(mode="echo", sizes="3076", count=2, fault_count=1,
                   expect=dict(completed=2, failed=0, timeouts=0, retries=0),
                   reasm_min=dict(orphan_fragment=1)),
    "superseded": dict(mode="echo", sizes="3076", count=2, fault_count=1,
                       expect=dict(completed=2, failed=0, timeouts=0, retries=0),
                       reasm_min=dict(superseded_transfer=1)),
    "header_mismatch": dict(mode="echo", sizes="3076", count=2, fault_count=1,
                            expect=dict(completed=2, failed=0, timeouts=1, retries=1),
                            reasm_min=dict(frame_header_mismatch=1)),
    "reasm_timeout": dict(mode="echo", sizes="3076", count=2, fault_count=1,
                          expect=dict(completed=2, failed=0, timeouts=1, retries=1),
                          reasm_min=dict(reassembly_timeout=1)),
    "disconnect_mid": dict(mode="echo", sizes="3076", count=2, fault_count=1,
                           expect=dict(completed=2, failed=0, disconnect_abort=1, retries=1),
                           reasm_min=dict(disconnect=1)),
    "disconnect_rx": dict(mode="echo", sizes="3076", count=2, fault_count=1,
                          expect=dict(completed=2, failed=0, disconnect_abort=1, retries=1)),
    "silent_once": dict(mode="echo", sizes="113", count=2, fault_count=1,
                        expect=dict(completed=2, failed=0, timeouts=1, retries=1)),
    "silent_all": dict(mode="echo", sizes="113", count=2, fault_count=3,
                       expect=dict(completed=1, failed=1, timeouts=3, retries=2)),
    "duplicate_response": dict(mode="echo", sizes="113", count=2, fault_count=1,
                               expect=dict(completed=2, failed=0, duplicate_response=1)),
    "stale": dict(mode="echo", sizes="113", count=2, fault_count=1,
                  expect=dict(completed=2, failed=0, stale_response=1)),
    "wrong_stream": dict(mode="echo", sizes="113", count=2, fault_count=1,
                         expect=dict(completed=2, failed=0, wrong_stream=1)),
    "busy_once": dict(mode="respond", sizes="113", count=2, fault_count=1,
                      expect=dict(completed=2, failed=0, edge_busy=1, retries=1)),
    "invalid_once": dict(mode="respond", sizes="113", count=2, fault_count=1,
                         expect=dict(completed=2, failed=0, invalid_response=1, retries=0)),
}

_KV = re.compile(r"(\w+)=(\S*)")


def kv(text: str) -> dict:
    """'TAG a=1 b=x' -> {'a': '1', 'b': 'x'}."""
    return dict(_KV.findall(text))


def read_capture(path: Path) -> list:
    """[(host_ms, text)] of device lines; host annotations start with '#HOST'."""
    out = []
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        stamp, _, text = raw.partition("\t")
        try:
            out.append((int(stamp), text))
        except ValueError:
            continue
    return out


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tool_hashes() -> dict:
    here = Path(__file__).resolve().parent
    names = ["week6_common.py", "week6_lab.py", "check_week6.py"]
    refs = [REF / "i1_ble_binding.py", REF / "i1v2_reference.py", I2REF / "i2_reference.py"]
    return {p.name: sha256_file(p) for p in [here / n for n in names] + refs if p.exists()}


def write_new_json(path: Path, data) -> None:
    path = Path(path)
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
