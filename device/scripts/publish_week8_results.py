#!/usr/bin/env python3
"""Copies the checked week 8 evidence into results/week8/device/ and derives small CSV tables.

Input is the week 8 lab root (D:/HUST/ASI_week8). Every folder used is named below; cdc.log,
peer logs, PPK2 raw words, the sample header/npz, Edge packages and photos stay outside Git and
are listed with their SHA-256 in manifest.json "raw_outside_git".
Only checker reports, summaries, receipts, build checks, the sample tables and tables derived
from cdc.log are copied. Refuses to overwrite. Every report must have the status listed here.

Run: device/host/.venv/Scripts/python.exe -B device/scripts/publish_week8_results.py \
       --lab D:/HUST/ASI_week8 --out results/week8/device
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

SAMPLES = "samples-20261023-c"
BUILDS = {"energy-usb": "build-20261026-clean-energy-usb", "energy": "build-20261026-clean-energy"}
# published name -> (path relative to --lab, expected status)
REPORTS = {
    "verify_tc2_clean.json": ("verify-clean-20261027-1420/check_verify.json", "PASS"),
    "verify_tc2_dirty_20261023.json": ("verify-20261023-1309/check_verify.json", "PASS"),
    "tc3_laptop_tail_200.json": ("cycles-tc3-20261023-1345/check_cycles.json", "PASS"),
    "tc3_laptop_edge_summary.json": ("cycles-tc3-20261023-1345/edge/summary.json", "PASS"),
    "kv260_g2_one0P0.json": ("kv260-one0P0-20261026-1517/check_cycles.json", "PASS"),
    "kv260_g2_one0P1.json": ("kv260-one0P1-20261026-1518/check_cycles.json", "PASS"),
    "kv260_g2_pairs5.json": ("kv260-pairs5-20261026-1518/check_cycles.json", "PASS"),
    "kv260_g2_pairs100.json": ("kv260-pairs100-20261026-1519/check_cycles.json", "PASS"),
    "kv260_g2_pairs100_peer_summary.json": ("kv260-pairs100-20261026-1519/edge/summary.json", "PASS"),
    "kv260_supp1_1M_one0P0.json": ("kv260-supp1-1M-one0P0-20261027-1351/check_cycles.json", "PASS"),
    # folder name says 2M; the link stayed 1M during this run (LINK phy_tx=0), see the report
    "kv260_supp2_1M_pairs5.json": ("kv260-supp2-2M-pairs5-20261027-1403/check_cycles.json", "PASS"),
    "kv260_supp4_2M_pairs5.json": ("kv260-supp4-2M-pairs5-20261027-1411/check_cycles.json", "PASS"),
    "ppk2_B5_session.json": ("B5-official-20261026-1328/check_session.json", "PASS"),
    "ppk2_B5_edge_summary.json": ("B5-official-20261026-1328/edge/summary.json", "PASS"),
    "phase_analysis_summary.json": ("B5-official-20261026-1328/analysis/summary.json", "PASS"),
    "ppk2_B5_attempt1_FAIL.json": ("B5-20261026-1225/check_session.json", "FAIL"),
    "ppk2_B5_attempt1_recheck_PASS.json": ("B5-20261026-1225/check_session_recheck.json", "PASS"),
}
KEPT_FAIL = ("ppk2_B5_attempt1_FAIL.json",)
PLAIN = {  # published name -> path relative to --lab (no status field)
    "samples/samples.csv": f"{SAMPLES}/samples.csv",
    "samples/excluded.csv": f"{SAMPLES}/excluded.csv",
    "samples/manifest.json": f"{SAMPLES}/manifest.json",
    "ppk2_B5_session_session.json": "B5-official-20261026-1328/session.json",
    "ppk2_B5_session_capture.json": "B5-official-20261026-1328/ppk2/capture.json",
    "ppk2_B5_session_note-20261026T063516Z.json": "B5-official-20261026-1328/note-20261026T063516Z.json",
    "cycles_200.csv": "B5-official-20261026-1328/analysis/cycles.csv",
    "ppk2_B5_attempt1_session.json": "B5-20261026-1225/session.json",
    "ppk2_B5_attempt1_capture.json": "B5-20261026-1225/ppk2/capture.json",
    "ppk2_B5_attempt1_note-20261026T053628Z.json": "B5-20261026-1225/note-20261026T053628Z.json",
    "ppk2_B5_attempt1_phase_analysis_summary.json": "B5-20261026-1225/analysis/summary.json",
    "ppk2_B5_attempt1_cycles_200.csv": "B5-20261026-1225/analysis/cycles.csv",
    # STATUS-only reads of the link after Set PHY (no cycle, no nonce); *.log is git-ignored
    "link_phy_status_conn2.log.txt": "kv260-supp3-phy-status-20261027-1400/cdc.log",
    "link_phy_status_conn3.log.txt": "kv260-supp4-2M-status-20261027-1405/cdc.log",
    "link_phy_status_tool.py.txt": "kv260-supp3-phy-status-20261027-1400/status_only.py",
}
# cdc.log of every console session -> link events and the G2 cycle table
SESSIONS = {
    "tc3_laptop": "cycles-tc3-20261023-1345",
    "kv260_g2_one0P0": "kv260-one0P0-20261026-1517",
    "kv260_g2_one0P1": "kv260-one0P1-20261026-1518",
    "kv260_g2_pairs5": "kv260-pairs5-20261026-1518",
    "kv260_g2_pairs100": "kv260-pairs100-20261026-1519",
    "kv260_supp1_1M": "kv260-supp1-1M-one0P0-20261027-1351",
    "kv260_supp2_1M": "kv260-supp2-2M-pairs5-20261027-1403",
    "kv260_supp4_2M": "kv260-supp4-2M-pairs5-20261027-1411",
}
RAW = (  # (path relative to --lab, note)
    (f"{SAMPLES}/week8_inputs.h", "W8-D3 sample header compiled into the image"),
    (f"{SAMPLES}/reference_s2.npz", "W8-D3 host reference x, q, scale, logits"),
    ("verify-clean-20261027-1420/cdc.log", "TC2 clean image"),
    ("verify-20261023-1309/cdc.log", "TC2 dirty image 23/10"),
    ("cycles-smoke-20261023-1340/cdc.log", "TC3 smoke 2 pairs"),
    ("cycles-tc3-20261023-1345/cdc.log", "TC3 laptop tail"),
    ("cycles-tc3-20261023-1345/edge/peer.jsonl", "TC3 laptop edge log"),
    ("check-readvertise-20261022-101933/cdc.log", "W8-D2 re-advertise check"),
    ("kv260-one0P0-20261026-1517/cdc.log", "G2 KV260"),
    ("kv260-one0P1-20261026-1518/cdc.log", "G2 KV260"),
    ("kv260-pairs5-20261026-1518/cdc.log", "G2 KV260"),
    ("kv260-pairs100-20261026-1519/cdc.log", "G2 KV260 (TC5)"),
    ("kv260-pairs100-20261026-1519/edge/peer_raw.jsonl", "G2 KV260 request log as received"),
    ("kv260-pairs100-20261026-1519/edge/peer.jsonl", "G2 KV260 request log normalised by import-peer"),
    ("kv260-supp1-1M-one0P0-20261026-1638/cdc.log", "aborted: KV260 did not connect in 600 s, not counted"),
    ("kv260-supp1-1M-one0P0-20261027-1351/cdc.log", "link check 1M"),
    ("kv260-supp2-2M-pairs5-20261027-1403/cdc.log", "link check, ran at 1M"),
    ("kv260-supp4-2M-pairs5-20261027-1411/cdc.log", "link check 2M"),
    ("B5-official-20261026-1328/edge/peer.jsonl", "B5 laptop edge log"),
    ("B5-official-20261026-1328/photos/bench-20261026.png", "B5 bench photo"),
    ("B5-20261026-1225/edge/peer.jsonl", "B5 attempt 1 laptop edge log"),
    ("photos/bench-kv260-20261026.png", "W8-D12 bench: KV260 ~50 cm"),
    ("photos/kv260-terminal-212-requests-20261026.png", "KV260 terminal, 212 requests"),
    ("gui_sv1.zip", "SV2 package: KV260 offline 100 samples"),
    ("ketqua/gui_sv1_g2.zip", "SV2 package: G2 request logs, offline run 2"),
    ("2710/gui_sv1_bo_sung.zip", "SV2 package: link check 27/10, Read/Set PHY logs"),
    ("from-trung-20261026-g2/review/offline_second/predictions.jsonl", "KV260 offline run 2 = --edge-reference"),
    ("from-trung-20261027-supp/request_logs/supp1_one_p0.jsonl", "SV2 export of raw/trial1/peer.jsonl"),
    ("from-trung-20261027-supp/request_logs/supp2_pairs5_1M.jsonl", "SV2 export of raw/trial2/peer.jsonl"),
    ("from-trung-20261027-supp/request_logs/supp4_pairs5_2M.jsonl", "SV2 export of raw/trial3_2m/peer.jsonl"),
)
CYCLE_KEYS = ("i", "pair", "rho", "n", "id", "seq", "rid", "label", "ref", "match", "logits",
              "head_us", "quant_us", "prot_us", "enc_us", "tx_us", "wait_us", "res")


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


def console_lines(path: Path):
    """(host ms, message) of a week8_lab.py cdc.log."""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stamp, _, message = line.partition("\t")
        if stamp.isdigit():
            yield int(stamp), message


def fields(message: str) -> dict:
    return dict(item.split("=", 1) for item in message.split()[1:] if "=" in item)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lab", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
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

    # TC1: static build checks of the two clean images
    build_rows = []
    for variant, folder in BUILDS.items():
        check, source = load(lab / folder / "week8_build_check.json"), load(lab / folder / "source.json")
        if check.get("status") != "PASS" or source.get("dirty"):
            raise SystemExit(f"{lab / folder}: static check not PASS or dirty tree")
        for item in ("week8_build_check.json", "source.json"):
            copy(lab / folder / item, out / "build_check" / f"{variant}_{item}", sources, out)
        build_rows.append([variant, check["build_id"], source["commit"][:12], check["bin_bytes"],
                           check["image_end_hex"], check["headroom_bytes"], check["ram_static_bytes"],
                           check["bin_sha256"]])
    write_csv(out / "build_resources.csv", ["variant", "build_id", "commit", "bin_bytes", "image_end",
                                            "headroom_before_0xDC000_bytes", "ram_static_bytes",
                                            "bin_sha256"], build_rows)
    sources["build_resources.csv"] = "derived: build_check/*_week8_build_check.json"

    failed_dfu = []
    for src in sorted((lab / "dfu").glob("dfu-*")):
        if src.suffix == ".json" and load(src).get("exit_code") != 0:
            failed_dfu.append(f"dfu/{src.name}")
        name = src.name + (".txt" if src.suffix == ".log" else "")   # *.log is git-ignored
        copy(src, out / "dfu" / name, sources, out)

    # TC6 table: mean, std, CI95 (Student-t) of every phase quantity per rho (laptop peer)
    summary = load(out / "phase_analysis_summary.json")
    rows = []
    for rho, group in summary["groups"].items():
        for quantity, d in group["stats"].items():
            rows.append([rho, quantity, d["n"], d.get("mean"), d.get("std"), d.get("ci95_half"),
                         d.get("ci95_rel_pct"), d.get("min"), d.get("max")])
    write_csv(out / "phase_energy_summary.csv", ["rho", "quantity", "n", "mean", "std", "ci95_half",
                                                 "ci95_rel_pct", "min", "max"], rows)
    sources["phase_energy_summary.csv"] = "derived: phase_analysis_summary.json groups"

    # TC4/TC8: link events as the dongle saw them; G2 cycle tables (DWT = CPU-active time only)
    link_rows = []
    for session, folder in SESSIONS.items():
        for stamp, message in console_lines(lab / folder / "cdc.log"):
            words = message.split()
            if message.startswith("EVT "):
                link_rows.append([session, stamp, " ".join(words[:2]), " ".join(words[2:])])
            elif message.startswith("CONNPARAM "):
                link_rows.append([session, stamp, words[0], " ".join(words[1:])])
            elif message.startswith("LINK "):
                f = fields(message)
                link_rows.append([session, stamp, "LINK", " ".join(
                    f"{k}={f[k]}" for k in ("connected", "att_mtu", "interval_1250us", "timeout_10ms",
                                            "phy_tx", "phy_rx", "connections") if k in f)])
    # drop repeated identical LINK lines (STATUS polling) inside one session
    deduped, last = [], {}
    for row in link_rows:
        if row[2] == "LINK" and last.get(row[0]) == row[3]:
            continue
        if row[2] == "LINK":
            last[row[0]] = row[3]
        deduped.append(row)
    write_csv(out / "link_events.csv", ["session", "host_ms", "event", "fields"], deduped)
    sources["link_events.csv"] = "derived: cdc.log EVT/CONNPARAM/LINK lines of " + ", ".join(SESSIONS.values())
    for session in ("kv260_g2_pairs100", "tc3_laptop"):
        rows, previous = [], None
        for stamp, message in console_lines(lab / SESSIONS[session] / "cdc.log"):
            if message.startswith("CYCLE "):
                f = fields(message)
                rows.append([stamp, stamp - previous if previous else ""] + [f.get(k, "") for k in CYCLE_KEYS])
                previous = stamp
        name = f"cycles_{session}.csv"
        write_csv(out / name, ["host_ms", "host_spacing_ms"] + list(CYCLE_KEYS), rows)
        sources[name] = f"derived: {SESSIONS[session]}/cdc.log CYCLE lines"

    raw = [raw_entry(lab / rel, note) for rel, note in RAW]
    for folder in ("B5-official-20261026-1328", "B5-20261026-1225"):
        capture = load(lab / folder / "ppk2" / "capture.json")
        raw.append({"path": str(lab / folder / "ppk2" / capture["raw_file"]), "sha256": capture["raw_sha256"],
                    "bytes": capture["raw_bytes"], "note": f"{folder}: PPK2 raw words (energy_phases.py)"})

    files = sorted(p for p in out.rglob("*") if p.is_file())
    manifest = {
        "schema": "week8-results-manifest/1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "kept_fail_reports": list(KEPT_FAIL),
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
