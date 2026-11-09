#!/usr/bin/env python3
"""Copies the checked week 9 evidence into results/week9/device/ (no device I/O).

Inputs: the week 9 lab root (D:/HUST/ASI_week9), the week9_figures.py tables directory (with its
figures/), and Trung's B5 log folder of 09/11 (D:/HUST/Trung/0911). Every folder used is named below.
PPK2 raw words, cdc.log, KV260 request/PHY/btmon logs, photos and console logs stay outside Git and
are listed with their SHA-256 in manifest.json "raw_outside_git". Only checker reports, summaries,
receipts, build checks, notes, the plan/reference tables and the analysis tables/figures are copied.
Refuses to overwrite; every report must have the status listed here (FAIL reports are kept on purpose).

Run: device/host/.venv/Scripts/python.exe -B device/scripts/publish_week9_results.py \
       --lab D:/HUST/ASI_week9 --analysis D:/HUST/ASI_week9/analysis-20261109 \
       --kv260-logs D:/HUST/Trung/0911 --out results/week9/device
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

BUILDS = {"dev": "build-20261029-clean-dev", "dev-usb": "build-20261029-clean-dev-usb",
          "dev-reg0-ldo": "build-20261029-clean-dev-reg0-ldo", "dev-reg1-ldo": "build-20261029-clean-dev-reg1-ldo"}
B4 = {"b4_s1": "B4-s1-20261029-1302", "b4_s2": "B4-s2-20261029-1320", "b4_s3": "B4-s3-20261029-1340"}
REG = {"b4_reg0ldo": "B4-reg0ldo-20261029-1405", "b4_reg1ldo": "B4-reg1ldo-20261029-1423"}
B5_OK = {"b5_kv260_p1": "B5-20261109-1419", "b5_kv260_p4": "B5-20261109-1509-p4"}
B5_FAIL = {"b5_kv260_p2": "B5-20261109-1438-p2", "b5_kv260_p3": "B5-20261109-1457-p3"}
# published name -> (path relative to --lab, expected status)
REPORTS = {
    "tc2_verify.json": ("verify-20261029-1223/check_verify.json", "PASS"),
    "tc2_session_dry_gap0.json": ("session-dry-20261029-1230/check_session.json", "PASS"),
    "tc2_session_dry_gap1000.json": ("session-dry-gap1000-20261029-1236/check_session.json", "PASS"),
}
for tag, folder in B4.items():
    # original reports FAIL only TC4_no_sample_above_3mA_between_cycles (RTC OVERFLOW, rule revised 8417d87)
    REPORTS[f"{tag}_check_session_FAIL_original.json"] = (f"{folder}/check_session.json", "FAIL")
    REPORTS[f"{tag}_check_session_recheck.json"] = (f"{folder}/check_session_recheck.json", "PASS")
REPORTS["b4_reg0ldo_check_session.json"] = (f"{REG['b4_reg0ldo']}/check_session.json", "PASS")
# experiment only: one s1 cycle 0.505 % shorter than DWT (HFINT faster with REG1 LDO), see the report
REPORTS["b4_reg1ldo_check_session_FAIL.json"] = (f"{REG['b4_reg1ldo']}/check_session.json", "FAIL")
for tag, folder in B5_OK.items():
    REPORTS[f"{tag}_check_session.json"] = (f"{folder}/check_session.json", "PASS")
    REPORTS[f"{tag}_check_kv260.json"] = (f"{folder}/check_kv260.json", "PASS")
    REPORTS[f"{tag}_energy_kv260_s2.json"] = (f"{folder}/energy_kv260_s2.json", "PASS")
    REPORTS[f"{tag}_edge_summary.json"] = (f"{folder}/edge/summary.json", "PASS")
for tag, folder in B5_FAIL.items():
    REPORTS[f"{tag}_check_session_FAIL.json"] = (f"{folder}/check_session.json", "FAIL")
# session 2: KV260 log imported (labels, PHY, match PASS); the only failed check is no_data_loss
REPORTS["b5_kv260_p2_check_kv260_FAIL.json"] = (f"{B5_FAIL['b5_kv260_p2']}/check_kv260.json", "FAIL")
REPORTS["b5_kv260_p2_energy_kv260_s2_FAIL.json"] = (f"{B5_FAIL['b5_kv260_p2']}/energy_kv260_s2.json", "FAIL")
REPORTS["b5_kv260_p2_edge_summary.json"] = (f"{B5_FAIL['b5_kv260_p2']}/edge/summary.json", "PASS")
KEPT_FAIL = tuple(k for k, (_, s) in REPORTS.items() if s == "FAIL")

PLAIN = {"plan/plan.csv": "plan-20261029/plan.csv", "plan/manifest.json": "plan-20261029/manifest.json",
         "plan/week9_plan.h": "plan-20261029/week9_plan.h", "refs/refs.csv": "refs-20261029/refs.csv",
         "refs/manifest.json": "refs-20261029/manifest.json",
         "b4_compare_s1_s2.json": "B4-compare-s1-s2-20261029.json",
         "b4_compare_s2_s3.json": "B4-compare-s2-s3-20261029.json"}
for tag, folder in {**B4, **REG}.items():
    PLAIN[f"{tag}_energy_dev.json"] = f"{folder}/energy_dev.json"
    PLAIN[f"{tag}_session.json"] = f"{folder}/session.json"
    PLAIN[f"{tag}_capture.json"] = f"{folder}/ppk2/capture.json"
    PLAIN[f"{tag}_analysis_summary.json"] = f"{folder}/analysis/summary.json"
for tag, folder in {**B5_OK, **B5_FAIL}.items():
    PLAIN[f"{tag}_session.json"] = f"{folder}/session.json"
    PLAIN[f"{tag}_capture.json"] = f"{folder}/ppk2/capture.json"
    PLAIN[f"{tag}_analysis_summary.json"] = f"{folder}/analysis/summary.json"
RAW = (  # (path relative to --lab, note)
    ("verify-20261029-1223/cdc.log", "TC2 VERIFY ALL + TDEV ALL on dev-usb"),
    ("session-dry-20261029-1230/cdc.log", "TC2 dry SESSION gap 0"),
    ("session-dry-gap1000-20261029-1236/cdc.log", "TC2 dry SESSION gap 1000 ms"),
    ("photos/bench-B4-start-20261029-1259.png", "B4 bench start (TC3)"),
    ("photos/bench-B4-after-s2-20261029-1331.png", "B4 bench end (TC3)"),
    ("photos/bench-B5-start-20261109-1419.png", "B5 bench start, KV260 next to the PPK2"),
    ("photos/bench-B5-end-20261109-1520.png", "B5 bench end"),
)
TRUNG = tuple(  # (path relative to --kv260-logs, note); session 3 log not sent (trace unusable)
    (f"phien{k}/{name.format(k=k)}", f"{note}, B5 session {k}") for k in (1, 2, 4) for name, note in (
        ("SHA256SUMS.txt", "Trung's SHA-256 list"), ("b5_p{k}_requests.jsonl", "KV260 request log"),
        ("b5_p{k}_phy.log", "KV260 Read PHY log"), ("b5_p{k}_run.json", "KV260 service run record (commit, model)"),
        ("b5_p{k}_summary.json", "KV260 service summary"), ("b5_p{k}.btsnoop", "btmon capture")))


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


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lab", required=True, type=Path)
    p.add_argument("--analysis", required=True, type=Path, help="week9_figures.py tables directory")
    p.add_argument("--kv260-logs", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    lab, out = args.lab, args.out
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty {out}")
    out.mkdir(parents=True, exist_ok=True)
    sources = {}

    for name, (rel, expected) in REPORTS.items():
        status = load(lab / rel).get("status")
        if status != expected:
            raise SystemExit(f"{lab / rel}: status {status}, expected {expected}")
        copy(lab / rel, out / name, sources, out)
    for name, rel in PLAIN.items():
        copy(lab / rel, out / name, sources, out)
    for tag, folder in {**B4, **REG, **B5_OK, **B5_FAIL}.items():
        for note in sorted((lab / folder).glob("note-*.json")):
            copy(note, out / f"{tag}_{note.name}", sources, out)

    # TC1: static build checks of the four clean images
    rows = []
    for variant, folder in BUILDS.items():
        check, source = load(lab / folder / "week9_build_check.json"), load(lab / folder / "source.json")
        if check.get("status") != "PASS" or source.get("dirty"):
            raise SystemExit(f"{lab / folder}: static check not PASS or dirty tree")
        for item in ("week9_build_check.json", "source.json"):
            copy(lab / folder / item, out / "build_check" / f"{variant}_{item}", sources, out)
        modes = check.get("regulator_modes") or {}
        rows.append([variant, check["build_id"], source["commit"][:12], check.get("regulator", "board"),
                     " ".join(f"{k}={v}" for k, v in modes.items()), check["bin_bytes"], check["image_end_hex"],
                     check["headroom_bytes"], check["ram_static_bytes"], check["bin_sha256"]])
    with open(out / "build_resources.csv", "x", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["variant", "build_id", "commit", "regulator", "regulator_modes", "bin_bytes", "image_end",
                    "headroom_before_0xDC000_bytes", "ram_static_bytes", "bin_sha256"])
        w.writerows(rows)
    sources["build_resources.csv"] = "derived: build_check/*_week9_build_check.json"

    failed_dfu = []
    for src in sorted((lab / "dfu").glob("dfu-*")):
        if src.suffix == ".json" and load(src).get("exit_code") != 0:
            failed_dfu.append(f"dfu/{src.name}")
        copy(src, out / "dfu" / (src.name + (".txt" if src.suffix == ".log" else "")), sources, out)

    # analysis tables + figures (week9_figures.py)
    for src in sorted(args.analysis.rglob("*")):
        if src.is_file():
            rel = src.relative_to(args.analysis)
            dst = out / ("figures" if rel.parts[0] == "figures" else "analysis") / \
                (Path(*rel.parts[1:]) if rel.parts[0] == "figures" else rel)
            copy(src, dst, sources, out)

    raw = [raw_entry(lab / rel, note) for rel, note in RAW]
    raw += [raw_entry(args.kv260_logs / rel, note) for rel, note in TRUNG]
    for tag, folder in {**B4, **REG, **B5_OK, **B5_FAIL}.items():
        cap = load(lab / folder / "ppk2" / "capture.json")
        raw.append({"path": str(lab / folder / "ppk2" / cap["raw_file"]), "sha256": cap["raw_sha256"],
                    "bytes": cap["raw_bytes"], "note": f"{folder}: PPK2 raw words"})
        for log in sorted(lab.glob(f"{folder}.console.*")):
            raw.append(raw_entry(log, f"{folder}: console output of the session command"))
    for folder in (*B5_OK.values(), B5_FAIL["b5_kv260_p2"]):
        for rel in ("edge/kv260_requests_raw.jsonl", "edge/peer.jsonl", "edge/kv260_phy.log"):
            raw.append(raw_entry(lab / folder / rel, f"{folder}: imported KV260 log"))

    files = sorted(q for q in out.rglob("*") if q.is_file())
    manifest = {
        "schema": "week9-results-manifest/1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "kept_fail_reports": list(KEPT_FAIL),
        "failed_dfu_receipts": failed_dfu,
        "raw_outside_git": raw,
        "files": [{"path": q.relative_to(out).as_posix(), "sha256": sha256(q), "bytes": q.stat().st_size,
                   "source": sources.get(q.relative_to(out).as_posix(), "")} for q in files],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"published {len(files)} files -> {out}; raw outside Git: {len(raw)} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
