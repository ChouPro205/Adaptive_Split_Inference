#!/usr/bin/env python3
"""Copies the checked week 10 evidence into results/week10/device/ (no device I/O).

The session folders are only known after the lab, so they are arguments: --session KIND=FOLDER (FOLDER
relative to --lab or absolute), KIND one of
  verify-ble, dry-ble, verify-prot, dry-prot, nonce     on-laptop checks (week10_lab.py), any status kept
  ewait, alls, prot                                     PPK2 sessions (week10_ppk2.py): the final check
                                                        (check_ewait / check_alls / check_session) must be PASS,
                                                        unless the folder is also given with --kept-fail
Summaries (week10_ppk2.py summary-*) with --summary, the week10_figures.py tables directory (with figures/)
with --analysis. Plan, references, load CSV, PROT block choice, the four clean builds and every DFU receipt of
the lab root are copied too. PPK2 raw words, cdc.log, KV260 request/PHY/queue logs, btmon captures, photos,
console logs and Trung's archives stay outside Git and are listed with SHA-256 in manifest.json
"raw_outside_git" (--raw PATH=NOTE adds files outside the session folders). Refuses to overwrite.

Run: device/host/.venv/Scripts/python.exe -B device/scripts/publish_week10_results.py --lab D:/HUST/ASI_week10 \
       --session verify-ble=verify-ble-20261112 --session dry-ble=dry4a-20261112-1557 ... \
       --session ewait=A1-... --session ewait=A2-... --session alls=B1-... --session prot=P1-... \
       --summary <summary-ewait dir> --summary <summary-alls dir> --summary <summary-prot dir> \
       --analysis <week10_figures tables dir> --out results/week10/device
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

KINDS = ("verify-ble", "dry-ble", "verify-prot", "dry-prot", "nonce", "ewait", "alls", "prot")
FINAL_CHECK = {"ewait": "check_ewait.json", "alls": "check_alls.json", "prot": "check_session.json"}
BUILDS = {"ble": "build-20261112-clean-ble", "ble-usb": "build-20261112-clean-ble-usb",
          "prot": "build-20261112-clean-prot", "prot-usb": "build-20261112-clean-prot-usb"}
FIXED = {"plan/manifest.json": "plan-20261112/manifest.json", "plan/prot_plan.csv": "plan-20261112/prot_plan.csv",
         "plan/ble_plan.csv": "plan-20261112/ble_plan.csv", "plan/ewait_load_blocks.csv": "plan-20261112/ewait_load_blocks.csv",
         "plan/week10_prot_plan.h": "plan-20261112/week10_prot_plan.h",
         "plan/week10_ble_plan.h": "plan-20261112/week10_ble_plan.h",
         "load/ewait_load_blocks.csv": "load-20261110/ewait_load_blocks.csv",
         "load/manifest.json": "load-20261110/manifest.json",
         "refs/refs.csv": "refs-20261112/refs.csv", "refs/sample_order.csv": "refs-20261112/sample_order.csv",
         "refs/manifest.json": "refs-20261112/manifest.json", "refs/SHA256SUMS.txt": "refs-20261112/SHA256SUMS.txt",
         "prot_block_choice.json": "prot-block-choice-20261112/prot_block_choice.json"}
# small files of a session folder that go into Git (relative to the folder; globs)
SMALL = ("session.json", "check_*.json", "energy_*.json", "ewait_rows*.csv", "alls_rows*.csv", "note-*.json",
         "analysis/summary.json", "ppk2/capture.json", "edge/summary.json", "edge/queue/queue_run.json",
         "edge/queue/queue_summary.json")
# large or raw files of a session folder: listed with SHA-256 only
RAW = ("cdc.log", "edge/kv260_requests_raw.jsonl", "edge/peer.jsonl", "edge/kv260_phy*", "edge/queue/jobs.jsonl",
       "analysis/cycles.csv", "edge/edge_reference_*")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def copy(src: Path, dst: Path, sources: dict, out: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        raise SystemExit(f"refusing to overwrite {dst}")
    shutil.copyfile(src, dst)
    sources[dst.relative_to(out).as_posix()] = str(src)


def raw_entry(path: Path, note: str) -> dict:
    return {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size, "note": note}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lab", required=True, type=Path, help="week 10 lab root (D:/HUST/ASI_week10)")
    p.add_argument("--session", action="append", default=[], help="KIND=FOLDER, KIND in " + ", ".join(KINDS))
    p.add_argument("--kept-fail", action="append", default=[], help="FOLDER of a session kept although FAIL")
    p.add_argument("--summary", action="append", type=Path, default=[], help="week10_ppk2.py summary-* directory")
    p.add_argument("--analysis", type=Path, help="week10_figures.py tables directory (with figures/)")
    p.add_argument("--raw", action="append", default=[], help="PATH=NOTE of a raw file outside the session folders")
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args(argv)
    lab, out = args.lab, args.out
    sessions = []
    for item in args.session:
        kind, _, folder = item.partition("=")
        if kind not in KINDS or not folder:
            raise SystemExit(f"--session {item!r}: expected KIND=FOLDER, KIND in {KINDS}")
        path = Path(folder) if Path(folder).is_absolute() else lab / folder
        if not path.is_dir():
            raise SystemExit(f"{path}: not a directory")
        sessions.append((kind, path))
    kept = {Path(k).name for k in args.kept_fail}
    for kind, path in sessions:
        if kind in FINAL_CHECK:
            status = load(path / FINAL_CHECK[kind]).get("status") if (path / FINAL_CHECK[kind]).exists() else None
            if status != "PASS" and path.name not in kept:
                raise SystemExit(f"{path}: {FINAL_CHECK[kind]} status {status}; pass --kept-fail to publish it anyway")
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty {out}")
    out.mkdir(parents=True, exist_ok=True)
    sources, reports, raw = {}, [], []

    for kind, path in sessions:
        dst_root = out / "sessions" / f"{kind}_{path.name}"
        for pattern in SMALL:
            for src in sorted(path.glob(pattern)):
                if src.is_file():
                    dst = dst_root / src.relative_to(path)
                    copy(src, dst, sources, out)
                    if src.name.startswith("check_"):
                        reports.append({"session": path.name, "kind": kind, "file": dst.relative_to(out).as_posix(),
                                        "status": load(src).get("status")})
        for pattern in RAW:
            for src in sorted(path.glob(pattern)):
                if src.is_file():
                    raw.append(raw_entry(src, f"{kind} {path.name}: {src.relative_to(path).as_posix()}"))
        cap = path / "ppk2" / "capture.json"
        if cap.exists():
            c = load(cap)
            raw.append({"path": str(path / "ppk2" / c["raw_file"]), "sha256": c["raw_sha256"], "bytes": c["raw_bytes"],
                        "note": f"{kind} {path.name}: PPK2 raw words"})
        for log in sorted(lab.glob(f"{path.name}.console.*")):
            raw.append(raw_entry(log, f"{kind} {path.name}: console output of the session command"))

    for folder in args.summary:
        for src in sorted(Path(folder).rglob("*")):
            if src.is_file():
                copy(src, out / "summaries" / Path(folder).name / src.relative_to(folder), sources, out)

    if args.analysis:
        for src in sorted(args.analysis.rglob("*")):
            if src.is_file():
                rel = src.relative_to(args.analysis)
                dst = out / ("figures" if rel.parts[0] == "figures" else "analysis") / \
                    (Path(*rel.parts[1:]) if rel.parts[0] == "figures" else rel)
                copy(src, dst, sources, out)

    for name, rel in FIXED.items():
        copy(lab / rel, out / name, sources, out)

    # TC1: static build checks of the four clean images
    rows = []
    for variant, folder in BUILDS.items():
        check, source = load(lab / folder / "week10_build_check.json"), load(lab / folder / "source.json")
        if check.get("status") != "PASS" or source.get("dirty"):
            raise SystemExit(f"{lab / folder}: static check not PASS or dirty tree")
        for item in ("week10_build_check.json", "source.json"):
            copy(lab / folder / item, out / "build_check" / f"{variant}_{item}", sources, out)
        rows.append([variant, check.get("build_id"), str(source.get("commit", ""))[:12], check.get("bin_bytes"),
                     check.get("image_end_hex"), check.get("headroom_bytes"), check.get("ram_static_bytes"),
                     check.get("plan_sha256"), check.get("bin_sha256")])
    with open(out / "build_resources.csv", "x", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["variant", "build_id", "commit", "bin_bytes", "image_end", "headroom_bytes", "ram_static_bytes",
                    "plan_sha256", "bin_sha256"])
        w.writerows(rows)
    sources["build_resources.csv"] = "derived: build_check/*_week10_build_check.json"

    failed_dfu = []
    for src in sorted((lab / "dfu").glob("dfu-*")):
        if src.suffix == ".json" and load(src).get("exit_code") != 0:
            failed_dfu.append(f"dfu/{src.name}")
        copy(src, out / "dfu" / (src.name + (".txt" if src.suffix == ".log" else "")), sources, out)

    for photo in sorted((lab / "photos").glob("*")) if (lab / "photos").is_dir() else []:
        raw.append(raw_entry(photo, "bench photo"))
    for item in args.raw:
        path, _, note = item.partition("=")
        raw.append(raw_entry(Path(path), note or "raw file"))

    files = sorted(q for q in out.rglob("*") if q.is_file())
    manifest = {
        "schema": "week10-results-manifest/1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "sessions": [{"kind": k, "folder": str(p)} for k, p in sessions],
        "kept_fail_sessions": sorted(kept),
        "check_reports": reports,
        "failed_dfu_receipts": failed_dfu,
        "raw_outside_git": raw,
        "files": [{"path": q.relative_to(out).as_posix(), "sha256": sha256(q), "bytes": q.stat().st_size,
                   "source": sources.get(q.relative_to(out).as_posix(), "")} for q in files],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"published {len(files)} files -> {out}; check reports {len(reports)} "
          f"({sum(r['status'] != 'PASS' for r in reports)} not PASS); raw outside Git: {len(raw)} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
