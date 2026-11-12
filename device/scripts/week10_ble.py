"""Week 10 radio-on cycle at every s (W10-D4): host references, KV260 request log, PPK2 cycle segmentation.

Shared by week10_lab.py / check_week10.py (ble-usb on laptop USB, TC2) and week10_ppk2.py session-alls /
import-alls (ble image on the PPK2, TC7). The rules are the ones of the week 8/9 checkers, per split:

  host references   device/week10/host_test/ble_shim.c (gcc, firmware numerics flags) gives q/scale of every
                    (sample, s) exactly as ble_cycle.c ble_head(), the FP32 s10 logits the dongle labels, and
                    the W10-D4 plan digest computed with the firmware's serialization; q/scale must equal the
                    week 9 refs (results/week9/device/refs, what VERIFY ALL checked on the dongle on 29/10)
  requests          the plain (rho0) I1 v2 request of sample n at s, built with contracts/i1v2_ref
  KV260 log         one JSON line per request (week 8/9 fields + split): the (sample, s) of a request is found
                    from (split, q_sha256, scale_sha256) in the refs; labels judged against the KV260 offline
                    predictions of the same q/scale (W8-D8) and logits bit-equal to them
  cycles            CTRL rising edge -> end of WAIT (s <= 9) or end of HEAD (s10); the plan says which s each
                    cycle is, the markers must agree (s10: no D2/D3; never D1 in the ble image)
"""
from __future__ import annotations

import ctypes as ct
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import energy_phases as ep  # noqa: E402
import week10_common as w10  # noqa: E402
import week9_common as w9  # noqa: E402

w8 = w9.w8
w7 = w8.w7
ROOT = w9.ROOT
WEEK10 = ROOT / "device" / "week10"
SHIM = WEEK10 / "host_test" / "ble_shim.c"
WEEK9_REFS = ROOT / "results" / "week9" / "device" / "refs"
R3_FIRMWARE = ROOT / "ml" / "results" / "week4-r3" / "firmware"
DEVICE_ONLY = 10
LOGITS = 5
EDGE_SPLITS = tuple(range(10))
SAMPLES = w10.ROUNDS                  # 50
FS = ep.SAMPLE_RATE_HZ
DT_MS = 1e3 / FS
CTRL, DEV, PROT, TX, WAIT = (ep.DEFAULT_MAP[n] for n in ("ctrl", "dev", "prot", "tx", "wait"))
SHIM_SOURCES = (SHIM, WEEK10 / "ble_plan_bytes.h", ROOT / "device" / "week8" / "g2_plan.h",
                ROOT / "device" / "week7" / "head_fast.c", ROOT / "device" / "week5" / "quantization.c",
                ROOT / "device" / "week6" / "sha256.c")


def frame_length_p0(channels: int, length: int) -> int:
    """I1 v2 plain request length (week 7 check_dryrun formula)."""
    return 68 + 8 * channels + channels * length


# ----------------------------------------------------------------------------- host references


def build_shim(directory: Path, samples: Path, plan: Path) -> ct.CDLL:
    cc = os.environ.get("CC") or shutil.which("gcc")
    if not cc:
        raise SystemExit("gcc not found (set CC): the week 10 host references need it")
    directory.mkdir(parents=True, exist_ok=True)
    out = directory / ("ble_shim.dll" if os.name == "nt" else "ble_shim.so")
    cmd = [cc, "-std=c11", "-O2", "-ffp-contract=off", "-fno-fast-math", "-shared", "-fPIC",
           "-Wall", "-Wextra", "-Werror", "-Wno-unknown-pragmas",
           "-I", str(WEEK10), "-I", str(ROOT / "device" / "week8"), "-I", str(ROOT / "device" / "week7"),
           "-I", str(ROOT / "device" / "week6"), "-I", str(ROOT / "device" / "src"),
           "-I", str(ROOT / "device" / "generated"), "-I", str(ROOT / "device" / "week5"),
           "-I", str(R3_FIRMWARE), "-I", str(samples), "-I", str(plan),
           "-o", str(out), str(SHIM), str(ROOT / "device" / "week7" / "head_fast.c"),
           str(ROOT / "device" / "week5" / "quantization.c"), str(ROOT / "device" / "week6" / "sha256.c")]
    subprocess.run(cmd, check=True)
    lib = ct.CDLL(str(out))
    lib.shim_set_sha256.restype = ct.c_char_p
    lib.shim_plan_sha256.restype = ct.c_char_p
    lib.shim_head_values.argtypes = [ct.c_uint, ct.c_uint, ct.POINTER(ct.c_float), ct.c_uint, ct.POINTER(ct.c_uint)]
    lib.shim_head_quant.argtypes = [ct.c_uint, ct.c_uint, ct.c_char_p, ct.c_uint, ct.c_char_p, ct.c_uint,
                                    ct.POINTER(ct.c_uint), ct.POINTER(ct.c_uint)]
    lib.shim_label.argtypes = [ct.POINTER(ct.c_float)]
    lib.shim_plan_digest.argtypes = [ct.c_char_p]
    return lib


