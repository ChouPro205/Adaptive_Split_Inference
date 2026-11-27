#!/usr/bin/env python3
"""Copies the checked week 11 evidence into results/week11/device/ (no device I/O).

Week 11 has no PPK2 session (W11-D1). Evidence: the plan of the week 12 lab, the static checks of the four
clean builds (link-usb/link x session 0/1), every DFU receipt, the two on-laptop VERIFY sessions (session.json +
check_*.json; cdc.log stays outside Git, listed with SHA-256) and extra analysis folders (--extra SRC=DEST, e.g.
the 2026-11-20 compression probe). Folders already in --out (TC5, written by week11_etx_tc5.py) are kept and
listed. Refuses to overwrite a file.

SHA-256 in manifest.json is of the LF bytes stored in Git: text files (.json .csv .md .py .h .c .txt) are hashed
with CRLF -> LF, so the manifest matches a checkout on any OS (.gitattributes eol=lf; .txt via core.autocrlf).

Run: device/host/.venv/Scripts/python.exe -B device/scripts/publish_week11_results.py --lab D:/HUST/ASI_week11 \
       --verify 0=verify-20261127-link-usb-s0 --verify 1=verify-20261127-link-usb-s1 \
       --extra <dir>=analysis/compression-20261120 --out results/week11/device
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

PLAN = "plan-20261127"
PLAN_FILES = ("manifest.json", "link_plan_s0.csv", "link_plan_s1.csv", "week11_link_plan_s0.h", "week11_link_plan_s1.h",
              "echo_vectors.json")
BUILDS = {f"{v}-s{s}": f"build-20261127b-clean-{v}-s{s}" for v in ("link-usb", "link") for s in (0, 1)}
TEXT = {".json", ".csv", ".md", ".py", ".h", ".c", ".txt"}


def sha256_lf(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.lower() in TEXT:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def sha256_raw(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def copy(src: Path, dst: Path, sources: dict, out: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        raise SystemExit(f"refusing to overwrite {dst}")
    shutil.copyfile(src, dst)
    sources[dst.relative_to(out).as_posix()] = str(src)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lab", required=True, type=Path, help="week 11 lab root (D:/HUST/ASI_week11)")
    p.add_argument("--verify", action="append", default=[], help="SESSION=FOLDER of a week11_lab.py verify run")
    p.add_argument("--extra", action="append", default=[], help="SRC=DEST (DEST relative to --out) folder to copy")
    p.add_argument("--note", action="append", default=[], help="PATH=NOTE of a lab folder kept outside Git")
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args(argv)
    lab, out = args.lab, args.out
    out.mkdir(parents=True, exist_ok=True)
    if (out / "manifest.json").exists():
        raise SystemExit(f"refusing to overwrite {out / 'manifest.json'}")
    sources, reports, raw = {}, [], []

    plan_manifest = load(lab / PLAN / "manifest.json")
    if plan_manifest.get("status") != "PASS":
        raise SystemExit("plan manifest is not PASS")
    for name in PLAN_FILES:
        copy(lab / PLAN / name, out / "plan" / name, sources, out)

    rows = []
    for variant, folder in BUILDS.items():
        check, source = load(lab / folder / "week11_build_check.json"), load(lab / folder / "source.json")
        if check.get("status") != "PASS" or source.get("dirty"):
            raise SystemExit(f"{lab / folder}: static check not PASS or dirty tree")
        for item in ("week11_build_check.json", "source.json"):
            copy(lab / folder / item, out / "build_check" / f"{variant}_{item}", sources, out)
        zips = sorted((lab / folder).glob("adaptive_split_week11_*.zip"))
        rows.append([variant, check.get("build_id"), str(source.get("commit", ""))[:12], check.get("bin_bytes"),
                     check.get("image_end_hex"), check.get("headroom_bytes"), check.get("ram_static_bytes"),
                     check.get("plan_sha256"), check.get("bin_sha256"), sha256_raw(zips[0]) if zips else ""])
        for z in zips:
            raw.append({"path": str(z), "sha256": sha256_raw(z), "bytes": z.stat().st_size, "note": f"DFU package {variant}"})
    with open(out / "build_resources.csv", "x", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["variant", "build_id", "commit", "bin_bytes", "image_end", "headroom_bytes", "ram_static_bytes",
                    "plan_sha256", "bin_sha256", "dfu_zip_sha256"])
        w.writerows(rows)
    sources["build_resources.csv"] = "derived: build_check/*_week11_build_check.json"

    failed_dfu = []
    for src in sorted((lab / "dfu").glob("dfu-*")):
        if src.suffix == ".json" and load(src).get("exit_code") not in (0, None):
            failed_dfu.append(f"dfu/{src.name}")
        copy(src, out / "dfu" / (src.name + (".txt" if src.suffix == ".log" else "")), sources, out)

    for item in args.verify:
        session, _, folder = item.partition("=")
        path = Path(folder) if Path(folder).is_absolute() else lab / folder
        for src in sorted(path.glob("check_*.json")) + [path / "session.json"]:
            dst = out / "sessions" / f"verify-s{session}_{path.name}" / src.name
            copy(src, dst, sources, out)
            if src.name.startswith("check_"):
                reports.append({"session": path.name, "kind": "verify", "file": dst.relative_to(out).as_posix(),
                                "status": load(src).get("status")})
        cdc = path / "cdc.log"
        if cdc.exists():
            raw.append({"path": str(cdc), "sha256": sha256_raw(cdc), "bytes": cdc.stat().st_size,
                        "note": f"verify session {session}: USB CDC log"})

    for item in args.extra:
        src_dir, _, dest = item.partition("=")
        src_dir = Path(src_dir)
        for src in sorted(src_dir.rglob("*")):
            if src.is_file():
                copy(src, out / dest / src.relative_to(src_dir), sources, out)

    notes = [{"path": k, "note": v} for k, _, v in (n.partition("=") for n in args.note)]
    files = sorted(q for q in out.rglob("*") if q.is_file() and q.name != "manifest.json")
    manifest = {
        "schema": "week11-results-manifest/1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "plan": {"folder": str(lab / PLAN), "sessions": plan_manifest.get("sessions")},
        "check_reports": reports,
        "failed_dfu_receipts": failed_dfu,
        "raw_outside_git": raw,
        "lab_notes": notes,
        "eol_note": "files[].sha256/bytes are of the LF bytes stored in Git (text suffixes hashed with CRLF -> LF)",
        "files": [{"path": q.relative_to(out).as_posix(), "sha256": sha256_lf(q),
                   "bytes": len(q.read_bytes().replace(b"\r\n", b"\n")) if q.suffix.lower() in TEXT else q.stat().st_size,
                   "source": sources.get(q.relative_to(out).as_posix(), "already in --out")} for q in files],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    bad = [r for r in reports if r["status"] != "PASS"]
    print(f"published {len(files)} files -> {out}; check reports {len(reports)} ({len(bad)} not PASS); "
          f"raw outside Git: {len(raw)}; failed DFU receipts: {len(failed_dfu)}")
    return 0 if not bad and not failed_dfu else 1


if __name__ == "__main__":
    sys.exit(main())
