"""Week 11 link ops (W11-D2, W11-D3): host references and the checkers of link-usb captures.

Shared by week11_lab.py / check_week11.py and test_week11_host.py:

  plan          a generate_week11_plan.py directory, authenticated: manifest PASS, file hashes = manifest, every
                session's CSV = week11_common.session_plan(), its digest = the manifest (and = PLAN_SHA256 once the
                plan is locked)
  link shim     device/week11/host_test/link_shim.c (gcc, firmware flags) with the session's week11_link_plan.h:
                the plan digest computed with the firmware's serialization, the C echo frame / ECHO-ACK v1
  S0c refs      the 100 W8-D3 inputs read out of week8_inputs.h by the S0c shim (C), encoded by the normative
                contracts/s0c_v1_ref/s0c_v1_ref.py (Python): what VERIFY must print (body, FP16 scale, k)
  verify        link-usb VERIFY: one VS0C line per sample = S0c refs; banner and VERIFY END: set, plan SHA-256 and
                the device's own plan digest
  session       link-usb SESSION dry run: one OP line per entry in plan order with (op, state, a, b) = plan;
                STATE/RECONNECT end with the state's parameters granted; ECHO length = a, ack/frame verified;
                S0C body/k = S0c refs of sample a. DWT times per op are reported (laptop power: debug only).
"""
from __future__ import annotations

import atexit
import ctypes as ct
import json
import os
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import test_week11_s0c_host as s0c_test  # noqa: E402  (shim builder + pinned S0c reference loader)
import week11_common as w11  # noqa: E402

# The S0c shim build directory of test_week11_s0c_host (a loaded DLL may stay locked on Windows).
atexit.register(shutil.rmtree, s0c_test.TMP, True)
ROOT = w11.ROOT
WEEK11 = ROOT / "device" / "week11"
GAP_PHY = {w11.PHY_1M: 1, w11.PHY_2M: 2, w11.PHY_CODED_S8: 4}   # BT_GAP_LE_PHY_*
# Filled when the plan is locked (deterministic generator: a regenerated directory gives the same bytes).
PLAN_SHA256: dict = {}


def kv(text: str) -> dict:
    out = {}
    for token in text.split(" "):
        key, sep, value = token.partition("=")
        if sep:
            out[key] = value
    return out


# ----------------------------------------------------------------------------- plan


def load_plan(directory: Path) -> dict:
    """{session: [Entry]} of an authenticated plan directory; ValueError otherwise."""
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS":
        raise ValueError(f"{directory} is not a PASS week 11 plan directory")
    for name, digest in manifest["outputs_sha256"].items():
        if s0c_test.sha256_file(directory / name) != digest:
            raise ValueError(f"{name} differs from its manifest")
    plans = {}
    for k in range(w11.SESSIONS):
        rows = w11.read_csv(directory / f"link_plan_s{k}.csv")
        if rows != w11.session_plan(k):
            raise ValueError(f"link_plan_s{k}.csv differs from the generator")
        digest = w11.sha256_hex(w11.plan_bytes(rows))
        if digest != manifest["sessions"][f"s{k}"]["plan_sha256"] or (PLAN_SHA256 and digest != PLAN_SHA256[k]):
            raise ValueError(f"session {k} digest {digest} differs from the manifest or the lock")
        plans[k] = rows
    return plans


