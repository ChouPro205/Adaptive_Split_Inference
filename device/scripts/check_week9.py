#!/usr/bin/env python3
"""Offline checks of week 9 dongle sessions recorded by week9_lab.py (cdc.log), dev-usb image.

  verify   TC2: VERIFY ALL prints one VQ line per (s, n), s = 0..10, n = 0..49, in that order; every
           sample ID, shape, payload bytes and q/scale SHA-256 equal the host C reference (refs.csv of
           generate_week9_refs.py); the banner reports the W8-D3 set, the W9-D4 plan and a plan digest
           computed on the device equal to it. TDEV ALL prints 50 timed runs per s (IRQs locked, after
           20 warm-up runs); the DWT head-only mean of every s is within --tolerance-pct of week 7 BENCH
           FAST (results/week7/device/t_dev_bench_by_split.csv), or within --floor-us for the
           microsecond-scale s where a few cycles of call overhead exceed the percentage. The table of
           t_dev (head, quantization, head + quantization = the D0 phase) per s is reported.
  session  SESSION [gap] [first] [count] dry run: every CYCLE of the plan in order (cycle, round,
           sample, split), result OK, payload bytes per tensor_sizes.csv, SESSION END with no failure.
           Laptop USB power: DWT times are CPU-time evidence, never energy numbers.
Exit 0 = PASS. Writes a JSON report to a new --output path.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import week6_common as wc  # noqa: E402
import week9_common as w9  # noqa: E402

w8 = w9.w8
MS_PER_CYCLE = 1000.0 / w9.CPU_HZ


def lines_with(capture, tag: str) -> list:
    return [wc.kv(text) for _, text in capture if text.startswith(tag)]


def banner_of(capture) -> dict:
    banners = [wc.kv(t) for _, t in capture if t.startswith("READY WEEK9 ")]
    return banners[-1] if banners else {}


def banner_checks(banner: dict, sample_set: w8.SampleSet) -> dict:
    return {
        "banner_variant_dev_usb": banner.get("variant") == "dev-usb",
        "banner_set_sha256": banner.get("set_sha256") == sample_set.set_sha256,
        "banner_plan_sha256": banner.get("plan_sha256") == w9.PLAN_SHA256,
        "device_plan_digest_equal": banner.get("plan_device_sha256") == w9.PLAN_SHA256
                                    and banner.get("plan_ok") == "1",
    }


def stats_ms(cycles: list) -> dict:
    values = [c * MS_PER_CYCLE for c in cycles]
    return {"n": len(values), "mean_ms": statistics.fmean(values) if values else None,
            "std_ms": statistics.stdev(values) if len(values) > 1 else 0.0,
            "min_ms": min(values) if values else None, "max_ms": max(values) if values else None}


def tdev_table(capture, tolerance_pct: float, floor_us: float) -> tuple:
    """(rows per split, every split within the rule) from the TD lines."""
    td = lines_with(capture, "TD s=")
    bench = w9.bench_fast_ms()
    rows, ok = [], []
    for s in range(w9.SPLITS):
        mine = [r for r in td if int(r["s"]) == s and "head_cyc" in r]
        head = stats_ms([int(r["head_cyc"]) for r in mine])
        quant = stats_ms([int(r["quant_cyc"]) for r in mine])
        total = stats_ms([int(r["total_cyc"]) for r in mine])
        within = False
        delta_pct = None
        if head["mean_ms"] is not None:
            delta_ms = head["mean_ms"] - bench[s]
            delta_pct = 100.0 * delta_ms / bench[s]
            within = abs(delta_pct) <= tolerance_pct or abs(delta_ms) * 1000.0 <= floor_us
        ok.append(len(mine) == w9.ROUNDS and [int(r["n"]) for r in mine] == list(range(w9.ROUNDS)) and within)
        rows.append({"split": s, "runs": len(mine), "head": head, "quant": quant, "head_plus_quant": total,
                     "bench_fast_week7_mean_ms": bench[s], "head_delta_pct_vs_bench": delta_pct,
                     "within_rule": within})
    return rows, all(ok)


def check_verify(capture, sample_set: w8.SampleSet, refs: dict, tolerance_pct: float = 2.0,
                 floor_us: float = 0.5) -> dict:
    vq = lines_with(capture, "VQ n=")
    end = lines_with(capture, "VERIFY END")
    banner = banner_of(capture)
    ok, mismatches = [], []
    for r in vq:
        key = (int(r["n"]), int(r.get("s", -1)))
        ref = refs.get(key)
        good = (ref is not None and r.get("id") == ref.sample_id and int(r.get("C", -1)) == ref.channels
                and int(r.get("L", -1)) == ref.length and int(r.get("bytes", -1)) == ref.bytes_payload
                and r.get("q_sha256") == ref.q_sha256 and r.get("scale_sha256") == ref.scale_sha256)
        ok.append(good)
        if not good:
            mismatches.append({"n": key[0], "s": key[1]})
    table, tdev_ok = tdev_table(capture, tolerance_pct, floor_us)
    tdsum = lines_with(capture, "TDSUM s=")
    checks = {
        **banner_checks(banner, sample_set),
        "vq_550_split_major_order": [(int(r["s"]), int(r["n"])) for r in vq]
                                    == [(s, n) for s in range(w9.SPLITS) for n in range(w9.ROUNDS)],
        "q_scale_id_shape_bytes_equal_host_reference": len(ok) == w9.CYCLES and all(ok),
        "verify_end": len(end) == 1 and end[0].get("splits") == "ALL"
                      and end[0].get("samples") == str(w9.ROUNDS)
                      and end[0].get("set_sha256") == sample_set.set_sha256,
        "tdev_11_splits_50_runs_irq_locked": [int(r["s"]) for r in tdsum] == list(range(w9.SPLITS))
                                             and all(r.get("runs") == str(w9.ROUNDS) and r.get("irq") == "locked"
                                                     and r.get("cpu_hz") == str(w9.CPU_HZ) for r in tdsum),
        "tdev_head_within_rule_of_week7_bench_fast": tdev_ok,
        "tdev_end": len(lines_with(capture, "TDEV END")) == 1,
    }
    return {"checks": checks, "mismatches": mismatches, "t_dev_table": table,
            "rule": f"|head mean - week 7 BENCH FAST| <= {tolerance_pct} % or <= {floor_us} us",
            "refs_dir": None, "set_sha256": sample_set.set_sha256, "plan_sha256": w9.PLAN_SHA256,
            "scope": "dev-usb on laptop power: q/scale bytes are MCU evidence; DWT times are CPU time"}


def check_session(capture, refs: dict, first: int = 0, count: int = w9.CYCLES) -> dict:
    rows = lines_with(capture, "CYCLE i=")
    plan = w9.plan_rows(w9.plan_splits())[first:first + count]
    begin = lines_with(capture, "SESSION BEGIN")
    end = lines_with(capture, "SESSION END")
    got = [(int(r["i"]), int(r["round"]), int(r["n"]), int(r["s"])) for r in rows]
    by_split = {}
    for r in rows:
        by_split.setdefault(int(r["s"]), []).append(int(r["head_cyc"]))
    checks = {
        "session_begin_plan_sha256": len(begin) == 1 and begin[0].get("plan_sha256") == w9.PLAN_SHA256
                                     and begin[0].get("first") == str(first) and begin[0].get("count") == str(count),
        "cycles_equal_plan_order": got == plan,
        "all_cycles_ok": len(rows) == count and all(r.get("res") == "OK" for r in rows),
        "bytes_equal_tensor_sizes": all(int(r["bytes"]) == refs[(int(r["n"]), int(r["s"]))].bytes_payload
                                        for r in rows if (int(r["n"]), int(r["s"])) in refs),
        "ids_equal_set": all(r.get("id") == refs[(int(r["n"]), int(r["s"]))].sample_id
                             for r in rows if (int(r["n"]), int(r["s"])) in refs),
        "session_end_no_failure": len(end) == 1 and end[0].get("ok") == str(count) and end[0].get("failed") == "0",
    }
    return {"checks": checks, "first": first, "count": count, "gap_ms": begin[0].get("gap_ms") if begin else None,
            "head_by_split_ms": {str(s): stats_ms(v) for s, v in sorted(by_split.items())},
            "ctrl_us": stats_ms([int(r["ctrl_cyc"]) for r in rows])["mean_ms"] * 1000.0 if rows else None,
            "scope": "dev-usb on laptop power: order/bytes evidence; DWT times are CPU time, not energy"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("kind", choices=["verify", "session"])
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory")
    parser.add_argument("--refs", type=Path, required=True, help="generate_week9_refs.py directory")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tolerance-pct", type=float, default=2.0, help="verify: TC2 DWT rule")
    parser.add_argument("--floor-us", type=float, default=0.5, help="verify: absolute floor of the rule")
    parser.add_argument("--first", type=int, default=0, help="session: first cycle")
    parser.add_argument("--count", type=int, default=w9.CYCLES, help="session: cycles")
    args = parser.parse_args()
    if args.output.exists():
        sys.exit(f"refusing to overwrite {args.output}")
    capture = wc.read_capture(args.session / "cdc.log")
    sample_set = w8.load_set(args.samples)
    refs = w9.load_refs(args.refs, sample_set)
    if args.kind == "verify":
        result = check_verify(capture, sample_set, refs, args.tolerance_pct, args.floor_us)
        result["refs_dir"] = str(args.refs)
    else:
        result = check_session(capture, refs, args.first, args.count)
    report = {"schema": f"week9-check-{args.kind}/1", "session": str(args.session),
              "status": "PASS" if all(result["checks"].values()) else "FAIL",
              "device_banner": banner_of(capture), **result,
              "tool_sha256": {n: wc.sha256_file(HERE / n) for n in ("check_week9.py", "week9_common.py")}}
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, ok in result["checks"].items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    if args.kind == "verify":
        for row in result["t_dev_table"]:
            h = row["head"]["mean_ms"]
            print(f"s={row['split']:2d} head {h if h is None else round(h, 4)} ms "
                  f"(bench {row['bench_fast_week7_mean_ms']:.4f}, d={row['head_delta_pct_vs_bench']}) "
                  f"head+quant {row['head_plus_quant']['mean_ms']}")
    print(f"RESULT: {report['status']} ({args.kind})")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