def bits_hex(values) -> str:
    """FP32 values -> the firmware's logits text (8 lowercase hex digits each, comma separated)."""
    return ",".join(f"{w:08x}" for w in np.asarray(values, dtype="<f4").view("<u4").tolist())


class HostRefs:
    """q/scale of every (sample 0..49, s 0..10), s10 logits/labels and the plan digest, from the C path."""

    def __init__(self, samples: Path, plan: Path, workdir: Path):
        self.sample_set = w8.load_set(samples)
        self.plans = w10.load_plans(plan)
        self.refs9 = w9.load_refs(WEEK9_REFS, self.sample_set)
        lib = build_shim(Path(workdir), Path(samples), Path(plan))
        if lib.shim_set_sha256().decode() != self.sample_set.set_sha256:
            raise ValueError("shim set differs from the W8-D3 set")
        digest = ct.create_string_buffer(65)
        lib.shim_plan_digest(digest)
        self.plan_digest = digest.value.decode()
        self.plan_header_sha256 = lib.shim_plan_sha256().decode()
        self.tensors, self.s10 = {}, {}
        q = ct.create_string_buffer(8192)
        scale = ct.create_string_buffer(256)
        c, length = ct.c_uint(), ct.c_uint()
        for n in range(SAMPLES):
            for s in range(w9.SPLITS):
                status = lib.shim_head_quant(n, s, q, len(q), scale, len(scale), ct.byref(c), ct.byref(length))
                if status != 0:
                    raise ValueError(f"shim head/quant failed at n={n} s={s}")
                qb, sb = q.raw[:c.value * length.value], scale.raw[:2 * c.value]
                r = self.refs9[(n, s)]
                if (w9.sha256_hex(qb), w9.sha256_hex(sb), c.value, length.value) != \
                        (r.q_sha256, r.scale_sha256, r.channels, r.length):
                    raise ValueError(f"host q/scale differ from the week 9 refs at n={n} s={s}")
                self.tensors[(n, s)] = (c.value, length.value, qb, sb)
            out = (ct.c_float * 8)()
            count = ct.c_uint()
            if lib.shim_head_values(n, DEVICE_ONLY, out, 8, ct.byref(count)) != 0 or count.value != LOGITS:
                raise ValueError(f"shim s10 logits failed at n={n}")
            logits = np.array(out[:LOGITS], dtype="<f4")
            label = int(lib.shim_label(out))
            if label != w8.label(tuple(float(x) for x in logits)):
                raise ValueError(f"g2_label differs from week8_common.label at n={n}")
            self.s10[n] = (bits_hex(logits), label)
        self.by_hash = {(s, r.q_sha256, r.scale_sha256): n for (n, s), r in self.refs9.items()}

    def request(self, n: int, s: int, request_id: int) -> bytes:
        """Plain (rho0) I1 v2 request of sample n at split s, as the dongle sends it."""
        c, length, qb, sb = self.tensors[(n, s)]
        return w8.ref.encode_request(request_id, w7.registry_profile().model_profile_id, w7.wire_split_id(s),
                                     c, length, w7.scales_fp32(sb), qb, None, None)

    def bytes_payload(self, s: int) -> int:
        c, length, _, _ = self.tensors[(0, s)]
        return c * length + 2 * c


# ----------------------------------------------------------------------------- KV260 references and log