def build_link_shim(directory: Path, plan: Path, session: int) -> ct.CDLL:
    cc = os.environ.get("CC") or shutil.which("gcc")
    if not cc:
        raise SystemExit("gcc not found (set CC): the week 11 host references need it")
    inc = Path(directory) / f"plan_s{session}"
    inc.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(plan) / f"week11_link_plan_s{session}.h", inc / "week11_link_plan.h")
    out = Path(directory) / f"link_shim-{os.getpid()}-s{session}{'.dll' if os.name == 'nt' else '.so'}"
    cmd = [cc, "-std=c11", "-O2", "-ffp-contract=off", "-fno-fast-math", "-shared", "-fPIC",
           "-Wall", "-Wextra", "-Werror", "-Wno-unknown-pragmas",
           "-I", str(WEEK11), "-I", str(inc), "-I", str(ROOT / "device" / "week6"),
           "-I", str(ROOT / "contracts" / "i1v2_ref"),
           "-o", str(out), str(WEEK11 / "host_test" / "link_shim.c"), str(WEEK11 / "echo_frames.c"),
           str(ROOT / "device" / "week6" / "sha256.c"), str(ROOT / "contracts" / "i1v2_ref" / "i1v2_codec.c")]
    subprocess.run(cmd, check=True)
    lib = ct.CDLL(str(out))
    lib.shim_plan_sha256.restype = ct.c_char_p
    lib.shim_plan_digest.argtypes = [ct.c_char_p]
    lib.shim_echo_frame.argtypes = [ct.c_char_p, ct.c_uint, ct.c_uint, ct.c_uint32, ct.c_int]
    lib.shim_echo_ack.argtypes = [ct.c_char_p, ct.c_uint, ct.c_char_p]
    lib.shim_echo_ack_check.argtypes = [ct.c_char_p, ct.c_uint, ct.c_char_p, ct.c_uint]
    return lib


def shim_digest(lib) -> str:
    out = ct.create_string_buffer(65)
    lib.shim_plan_digest(out)
    return out.value.decode()


def c_echo_frame(lib, length: int, request_id: int, ack: bool = True) -> bytes:
    buf = ct.create_string_buffer(w11.FRAME_MAX)
    n = lib.shim_echo_frame(buf, w11.FRAME_MAX, length, request_id, int(ack))
    return buf.raw[:n]


def c_ack(lib, sent: bytes) -> bytes:
    out = ct.create_string_buffer(w11.ACK_LENGTH)
    lib.shim_echo_ack(sent, len(sent), out)
    return out.raw


# ----------------------------------------------------------------------------- S0c refs


def s0c_refs(samples: Path) -> dict:
    """{n: (body_hex, scale_hex, k)} of the 100 W8-D3 inputs, encoded by the normative Python reference."""
    if s0c_test.sha256_file(Path(samples) / "week8_inputs.h") != s0c_test.WEEK8_INPUTS_SHA256:
        raise ValueError("week8_inputs.h is not the W8-D3 header")
    saved = s0c_test.SAMPLES
    s0c_test.SAMPLES = Path(samples)
    try:
        lib = s0c_test.build(True)
    finally:
        s0c_test.SAMPLES = saved
    if lib.shim_set_sha256().decode() != s0c_test.WEEK8_SET_SHA256:
        raise ValueError("S0c shim set differs from W8-D3")
    ref = s0c_test.load_ref()
    out = {}
    for n in range(100):
        x = np.zeros(360, dtype="<f4")
        if lib.shim_week8_input(n, x.ctypes.data_as(ct.POINTER(ct.c_float))) != 0:
            raise ValueError(f"no W8-D3 input {n}")
        body, scale, _ = ref.encode(x)
        out[n] = (body.hex(), np.asarray(scale, dtype="<f2").tobytes().hex(), body[1])
    return out


# ----------------------------------------------------------------------------- checkers


def banner_of(capture) -> dict:
    banners = [kv(t) for _, t in capture if t.startswith("READY WEEK11 ")]
    return banners[-1] if banners else {}


def banner_checks(banner: dict, session: int, digest: str, set_sha256: str) -> dict:
    return {
        "banner_variant_link_usb": banner.get("variant") == "link-usb",
        "banner_session": banner.get("session") == str(session),
        "banner_set_sha256": banner.get("set_sha256") == set_sha256,
        "banner_plan_sha256": banner.get("plan_sha256") == digest,
        "device_plan_digest_equal": banner.get("plan_device_sha256") == digest and banner.get("plan_ok") == "1",
        "banner_s0c_v1": banner.get("s0c") == "S0C-V1",
        "banner_states_entries": banner.get("states") == str(len(w11.STATES)),
    }


