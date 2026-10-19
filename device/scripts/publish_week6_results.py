#!/usr/bin/env python3
"""Copies the checked week 6 dongle evidence into results/week6/ and derives small CSV tables.

Input: the lab session folder written by week6_lab.py / check_week6.py (raw cdc.log/peer.jsonl
stay there, outside Git) and the two build folders of build_week6.ps1. Only checker reports,
DFU receipts, static build checks and tables derived from them are copied; every copied or
derived file is listed with its SHA-256 and source in manifest.json. Refuses to overwrite.

Run: device/host/.venv/Scripts/python.exe -B device/scripts/publish_week6_results.py \
       --session D:/HUST/ASI_week6/device-session-20261019 \
       --build-default D:/HUST/ASI_week6/20261019-r1-default \
       --build-mtu23 D:/HUST/ASI_week6/20261019-r1-mtu23 --out results/week6
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# published name -> path relative to the session folder (all must be status PASS unless listed
# in KEPT_FAIL, which documents a checker-invocation mistake and is never used as evidence)
REPORTS = {
    "selftest_default.json": "01-selftest-default/check_selftest.json",
    "loopback_plain200_mtu247.json": "02-plain-200/check_loopback.json",
    "negative_19_summary.json": "03b-negative/summary.json",
    "negative_first_run_summary.json": "03-negative/summary.json",
    "negative_disconnect_mid_trial.json": "03a-trial-disconnect_mid/disconnect_mid/check_negative.json",
    "nonce_hooks.json": "05-nonce-hooks/check_nonce.json",
    "nonce_soft_reset_110.json": "06-nonce-soft/check_nonce.json",
    "nonce_power_cut_12.json": "07-nonce-power/check_nonce.json",
    "nonce_combined.json": "nonce-combined.json",
    "sentinel_dfu_default_to_mtu23.json": "09-sentinel-check.json",
    "sentinel_dfu_mtu23_to_default_wrong_baseline.json": "11-sentinel-check.json",
    "sentinel_dfu_mtu23_to_default.json": "11b-sentinel-check.json",
    "loopback_mtu23_4sizes_x10.json": "10-mtu23-sizes/check_loopback.json",
    "loopback_official_1000_mtu247.json": "12-official-1000/check_loopback.json",
}
KEPT_FAIL = {"negative_first_run_summary.json", "sentinel_dfu_mtu23_to_default_wrong_baseline.json"}
RUNS = {  # loopback runs -> table rows
    "plain200_mtu247": "loopback_plain200_mtu247.json",
    "mtu23_4sizes_x10": "loopback_mtu23_4sizes_x10.json",
    "official_1000_mtu247": "loopback_official_1000_mtu247.json",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))  # PowerShell writes a BOM


def write_csv(path: Path, header: list, rows: list) -> None:
    with open(path, "x", encoding="utf-8", newline="\n") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def stat(d: dict, key: str):
    return d.get(key, "") if d else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", required=True, type=Path)
    parser.add_argument("--build-default", required=True, type=Path)
    parser.add_argument("--build-mtu23", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    out = args.out
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty {out}")
    (out / "dfu").mkdir(parents=True, exist_ok=True)
    (out / "build_check").mkdir(exist_ok=True)
    sources = {}

    for name, rel in REPORTS.items():
        src = args.session / rel
        status = load(src).get("status")
        if status != ("FAIL" if name in KEPT_FAIL else "PASS"):
            raise SystemExit(f"{src}: unexpected status {status}")
        shutil.copyfile(src, out / name)
        sources[name] = str(src)
    for src in sorted((args.session / "dfu").glob("dfu-*")):
        if src.suffix == ".json" and load(src.with_suffix(".json")).get("exit_code") != 0:
            raise SystemExit(f"{src}: DFU exit code not 0")
        name = src.name + (".txt" if src.suffix == ".log" else "")  # *.log is git-ignored
        shutil.copyfile(src, out / "dfu" / name)
        sources[f"dfu/{name}"] = str(src)
    for variant, folder in (("default", args.build_default), ("mtu23", args.build_mtu23)):
        for item in ("week6_build_check.json", "source.json"):
            name = f"build_check/{variant}_{item}"
            shutil.copyfile(folder / item, out / name)
            sources[name] = str(folder / item)
        if load(folder / "week6_build_check.json").get("status") != "PASS":
            raise SystemExit(f"{folder}: static build check not PASS")

    # criterion 1-2: one row per P1 vector
    selftest = load(out / "selftest_default.json")
    keys = ["i", "s", "transformed_equals_python", "unprotect_byte_exact", "n80_equals_package",
            "request_equals_python", "descriptor_equals_package", "pass",
            "prot_cyc", "unprot_cyc", "enc_cyc", "sha_cyc"]
    write_csv(out / "p1_vectors_50.csv", keys, [[v.get(k, "") for k in keys] for v in selftest["p1_vectors"]])
    sources["p1_vectors_50.csv"] = "derived: selftest_default.json p1_vectors"

    # criterion 8: DWT per split (64 MHz)
    hz = selftest["dwt_clock_hz"]
    rows = []
    for split, d in sorted(selftest["dwt_cycles_by_split"].items(), key=lambda kv: int(kv[0][1:])):
        for op in ("quant", "prot", "unprot", "enc"):
            c = d.get(f"{op}_cyc") or {}
            if c:
                rows.append([split, op, c["n"], c["min"], c["median"], c["p95"], c["max"],
                             round(c["median"] * 1e6 / hz, 3)])
    write_csv(out / "dwt_by_split.csv", ["split", "operation", "n", "min_cycles", "median_cycles",
                                          "p95_cycles", "max_cycles", "median_us"], rows)
    sources["dwt_by_split.csv"] = "derived: selftest_default.json dwt_cycles_by_split, dwt_clock_hz"

    # criteria 3-5, 8: counters per run, RTT per frame size, stack high-water
    counter_rows, size_rows, stack_rows = [], [], []
    counter_keys = None
    for run, name in RUNS.items():
        r = load(out / name)
        counter_keys = counter_keys or list(r["counters"])
        counter_rows.append([run, r["run_begin"]["variant"], r["run_begin"]["att_mtu"]]
                            + [r["counters"][k] for k in counter_keys])
        for size, d in sorted(r["per_size"].items(), key=lambda kv: int(kv[0])):
            rtt, tx = d.get("rtt_ms") or {}, d.get("first_attempt_tx_ms") or {}
            size_rows.append([run, r["run_begin"]["att_mtu"], size, d["count"], "|".join(d["flags"]),
                              "|".join(d["s"]), d["fragments"], stat(rtt, "min"), stat(rtt, "median"),
                              stat(rtt, "p95"), stat(rtt, "max"), stat(tx, "median"),
                              round(d.get("echo_goodput_bytes_per_s", 0), 1)])
        for s in r["stack"]:
            stack_rows.append([run, s["name"], s["used"], s["size"]])
    for s in selftest["stack"]:
        stack_rows.append(["selftest_default", s["name"], s["used"], s["size"]])
    write_csv(out / "loopback_counters.csv", ["run", "variant", "att_mtu"] + counter_keys, counter_rows)
    write_csv(out / "loopback_rtt_by_size.csv",
              ["run", "att_mtu", "frame_bytes", "packets", "flags", "split_id", "fragments_per_direction",
               "rtt_min_ms", "rtt_median_ms", "rtt_p95_ms", "rtt_max_ms", "first_tx_median_ms",
               "echo_goodput_bytes_per_s"], size_rows)
    write_csv(out / "stack_highwater.csv", ["run", "thread", "used_bytes", "size_bytes"], stack_rows)
    for name in ("loopback_counters.csv", "loopback_rtt_by_size.csv", "stack_highwater.csv"):
        sources[name] = "derived: " + ", ".join(RUNS.values())

    files = sorted(p for p in out.rglob("*") if p.is_file())
    manifest = {
        "schema": "week6-results-manifest/1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "raw_session": str(args.session),
        "kept_fail_reports": sorted(KEPT_FAIL),
        "files": [{"path": p.relative_to(out).as_posix(), "sha256": sha256(p), "bytes": p.stat().st_size,
                   "source": sources.get(p.relative_to(out).as_posix(), "")} for p in files],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"published {len(files)} files -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