def load_edge_reference(paths, host: HostRefs) -> dict:
    """KV260 offline predictions (W8-D8) of the 50 samples at s0..s9: JSON lines with sample_id or
    set_index, split, logits (5 FP32) and, if present, q_sha256/scale_sha256 (must equal the refs).
    One or several files; every (sample, s) exactly once. Returns {(n, s): (logits bits, label)} plus
    the SHA-256 of each file."""
    index = {s.sample_id: n for n, s in enumerate(host.sample_set.samples)}
    out, sources = {}, {}
    for path in map(Path, paths):
        sources[str(path)] = w7.sha256_file(path)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            n = int(row["set_index"]) if "set_index" in row else index[row["sample_id"]]
            s = int(row["split"])
            values = np.array(row["logits"], dtype=np.float64)
            if not (0 <= n < SAMPLES and s in EDGE_SPLITS) or (n, s) in out:
                raise ValueError(f"{path}:{number}: (n={n}, s={s}) outside 0..49 x 0..9 or repeated")
            if "sample_id" in row and row["sample_id"] != host.sample_set.samples[n].sample_id:
                raise ValueError(f"{path}:{number}: sample_id differs from set_index {n}")
            if values.shape != (5,) or not np.array_equal(values.astype("<f4"), values):
                raise ValueError(f"{path}:{number}: logits not 5 FP32 values")
            r = host.refs9[(n, s)]
            if "q_sha256" in row and (row["q_sha256"].lower(), row["scale_sha256"].lower()) != (r.q_sha256, r.scale_sha256):
                raise ValueError(f"{path}:{number}: q/scale SHA-256 differ from the refs of (n={n}, s={s})")
            logits = values.astype("<f4")
            out[(n, s)] = (bits_hex(logits), w8.label(tuple(float(x) for x in logits)))
    missing = [(n, s) for n in range(SAMPLES) for s in EDGE_SPLITS if (n, s) not in out]
    if missing:
        raise ValueError(f"KV260 offline predictions miss {len(missing)} (sample, s), e.g. {missing[:3]}")
    return {"labels": out, "sources_sha256": sources}


def request_split(event: dict) -> int | None:
    """split of a KV260 log line: 'split' (0..9), or 'wire_split_id'/'split_id' (256 + s)."""
    if event.get("split") is not None:
        return int(event["split"])
    for key in ("wire_split_id", "split_id"):
        if event.get(key) is not None:
            return int(event[key]) - 256
    return None


def normalize_kv260_log(lines: list, host: HostRefs) -> tuple:
    """Request lines of the KV260 log -> (records, counters). Fields as week 8/9 (PEER_LOG_FIELDS) plus
    split; optional service_ms / tail_us (tail time) are kept."""
    import week8_lab as w8lab
    records, counters = [], {"response_sent": 0, "unknown_sample": 0, "not_ok": 0, "no_split": 0}
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("ev") != "request":
            continue
        rid = event["request_id"]
        r = {"request_id": int(rid, 16) if isinstance(rid, str) else int(rid), "rho": event.get("rho"),
             "result": event["result"], "line": number, "split": request_split(event)}
        for key in ("t_rx_ms", "t_tx_done_ms", "len", "att_mtu", "tail_us", "service_ms", "queue_wait_ms",
                    "connection", "q_at_arrival"):
            if key in event:
                r[key] = event[key]
        if r["split"] is None:
            counters["no_split"] += 1
        if r["result"] == "OK":
            r["q_sha256"], r["scale_sha256"] = event["q_sha256"].lower(), event["scale_sha256"].lower()
            r["logits"] = w8lab.logits_bits(event["logits"])
            r["label"] = w8.label(w8.logits_from_hex(r["logits"]))
            if "label" in event and int(event["label"]) != r["label"]:
                raise ValueError(f"line {number}: label {event['label']} is not argmax of the logits")
            r["sample"] = host.by_hash.get((r["split"], r["q_sha256"], r["scale_sha256"]))
            counters["response_sent"] += 1
            if r["sample"] is None:
                counters["unknown_sample"] += 1
        else:
            counters["not_ok"] += 1
        records.append(r)
    return records, counters