def check_verify(capture, refs: dict, session: int, digest: str, set_sha256: str) -> tuple:
    lines = [kv(t) for _, t in capture if t.startswith("VS0C n=")]
    end = [kv(t) for _, t in capture if t.startswith("VERIFY END")]
    seen, bad = set(), []
    for r in lines:
        n = int(r["n"])
        want = refs.get(n)
        ok = want is not None and r.get("body") == want[0] and r.get("scale") == want[1] \
            and r.get("k") == str(want[2]) and r.get("body_len") == str(len(want[0]) // 2)
        if not ok:
            bad.append(n)
        seen.add(n)
    checks = {
        **banner_checks(banner_of(capture), session, digest, set_sha256),
        "vs0c_one_line_per_sample": len(lines) == 100 and seen == set(range(100)),
        "vs0c_equal_python_reference": not bad and len(lines) == 100,
        "verify_end_plan_ok": len(end) == 1 and end[0].get("plan_ok") == "1"
                              and end[0].get("plan_device_sha256") == digest and end[0].get("s0c") == "S0C-V1",
    }
    lengths = [len(refs[n][0]) // 2 for n in range(100)]
    details = {"mismatched_samples": bad, "s0c_body_bytes": {"mean": statistics.mean(lengths), "min": min(lengths),
                                                             "max": max(lengths)}}
    return checks, details


def state_granted(r: dict, state: w11.LinkState) -> bool:
    phy = GAP_PHY[state.phy]
    return (r.get("interval_1250us") == str(state.interval_1250us) and r.get("latency") == str(state.latency)
            and r.get("timeout_10ms") == str(state.timeout_10ms) and r.get("phy_tx") == str(phy)
            and r.get("phy_rx") == str(phy) and r.get("tx_len") == str(state.tx_octets)
            and r.get("tx_dbm") == str(state.tx_power_dbm))


def check_session(capture, rows, first: int, count: int, refs: dict) -> tuple:
    ops = [kv(t) for _, t in capture if t.startswith("OP i=")]
    end = [kv(t) for _, t in capture if t.startswith("SESSION END")]
    want = rows[first:first + count]
    order = len(ops) == len(want) and all(
        int(o["i"]) == e.index and o.get("op") == w11.OP_NAMES[e.op] and int(o["state"]) == e.state
        and int(o["a"]) == e.a and int(o["b"]) == e.b for o, e in zip(ops, want))
    failed, refused, wrong = [], [], []
    times = {}
    for o, e in zip(ops, want):
        if o.get("res") != "OK":
            failed.append({"i": e.index, "op": w11.OP_NAMES[e.op], "res": o.get("res"), "state": e.state})
        if e.op in (w11.OP_STATE, w11.OP_RECONNECT):
            target = w11.STATES[e.state if e.op == w11.OP_STATE else w11.BASE]
            if not state_granted(o, target):
                refused.append({"i": e.index, "state": target.name})
        if e.op == w11.OP_ECHO and o.get("res") == "OK" and o.get("len") != str(e.a):
            wrong.append({"i": e.index, "what": "echo length"})
        if e.op == w11.OP_S0C and o.get("res") == "OK":
            body_hex, _, k = refs[e.a]
            if o.get("body") != str(len(body_hex) // 2) or o.get("k") != str(k):
                wrong.append({"i": e.index, "what": "s0c body/k"})
        key = (w11.STATES[e.state].name, w11.OP_NAMES[e.op], e.a, e.b)
        if o.get("res") == "OK":
            times.setdefault(key, []).append({f: int(o[f]) for f in ("tx_us", "wait_us", "head_us", "link_ms")
                                              if f in o})
    checks = {
        "op_lines_in_plan_order": order,
        "every_op_ok": not failed,
        "every_state_granted": not refused,
        "echo_lengths_and_s0c_match": not wrong,
        "session_end_counts": len(end) == 1 and end[0].get("ok") == str(len(want) - len(failed))
                              and end[0].get("count") == str(count),
    }
    summary = {}
    for (state, op, a, b), values in sorted(times.items()):
        row = {}
        for f in ("tx_us", "wait_us", "head_us", "link_ms"):
            xs = [v[f] for v in values if f in v]
            if xs and any(xs):
                row[f + "_median"] = statistics.median(xs)
        summary[f"{state}/{op}/{a}/{b}"] = {"n": len(values), **row}
    return checks, {"failed": failed, "refused": refused, "wrong": wrong,
                    "dwt_debug_only_laptop_power": summary}
