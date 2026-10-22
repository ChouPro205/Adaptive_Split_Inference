#!/usr/bin/env python3
"""Copies the checked week 7 evidence into results/week7/ and derives small CSV tables.

Inputs (raw traces, cdc.log, peer.jsonl stay outside Git; each is listed with its SHA-256 in
manifest.json "raw_outside_git"):
  --lab        laptop-USB session of week7_lab.py (bench TC7, verify TC4, dryrun) + dfu/ receipts
  --firmware   build_week7.ps1 folder with bench-fast, energy-usb-fast, energy-fast, energy-week4 (TC8)
  --a1 --a2 --b  week7_ppk2.py session folders (idle week 2 image, active week 1 image, session B)
  --b-failed   earlier session B attempts, published as kept FAIL reports (never as evidence)
  --ppk2-dfu   DFU receipts of the PPK2 day
  --figures    week7_figures.py output
Only checker reports, capture metadata, the cycle table, receipts, build checks, figures and
tables derived from them are copied. Refuses to overwrite.

Run: device/host/.venv/Scripts/python.exe -B device/scripts/publish_week7_results.py \
       --lab D:/HUST/ASI_week7/session-20261020 --firmware D:/HUST/ASI_week7/firmware-20261019 \
       --a1 <A1> --a2 <A2> --b <B> --ppk2-dfu <day>/dfu --figures <figures> --out results/week7
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

# published name -> path relative to --lab; KEPT_FAIL documents a checker bug fixed the same day
LAB_REPORTS = {
    "bench_tc7.json": "bench/check_bench.json",
    "verify_tc4.json": "verify2/check_verify.json",
    "verify_first_run_FAIL.json": "verify/check_verify.json",
    "dryrun_50p1_50p0.json": "dryrun/check_dryrun_recheck_block.json",
    "dryrun_first_check_FAIL.json": "dryrun/check_dryrun.json",
    "dryrun_stub_edge.json": "dryrun/stub/summary.json",
}
LAB_RAW = ("bench/cdc.log", "verify/cdc.log", "verify2/cdc.log", "dryrun/cdc.log",
           "dryrun/stub/peer.jsonl", "nonce/nonce_before_week7.txt")
KEPT_FAIL = {"verify_first_run_FAIL.json", "dryrun_first_check_FAIL.json"}
BUILDS = ("bench-fast", "energy-usb-fast", "energy-fast", "energy-week4")
PPK2 = {  # session flag -> (published prefix, checker report)
    "a1": ("ppk2_A1_idle_week2", "check_idle.json"),
    "a2": ("ppk2_A2_active_week1", "check_active.json"),
    "b": ("ppk2_B_session", "check_session.json"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))  # PowerShell writes a BOM


def write_csv(path: Path, header: list, rows: list) -> None:
    with open(path, "x", encoding="utf-8", newline="\n") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def copy(src: Path, dst: Path, sources: dict, out: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        raise SystemExit(f"refusing to overwrite {dst}")
    shutil.copyfile(src, dst)
    sources[dst.relative_to(out).as_posix()] = str(src)


def raw_entry(path: Path, note: str) -> dict:
    return {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size, "note": note}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lab", required=True, type=Path)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--a1", required=True, type=Path)
    parser.add_argument("--a2", required=True, type=Path)
    parser.add_argument("--b", required=True, type=Path)
    parser.add_argument("--b-failed", type=Path, action="append", default=[])
    parser.add_argument("--ppk2-dfu", type=Path)
    parser.add_argument("--figures", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    out = args.out
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty {out}")
    out.mkdir(parents=True, exist_ok=True)
    sources, raw = {}, []

    # laptop-USB evidence: TC7 bench, TC4 verify, dry run (timing/debug only, never energy)
    for name, rel in LAB_REPORTS.items():
        src = args.lab / rel
        status = load(src).get("status")
        if status != ("FAIL" if name in KEPT_FAIL else "PASS"):
            raise SystemExit(f"{src}: unexpected status {status}")
        copy(src, out / name, sources, out)
    for rel in LAB_RAW:
        if (args.lab / rel).exists():
            raw.append(raw_entry(args.lab / rel, "laptop-USB session"))
    # A failed DFU (e.g. bootloader port not opening) is kept and listed; the images measured are
    # checked separately: every session.json carries its own exit-0 receipt (week7_ppk2.image_info).
    receipt_dirs = [args.lab / "dfu"] + ([args.ppk2_dfu] if args.ppk2_dfu else [])
    failed_dfu = []
    for folder in receipt_dirs:
        for src in sorted(folder.glob("dfu-*")):
            if src.suffix == ".json" and load(src).get("exit_code") != 0:
                failed_dfu.append(f"dfu/{src.name}")
            name = src.name + (".txt" if src.suffix == ".log" else "")   # *.log is git-ignored
            copy(src, out / "dfu" / name, sources, out)

    # TC8: static build checks of the four images
    build_rows = []
    for variant in BUILDS:
        folder = args.firmware / variant
        check, source = load(folder / "week7_build_check.json"), load(folder / "source.json")
        if check.get("status") != "PASS" or source.get("dirty"):
            raise SystemExit(f"{folder}: static check not PASS or dirty tree")
        for item in ("week7_build_check.json", "source.json"):
            copy(folder / item, out / "build_check" / f"{variant}_{item}", sources, out)
        build_rows.append([variant, check["build_id"], source["commit"][:12], check["bin_bytes"],
                           check["image_end_hex"], check["headroom_bytes"], check["ram_static_bytes"],
                           check["bin_sha256"]])
    write_csv(out / "build_resources.csv", ["variant", "build_id", "commit", "bin_bytes", "image_end",
                                            "headroom_before_0xDC000_bytes", "ram_static_bytes",
                                            "bin_sha256"], build_rows)
    sources["build_resources.csv"] = "derived: build_check/*_week7_build_check.json"

    # TC7: t_dev per split, both kernels on the same image
    bench = load(out / "bench_tc7.json")
    keys = ["split", "W4_mean_ms", "W4_std_ms", "FAST_mean_ms", "FAST_std_ms",
            "speedup_vs_w4_same_image", "week4_published_mean_ms", "speedup_vs_week4_published"]
    write_csv(out / "t_dev_bench_by_split.csv", keys, [[r.get(k, "") for k in keys] for r in bench["t_dev_table"]])
    sources["t_dev_bench_by_split.csv"] = "derived: bench_tc7.json t_dev_table"

    # PPK2 sessions A1, A2, B (+ kept FAIL attempts of B)
    for flag, (prefix, report) in PPK2.items():
        folder = getattr(args, flag)
        if load(folder / report).get("status") != "PASS":
            raise SystemExit(f"{folder / report}: not PASS (publish FAIL attempts with --b-failed)")
        copy(folder / report, out / f"{prefix}.json", sources, out)
        copy(folder / "session.json", out / f"{prefix}_session.json", sources, out)
        copy(folder / "ppk2" / "capture.json", out / f"{prefix}_capture.json", sources, out)
        for note in sorted(folder.glob("note-*.json")):
            copy(note, out / f"{prefix}_{note.name}", sources, out)
        capture = load(folder / "ppk2" / "capture.json")
        raw.append({"path": str(folder / "ppk2" / capture["raw_file"]), "sha256": capture["raw_sha256"],
                    "bytes": capture["raw_bytes"], "note": f"{prefix}: PPK2 raw words (energy_phases.py)"})
    for k, folder in enumerate(args.b_failed, 1):
        status = load(folder / "check_session.json").get("status")
        if status != "FAIL":
            raise SystemExit(f"{folder}: --b-failed expects a FAIL attempt, got {status}")
        copy(folder / "check_session.json", out / f"ppk2_B_attempt{k}_FAIL.json", sources, out)
        # A FAIL that only a checker bug caused: the recheck (week7_ppk2.py recheck) and the
        # attempt's own tables go along as a replication of --b, never in place of it.
        recheck = folder / "check_session_recheck.json"
        if recheck.exists() and load(recheck).get("status") == "PASS":
            prefix = f"ppk2_B_attempt{k}"
            copy(recheck, out / f"{prefix}_recheck_PASS.json", sources, out)
            copy(folder / "session.json", out / f"{prefix}_session.json", sources, out)
            copy(folder / "ppk2" / "capture.json", out / f"{prefix}_capture.json", sources, out)
            copy(folder / "analysis" / "summary.json", out / f"{prefix}_phase_analysis_summary.json",
                 sources, out)
            copy(folder / "analysis" / "cycles.csv", out / f"{prefix}_cycles_100.csv", sources, out)
            for note in sorted(folder.glob("note-*.json")):
                copy(note, out / f"{prefix}_{note.name}", sources, out)
            capture = load(folder / "ppk2" / "capture.json")
            raw.append({"path": str(folder / "ppk2" / capture["raw_file"]), "sha256": capture["raw_sha256"],
                        "bytes": capture["raw_bytes"], "note": f"{prefix}: PPK2 raw words (replication)"})
            raw.append(raw_entry(folder / "stub" / "peer.jsonl", f"{prefix} stub edge"))
    b = args.b
    copy(b / "analysis" / "summary.json", out / "phase_analysis_summary.json", sources, out)
    copy(b / "analysis" / "cycles.csv", out / "cycles_100.csv", sources, out)
    copy(b / "stub" / "summary.json", out / "stub_edge_session.json", sources, out)
    for rel in ("stub/peer.jsonl", "stub.out"):
        if (b / rel).exists():
            raw.append(raw_entry(b / rel, "session B stub edge"))

    # TC6 tables: mean, std, CI95 (Student-t) of every phase quantity per rho; marker vs DWT
    summary = load(out / "phase_analysis_summary.json")
    rows = []
    for rho, group in summary["groups"].items():
        for quantity, d in group["stats"].items():
            rows.append([rho, quantity, d["n"], d.get("mean"), d.get("std"), d.get("ci95_half"),
                         d.get("ci95_rel_pct"), d.get("min"), d.get("max")])
    write_csv(out / "phase_energy_summary.csv", ["rho", "quantity", "n", "mean", "std", "ci95_half",
                                                 "ci95_rel_pct", "min", "max"], rows)
    sources["phase_energy_summary.csv"] = "derived: phase_analysis_summary.json groups"
    session = load(out / "ppk2_B_session.json")
    dwt = session.get("phase_vs_dwt") or []
    keys = ["rho", "phase", "marker_mean_ms", "dwt_mean_ms", "delta_ms", "delta_pct"]
    write_csv(out / "phase_time_marker_vs_dwt.csv", keys, [[r[k] for k in keys] for r in dwt])
    sources["phase_time_marker_vs_dwt.csv"] = "derived: ppk2_B_session.json phase_vs_dwt"

    for src in sorted(p for p in args.figures.iterdir() if p.suffix in (".pdf", ".png")):
        copy(src, out / "figures" / src.name, sources, out)

    files = sorted(p for p in out.rglob("*") if p.is_file())
    manifest = {
        "schema": "week7-results-manifest/1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "kept_fail_reports": sorted(KEPT_FAIL) + [f"ppk2_B_attempt{k}_FAIL.json"
                                                 for k in range(1, len(args.b_failed) + 1)],
        "failed_dfu_receipts": failed_dfu,
        "raw_outside_git": raw,
        "files": [{"path": p.relative_to(out).as_posix(), "sha256": sha256(p), "bytes": p.stat().st_size,
                   "source": sources.get(p.relative_to(out).as_posix(), "")} for p in files],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"published {len(files)} files -> {out}; raw outside Git: {len(raw)} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