def evaluate_requests(records: list, counters: dict, plan_rows: list, edge_ref: dict | None,
                      dongle: dict | None = None) -> dict:
    """KV260 side of a dry run or an energy session: one request per s <= 9 cycle of plan_rows, in order,
    rho0, the plan's (sample, s), result OK, labels = KV260 offline (if given) per s. dongle: optional
    {cycle: (request_id, logits bits)} of the ble-usb console, compared bit for bit."""
    expected = [r for r in plan_rows if r.split != DEVICE_ONLY]
    got = [(r.get("sample"), r.get("split")) for r in records]
    per_s = {s: {"n": 0, "label_equal_offline": 0, "logits_equal_offline": 0} for s in EDGE_SPLITS}
    mismatches = []
    for row, rec in zip(expected, records):
        if rec.get("result") != "OK" or rec.get("split") not in per_s:
            continue
        entry = per_s[rec["split"]]
        entry["n"] += 1
        if edge_ref is not None and rec.get("sample") is not None:
            bits, label = edge_ref["labels"][(rec["sample"], rec["split"])]
            entry["label_equal_offline"] += rec["label"] == label
            entry["logits_equal_offline"] += rec["logits"] == bits
            if rec["logits"] != bits:
                mismatches.append({"cycle": row.cycle, "split": rec["split"], "sample": rec["sample"]})
    checks = {
        "one_request_per_edge_cycle": len(records) == len(expected),
        "requests_in_plan_order": got == [(r.sample, r.split) for r in expected],
        "all_rho0": all(r.get("rho") in ("P0", None) for r in records),
        "all_ok": counters.get("not_ok", 1) == 0 and counters.get("response_sent") == len(expected),
        "every_request_has_split": counters.get("no_split", 1) == 0,
        "every_request_known_sample": counters.get("unknown_sample", 1) == 0,
    }
    if edge_ref is not None:
        checks["labels_equal_kv260_offline_every_s"] = all(v["label_equal_offline"] == v["n"] for v in per_s.values()) \
            and sum(v["n"] for v in per_s.values()) == len(expected)
        checks["logits_bit_equal_kv260_offline"] = not mismatches and bool(records)
    if dongle is not None:
        pairs = [(dongle.get(row.cycle), rec) for row, rec in zip(expected, records)]
        checks["dongle_logits_equal_kv260_log"] = all(
            d is not None and d[0] == rec["request_id"] and d[1] == rec.get("logits") for d, rec in pairs) and bool(pairs)
    t_edge = {}
    for rec in records:
        if isinstance(rec.get("t_rx_ms"), (int, float)) and isinstance(rec.get("t_tx_done_ms"), (int, float)):
            t_edge.setdefault(rec.get("split"), []).append(rec["t_tx_done_ms"] - rec["t_rx_ms"])
    return {"checks": checks, "per_s": {str(k): v for k, v in per_s.items()}, "logit_mismatches": mismatches[:20],
            "t_edge_ms_by_s": {str(s): ep.describe(v) for s, v in sorted(t_edge.items(), key=lambda kv: (kv[0] is None, kv[0]))}}


# ----------------------------------------------------------------------------- PPK2 cycles of the ble image


