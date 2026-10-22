#!/usr/bin/env python3
"""Offline checks of week 7 dongle sessions recorded by week7_lab.py (cdc.log [+ stub/summary.json]).

  bench   TC7: CMP 220/220 bitwise (on-device W4 vs FAST) and every W4 output hash equal to the host
          kernel (test_week7_host.py --write-head-hashes); MIX 16/16; BENCH 100 valid timings per
          kernel and split -> t_dev table (ms), speed-up vs W4 and vs the week 4 published means.
  verify  TC4: for every VQ line q/scale SHA-256 equal to the SV3 quantization20 golden, except the
          3 FP16 scale bits at s=10 explained by the week 5 acceptance (week7_common.device_tensor,
          reported as explained_golden_differences); every VREQ (P0 plain, P1 PUBLIC_TEST key,
          sequence n+1, request_id n+1) equal to the request built by contracts/i1v2_ref + i2_ref
          from that tensor.
  dryrun  energy-usb + stub edge: every CYCLE OK, no Flash write inside a cycle, P1 sequences inside
          the block reserved at boot [session_reserved_sequence, reserved_through] (and above
          --prior-reserved-through, the NONCE value read before the session) and strictly increasing, frame lengths per I1 v2, stub PASS;
          DWT phase times summarized (debug only, never energy numbers).
Exit 0 = PASS. Writes a JSON report to a new --output path.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import week6_common as wc  # noqa: E402

ROOT = HERE.parents[1]
WEEK4_TIMING = ROOT / "results" / "week4" / "week4_timing_summary.csv"
CPU_HZ = 64_000_000


def lines_with(capture, tag: str) -> list:
    return [wc.kv(text) for _, text in capture if text.startswith(tag)]


def check_bench(capture, host_hashes: Path | None) -> dict:
    cmp_rows = lines_with(capture, "CMP n=")
    mix_rows = lines_with(capture, "MIX i=")
    host = {}
    if host_hashes:
        with open(host_hashes, encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                host[(int(row["sample"]), int(row["split"]))] = row["sha256"]
    cases = {(int(r["n"]), int(r["s"])) for r in cmp_rows}
    host_match = [r["w4_sha256"] == host.get((int(r["n"]), int(r["s"]))) for r in cmp_rows]
    mix_host = [r["sha256"] == host.get((int(r["n"]), int(r["s"]))) for r in mix_rows]
    timings = {}
    for _, text in capture:
        if text.startswith("CYCLES kernel="):
            r = wc.kv(text)
            timings.setdefault((r["kernel"], int(r["s"])), []).append(int(r["cycles"]))
    week4 = {}
    if WEEK4_TIMING.exists():
        with open(WEEK4_TIMING, encoding="utf-8") as handle:
            week4 = {int(r["split"]): float(r["mean_ms"]) for r in csv.DictReader(handle)}
    table = []
    for split in range(11):
        row = {"split": split}
        for kernel in ("W4", "FAST"):
            values = [c / CPU_HZ * 1e3 for c in timings.get((kernel, split), [])]
            row[f"{kernel}_n"] = len(values)
            if values:
                row[f"{kernel}_mean_ms"] = statistics.fmean(values)
                row[f"{kernel}_std_ms"] = statistics.stdev(values) if len(values) > 1 else 0.0
                row[f"{kernel}_min_ms"] = min(values)
                row[f"{kernel}_max_ms"] = max(values)
        if row.get("FAST_mean_ms") and row.get("W4_mean_ms"):
            row["speedup_vs_w4_same_image"] = row["W4_mean_ms"] / row["FAST_mean_ms"]
        if row.get("FAST_mean_ms") and week4.get(split):
            row["week4_published_mean_ms"] = week4[split]
            row["speedup_vs_week4_published"] = week4[split] / row["FAST_mean_ms"]
        table.append(row)
    s10 = table[10].get("speedup_vs_w4_same_image")
    checks = {
        "cmp_220_cases": len(cmp_rows) == 220 and len(cases) == 220,
        "cmp_all_bitwise_equal": bool(cmp_rows) and all(r["equal"] == "1" for r in cmp_rows),
        "cmp_end_pass_220": any(t.startswith("CMP END pass=220 total=220") for _, t in capture),
        "mix_16": len(mix_rows) == 16,
        "mix_all_equal_ref": bool(mix_rows) and all(r["equal_ref"] == "1" for r in mix_rows),
        "fast_1100_timings": sum(row.get("FAST_n", 0) for row in table) == 1100,
        "w4_1100_timings": sum(row.get("W4_n", 0) for row in table) == 1100,
    }
    if host:
        checks["w4_outputs_equal_host_kernel"] = bool(host_match) and all(host_match)
        checks["mix_outputs_equal_host_kernel"] = bool(mix_host) and all(mix_host)
    return {"checks": checks, "t_dev_table": table,
            "speedup_s10": s10, "speedup_s10_at_least_1_5": None if s10 is None else s10 >= 1.5,
            "note": "speed-up < 1.5x at s=10 is reported to GV before week 9 (TC7), not a FAIL"}


def check_verify(capture) -> dict:
    import week7_common as w7
    vq = lines_with(capture, "VQ n=")
    vreq = lines_with(capture, "VREQ n=")
    q_ok, req_ok, details, explained = [], [], [], []
    for r in vq:
        n, s = int(r["n"]), int(r["s"])
        g = w7.device_tensor(n, s)
        ok = r.get("q_sha256") == g.q_sha256 and r.get("scale_sha256") == g.scale_sha256
        q_ok.append(ok)
        if not ok:
            details.append({"n": n, "s": s, "what": "q/scale"})
        elif g.scale_sha256 != w7.golden_tensor(n, s).scale_sha256:
            explained.append({"n": n, "s": s, "channels": sorted(w7.mcu_scale_differences()[(n, s)])})
    for r in vreq:
        n, s, rid = int(r["n"]), int(r["s"]), int(r["rid"])
        p1 = r["rho"] == "P1"
        frame = w7.build_request(n, s, rid, w7.PUBLIC_TEST_KEY if p1 else None,
                                 int(r["seq"]) if p1 else None, mcu=True)
        ok = int(r["len"]) == len(frame) and r["sha256"] == w7.sha256_hex(frame)
        req_ok.append(ok)
        if not ok:
            details.append({"n": n, "s": s, "rho": r["rho"], "what": "request"})
    splits = sorted({int(r["s"]) for r in vq})
    checks = {
        "q_scale_cases": len(vq) == 20 * len(splits) and bool(vq),
        "q_scale_equal_golden": bool(q_ok) and all(q_ok),
        "request_cases": len(vreq) == 2 * len(vq),
        "requests_equal_python_reference": bool(req_ok) and all(req_ok),
    }
    return {"checks": checks, "splits": splits, "mismatches": details,
            "explained_golden_differences": explained,
            "explained_note": "q/scale compared with device_tensor(): SV3 golden except the FP16 "
                              "scale bits of results/week5/golden_difference_analysis.json"}


def check_dryrun(capture, stub_summary: Path | None, p1: int, p0: int, split: int,
                 prior_reserved: int | None = None) -> dict:
    rows = lines_with(capture, "CYCLE i=")
    # The first NONCE line follows the boot reservation: reserved_through is the END of the new
    # block and session_reserved_sequence its first value (week 6 nonce_store semantics).
    boot_nonce = next((wc.kv(t) for _, t in capture if t.startswith("NONCE status=")), {})
    reserved_at_boot = int(boot_nonce.get("reserved_through", "0"))
    block_first = int(boot_nonce.get("session_reserved_sequence", "0"))
    sequences = [int(r["seq"]) for r in rows if r["rho"] == "P1"]
    channels, length = {0: (1, 360), 1: (16, 360), 2: (16, 180), 3: (32, 180), 4: (32, 90),
                        5: (48, 90), 6: (48, 45), 7: (64, 45), 8: (64, 22), 9: (32, 1),
                        10: (5, 1)}[split]
    want_len = {"P1": 108 + 8 * channels + channels * length, "P0": 68 + 8 * channels + channels * length}
    checks = {
        "cycle_count": len(rows) == p1 + p0,
        "all_ok": bool(rows) and all(r["res"] == "OK" for r in rows),
        "rho_order": [r["rho"] for r in rows] == ["P1"] * p1 + ["P0"] * p0,
        "no_flash_write_in_cycle": all(r["nonce_writes"] == "0" for r in rows),
        "p1_sequence_in_boot_block": block_first > 0 and bool(sequences) and all(
            block_first <= s <= reserved_at_boot for s in sequences),
        "p1_sequence_strictly_increasing": all(b > a for a, b in zip(sequences, sequences[1:])),
        "frame_lengths": all(int(r["len"]) == want_len[r["rho"]] for r in rows),
        "single_attempt": all(r["invalid"] == "0" for r in rows),
    }
    if prior_reserved is not None:
        checks["p1_sequence_above_prior_reservation"] = bool(sequences) and all(
            s > prior_reserved for s in sequences)
    if stub_summary and stub_summary.exists():
        stub = json.loads(stub_summary.read_text(encoding="utf-8"))
        checks["stub_edge_pass"] = stub.get("status") == "PASS"
    phases = {}
    for key in ("ctrl_us", "head_us", "quant_us", "prot_us", "enc_us", "tx_us", "wait_us"):
        for rho in ("P1", "P0"):
            values = [int(r[key]) for r in rows if r["rho"] == rho]
            if values:
                phases[f"{rho}_{key}"] = {"mean": statistics.fmean(values), "min": min(values),
                                          "max": max(values)}
    return {"checks": checks, "reserved_through_at_boot": reserved_at_boot,
            "session_reserved_sequence": block_first, "prior_reserved_through": prior_reserved,
            "first_p1_sequence": sequences[0] if sequences else None,
            "last_p1_sequence": sequences[-1] if sequences else None,
            "dwt_phases_us": phases,
            "scope": "energy-usb on laptop power: timing/debug evidence only, not energy"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("kind", choices=["bench", "verify", "dryrun"])
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host-hashes", type=Path)
    parser.add_argument("--p1", type=int, default=50)
    parser.add_argument("--p0", type=int, default=50)
    parser.add_argument("--split", type=int, default=2)
    parser.add_argument("--prior-reserved-through", type=int,
                        help="dryrun: NONCE reserved_through read before the session")
    args = parser.parse_args()
    if args.output.exists():
        sys.exit(f"refusing to overwrite {args.output}")
    capture = wc.read_capture(args.session / "cdc.log")
    if args.kind == "bench":
        result = check_bench(capture, args.host_hashes)
    elif args.kind == "verify":
        result = check_verify(capture)
    else:
        result = check_dryrun(capture, args.session / "stub" / "summary.json", args.p1, args.p0,
                              args.split, args.prior_reserved_through)
    banner = next((t for _, t in capture if t.startswith("READY WEEK7")), "")
    report = {"schema": f"week7-check-{args.kind}/1", "session": str(args.session),
              "status": "PASS" if all(result["checks"].values()) else "FAIL",
              "device_banner": wc.kv(banner), **result,
              "tool_sha256": {n: wc.sha256_file(HERE / n) for n in ("check_week7.py", "week7_common.py")}}
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, ok in result["checks"].items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"RESULT: {report['status']} ({args.kind})")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
