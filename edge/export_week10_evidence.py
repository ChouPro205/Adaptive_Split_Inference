#!/usr/bin/env python3
"""Export small, checksum-verified Week 10 results without running hardware."""
import argparse
from collections import Counter
import csv
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tarfile
import tempfile

from server.week10 import evidence


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def inspect_lab(folder, backend, stats):
    archive = folder.with_name(folder.name + ".tar.gz")
    digest = evidence.sha(archive)
    expected = archive.with_name(archive.name + ".sha256.txt").read_text().split()[0]
    if digest != expected:
        raise ValueError(f"Archive checksum mismatch: {archive.name}")
    listed = evidence.verify(folder, "SHA256SUMS")
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        names = [member.name for member in members]
        if set(names) != listed | {"SHA256SUMS"} or len(names) != len(set(names)):
            raise ValueError(f"Archive inventory mismatch: {archive.name}")
        for member in members:
            if not member.isfile():
                raise ValueError(f"Expected a regular archive member: {member.name}")
            with tar.extractfile(member) as stream:
                actual = hashlib.sha256(stream.read()).hexdigest()
            if actual != evidence.sha(evidence.child(folder, member.name)):
                raise ValueError(f"Archive bytes differ: {member.name}")
    capture = folder / "capture"
    run = read_json(capture / "run.json")
    trial = read_json(folder / "trial.json")
    summary = read_json(capture / "summary.json")
    review = read_json(folder / "review.json")
    if run["backend"] != backend:
        raise ValueError(f"Backend differs: {folder.name}")
    rows = [r for r in read_rows(capture / "requests.jsonl") if r.get("ev") == "request"]
    if len(rows) != summary["rows"] or summary["expected"] != trial["expected"]:
        raise ValueError(f"Request count differs: {folder.name}")
    warm = [r for r in rows if r.get("model_cache_hit") and not r["response_cache_hit"]
            and r.get("previous_s") != r["split"] and r["result"] == "OK"]
    phy = read_rows(capture / "phy.jsonl")
    queue = capture / "queue_sim"
    queue_data = None
    if queue.is_dir():
        config = read_json(queue / "queue_run.json")["config"]
        jobs = [r for r in read_rows(queue / "jobs.jsonl") if r["event"] == "enqueue"]
        foreground = {r["job_id"]: r for r in jobs if r["kind"] == "foreground"}
        offsets = [foreground[r["job_id"]]["enqueued_ns"] / 1e6 - r["t_rx_ms"]
                   for r in rows if r.get("job_id") in foreground]
        queue_data = {
            "seed": config["seed"],
            "scenario_sha256": config["scenario_sha256"],
            "mqtt_enabled": config["mqtt_enabled"],
            "foreground_joined_count": len(offsets),
            "enqueue_minus_rx_min_ms": min(offsets, default=None),
            "enqueue_minus_rx_max_ms": max(offsets, default=None),
            "summary": read_json(queue / "queue_summary.json"),
        }
    return {
        "capture_id": folder.name,
        "archive_sha256": digest,
        "archive_size_bytes": archive.stat().st_size,
        "inventory_sha256": evidence.sha(folder / "SHA256SUMS"),
        "lab_source_sha256": {name: evidence.sha(folder / "lab_source" / name)
                              for name in ("ble_week10.py", "lab.py", "shared_queue.py", "lab_config.py")},
        "request_count": len(rows),
        "expected_count": trial["expected"],
        "ok_count": sum(r["result"] == "OK" for r in rows),
        "offline_bit_exact_count": sum(r.get("offline_bit_exact") is True for r in rows),
        "plan_match_count": sum(r.get("plan_match") is True for r in rows)
        if trial["mode"] == "cache" else None,
        "requests_by_split": dict(Counter(r["split"] for r in rows)),
        "requests_by_protection": dict(Counter(r["rho"] for r in rows)),
        "queue_mode": trial["queue_mode"],
        "queue": queue_data,
        "phy_2m_before_first_rx": bool(rows) and any(
            p["tx_phy"] == p["rx_phy"] == "2M" and p["hci_status"] == 0
            and p["t_ms"] <= rows[0]["t_rx_ms"] for p in phy),
        "trace_check_exit": read_json(folder / "trace_check.json")["returncode"],
        "warm_switch": stats(r["switch_ms"] for r in warm),
        "warm_directed_pairs": len({(r["previous_s"], r["split"]) for r in warm}),
        "service_status": summary["status"],
        "service_error": summary["error"],
        "device_disconnect_observed": summary["device_disconnect_observed"],
        "edge_review_status": review["status"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--lab-imports", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    capture = args.capture.resolve()
    inventory = read_json(capture / "capture_receipt.json")["files"]
    for relative, expected in inventory.items():
        if evidence.sha(evidence.child(capture, relative)) != expected:
            raise ValueError(f"Capture checksum mismatch: {relative}")

    sys.path.insert(0, str(capture / "source/edge/server/week10"))
    analyzer = importlib.import_module("analyze")
    run, _, _, complete = analyzer.read_run(capture / "benchmark")
    backend = run["backend"]
    offline = {}
    for name in ("smoke_nho", "smoke_day_du", "parity"):
        info, summary, rows, valid = analyzer.read_run(capture / name)
        if not valid or info["backend"] != backend:
            raise ValueError(f"Incomplete or different backend: {name}")
        offline[name] = {
            "run_id": info["run_id"], "row_count": len(rows),
            "parity_mismatches": summary["parity_mismatches"],
            "max_contexts": max(r["contexts_count"] for r in rows),
        }
    if not complete:
        raise ValueError("Benchmark incomplete")
    lab = [inspect_lab(args.lab_imports / name, backend, analyzer.stats)
           for name in ("4a", "4b", "A1_lan_2", "A2", "B1", "B2")]
    with tempfile.TemporaryDirectory() as scratch:
        derived = Path(scratch) / "analysis"
        summary = analyzer.analyze(capture / "benchmark", derived)
        args.output.mkdir(parents=True, exist_ok=False)
        evidence.save(args.output / "summary.json", summary)
        evidence.save(args.output / "lab_summary.json", lab)
        evidence.save(args.output / "provenance.json", {
            "schema_version": 1,
            "capture_receipt_sha256": evidence.sha(capture / "capture_receipt.json"),
            "benchmark_created_utc": run["created_utc"],
            "benchmark_host": run["host"],
            "backend": backend,
            "offline_checks": offline,
            "acquired_source_files": run["source_files"],
            "measurement_scope": "KV260 offline benchmark and Edge-side BLE captures",
        })
        with (derived / "timing.csv").open(newline="") as source, (
                args.output / "warm_switch_samples.csv").open("x", newline="") as dest:
            writer = csv.writer(dest, lineterminator="\n")
            writer.writerow(("previous_s", "split_s", "switch_ms"))
            for row in csv.DictReader(source):
                if row["phase"] == "warm_switch" and row["previous_s"] != row["split_s"]:
                    writer.writerow((row["previous_s"], row["split_s"], row["switch_ms"]))
    evidence.seal(args.output, "sha256sum_export.txt")


if __name__ == "__main__":
    main()