def head_high_fraction(current: np.ndarray) -> float:
    """Share of 1 ms HEAD blocks above the high level, raw samples when HEAD is shorter than 1 ms (s0):
    week9_ppk2.segment_dev_cycles, the definition behind the week 9 Table III core E_dev."""
    import week9_ppk2 as w9p
    head = np.asarray(current, float)
    blocks = head[:head.size // 100 * 100].reshape(-1, 100).mean(axis=1) if head.size >= 100 else head
    return float(np.mean(blocks > w9p.HIGH_LEVEL_UA)) if blocks.size else float("nan")


def segment_ble_cycles(trace: ep.Trace, after: int, plan_rows: list) -> tuple:
    """Cycles after the self-test, mapped to the plan in order: each starts at a CTRL rising edge and ends
    at the fall of WAIT (s <= 9) or of HEAD (s10). Every 10 us sample goes to the phase whose marker is
    the only one set (W7-D11). Errors per cycle: missing/multiple/extra phases, order, overlap, D1 at all,
    a marker pulse after the end of the cycle (retry), truncated end."""
    names = {"ctrl": CTRL, "dev": DEV, "prot": PROT, "tx": TX, "wait": WAIT}
    runs = {n: ep.channel_runs(trace.bits, c) for n, c in names.items()}
    ctrl_s = runs["ctrl"][0]
    ctrl_s = ctrl_s[ctrl_s > after]
    mask = sum(1 << c for c in names.values())
    v = trace.v_supply_mv / 1000.0
    cycles = []
    for k, start in enumerate(ctrl_s):
        limit = int(ctrl_s[k + 1]) if k + 1 < ctrl_s.size else trace.n
        plan = plan_rows[k] if k < len(plan_rows) else None
        device_only = plan is not None and plan.split == DEVICE_ONLY
        inside = {}
        for n in names:
            s, e = runs[n]
            sel = (s >= start) & (s < limit)
            inside[n] = (s[sel], e[sel])
        errors = [] if plan is not None else ["beyond_plan"]
        needed = ("ctrl", "dev") if device_only else ("ctrl", "dev", "tx", "wait")
        for n in ("ctrl", "dev", "tx", "wait"):
            count = inside[n][0].size
            if n in needed and count == 0:
                errors.append(f"missing_{n}")
            if n in needed and count > 1:
                errors.append("retry_tx" if n == "tx" else f"multiple_{n}")
            if n not in needed and count:
                errors.append(f"unexpected_{n}")
        if inside["prot"][0].size:
            errors.append("unexpected_prot")
        last = "dev" if device_only else "wait"
        ends = inside[last][1]
        end = int(ends[0]) if ends.size else int(max((int(e[-1]) for s, e in inside.values() if e.size), default=start))
        if end >= trace.n - 1 or not ends.size:
            errors.append("truncated_end")
        order = [int(inside[n][0][0]) for n in needed if inside[n][0].size]
        if order != sorted(order):
            errors.append("phase_order")
        seg_bits = trace.bits[start:end] & mask
        seg_i = trace.current_ua[start:end]
        row = {"cycle": len(cycles), "split": plan.split if plan else None, "sample": plan.sample if plan else None,
               "round": plan.round if plan else None, "device_only": device_only,
               "start_sample": int(start), "end_sample": int(end), "t_cycle_ms": (end - start) * DT_MS,
               "E_cycle_uJ": v * float(np.sum(seg_i)) * ep.DT_S}
        accounted = 0.0
        for n in ("ctrl", "dev", "tx", "wait"):
            only = seg_bits == (1 << names[n])
            row[f"t_{n}_ms"] = int(np.count_nonzero(only)) * DT_MS
            row[f"E_{n}_uJ"] = v * float(np.sum(seg_i[only])) * ep.DT_S
            accounted += row[f"E_{n}_uJ"]
        gap = seg_bits == 0
        multi = (seg_bits != 0) & ((seg_bits & (seg_bits - 1)) != 0)
        row["t_gap_ms"] = int(np.count_nonzero(gap)) * DT_MS
        row["E_gap_uJ"] = v * float(np.sum(seg_i[gap])) * ep.DT_S
        row["overlap_samples"] = int(np.count_nonzero(multi))
        if row["overlap_samples"]:
            errors.append("phase_overlap")
        row["E_phases_uJ"] = accounted
        row["diff_pct"] = (100.0 * abs(row["E_cycle_uJ"] - accounted) / row["E_cycle_uJ"]
                           if row["E_cycle_uJ"] > 0 else float("nan"))
        row["dev_high_fraction"] = head_high_fraction(seg_i[seg_bits == (1 << DEV)])
        # Pulses after the end of the cycle and before the next CTRL: a retry or a firmware fault.
        for n in names:
            s, _ = runs[n]
            if np.any((s >= end) & (s < limit)):
                errors.append(f"after_end_{n}")
        row["errors"] = errors
        cycles.append(row)
    return cycles


def add_net(cycles: list, i_idle_ua: float, v_supply_mv: float) -> None:
    v = v_supply_mv / 1000.0
    for row in cycles:
        for n in ("ctrl", "dev", "tx", "wait", "cycle"):
            row[f"E_{n}_net_uJ"] = row[f"E_{n}_uJ"] - v * i_idle_ua * row[f"t_{n}_ms"] / 1e3


CYCLE_COLUMNS = ["cycle", "round", "sample", "split", "device_only", "start_sample", "end_sample", "t_cycle_ms",
                 "t_ctrl_ms", "t_dev_ms", "t_tx_ms", "t_wait_ms", "t_gap_ms", "E_cycle_uJ", "E_ctrl_uJ", "E_dev_uJ",
                 "E_tx_uJ", "E_wait_uJ", "E_gap_uJ", "overlap_samples", "E_phases_uJ", "diff_pct", "dev_high_fraction",
                 "E_cycle_net_uJ", "E_ctrl_net_uJ", "E_dev_net_uJ", "E_tx_net_uJ", "E_wait_net_uJ", "errors"]
