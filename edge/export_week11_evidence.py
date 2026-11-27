"""Export compact, checksum-verified Week 11 results from retained captures."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "edge/server/week10"))
from evidence import save, seal, sha, verify

WEEK3_SHA = "9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90"
PACKAGE_A_SHA = "fcf3f8469f0671871aa1a9bafe0aea5053d10ccd2b7f8b60f015738454171e2c"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_checked(folder, required):
    if not set(required) <= verify(folder):
        raise ValueError(f"Missing sealed entries in {folder}")


def board_capture(folder, required):
    read_checked(folder / "raw", required)
    if not {"run.log", "exit_code.txt"} <= verify(folder, "shell.sha256"):
        raise ValueError(f"Missing sealed board command log in {folder}")
    if (folder / "exit_code.txt").read_text().strip() != "0":
        raise ValueError(f"Board command did not complete: {folder}")
    return folder / "raw"


def export(a):
    stress_raw = board_capture(a.stress_capture, ("run.json", "stress.py"))
    burst_raw = board_capture(a.burst_capture, ("config.json", "board_result.json", "delivery.sha256", "trace.csv"))
    read_checked(a.stress, ("summary.json", "memory.csv"))
    read_checked(a.burst, ("summary.json", "wait_by_q.csv"))
    read_checked(a.echo, ("summary.json", "echo_checks.csv", "echo_host.py"))

    stress = load(a.stress / "summary.json")
    burst = load(a.burst / "summary.json")
    echo = load(a.echo / "summary.json")
    run = load(stress_raw / "run.json")
    burst_config = load(burst_raw / "config.json")
    if stress["run_id"] != run["run_id"] or stress["source_inventory_sha256"] != sha(stress_raw / "sha256sum_results.txt"):
        raise ValueError("Stress analysis belongs to a different capture")
    if burst["source_inventory_sha256"] != sha(burst_raw / "sha256sum_results.txt"):
        raise ValueError("Burst analysis belongs to a different capture")
    required_sizes = {64, 104, 112, 128, 130, 256, 362, 512, 1024, 2048, 4096}
    if (not stress["execution_complete"] or stress["validated_switches"] != 10000
            or not stress["memory_samples_complete"] or stress["rss_source"] != ["psutil"]
            or stress["worker_returncode"] != 0 or stress["parity_mismatches"] != 0
            or not burst["workload_pass"] or burst["q_max"] < 12 or burst["dropped"] != 0
            or burst["completed"] != burst["arrived"] or burst["failed"] != 0
            or echo["status"] != "HOST_ECHO_OK" or not required_sizes <= set(echo["sizes_bytes"])):
        raise ValueError("An execution result is missing or incomplete")
    if stress["backend"] != run["backend"] or run["backend"] != burst_config["backend"]:
        raise ValueError("Backend identity differs between the two board runs")

    t1 = load(a.t1_receipt)
    t1_log = a.t1_log.read_text(encoding="utf-8").splitlines()
    expected_logs = {f"T1_LOAD_A_OK {PACKAGE_A_SHA} [1, 5]",
                     f"T1_REJECT_OLD_OK Checkpoint SHA-256 {WEEK3_SHA} differs from the approved {PACKAGE_A_SHA}"}
    if (t1["checkpoint"]["sha256"] != PACKAGE_A_SHA or t1["dry_run_logits_shape"] != [1, 5]
            or t1["synthetic"] or not t1["dry_run"] or t1["dpu_validation"] != "NOT_RUN"
            or not expected_logs <= set(t1_log)
            or a.t1_log.with_suffix(".exit_code.txt").read_text().strip() != "0"):
        raise ValueError("T1 HOST receipt or log differs")

    measured_sources = {
        "stress.py": sha(stress_raw / "stress.py"),
        "echo_host.py": sha(a.echo / "echo_host.py"),
    }
    for line in (burst_raw / "delivery.sha256").read_text().splitlines():
        digest, name = line.split("  ", 1)
        if name in {"burst.py", "burst_board.sh", "shared_queue.py"}:
            measured_sources[name] = digest
    if len(measured_sources) != 5 or any(
            sha(ROOT / "edge/server/week11" / name) != digest for name, digest in measured_sources.items()):
        raise ValueError("Source to publish differs from evidence")

    out = a.output
    out.mkdir(parents=True, exist_ok=False)
    for name, data in (("summary.json", stress), ("burst_summary.json", burst), ("echo_summary.json", echo)):
        save(out / name, data)
    for folder, name in ((a.stress, "memory.csv"), (a.burst, "wait_by_q.csv"), (a.echo, "echo_checks.csv")):
        # Normalize only the export. Git stores the CSV files with LF.
        (out / name).write_bytes((folder / name).read_bytes().replace(b"\r\n", b"\n"))
    save(out / "package_a_summary.json", dict(scope="HOST_CPU_DRY_RUN", checkpoint_sha256=PACKAGE_A_SHA,
         rejected_checkpoint_sha256=WEEK3_SHA, checkpoint_loaded=True, old_checkpoint_rejected=True,
         split_s=t1["split_point_s"], logits_shape=t1["dry_run_logits_shape"],
         calibration_split=t1["calibration"]["declared_split"],
         calibration_sha256=t1["calibration"]["sha256"], dpu_validation=t1["dpu_validation"]))

    save(out / "provenance.json", dict(schema_version=1, exporter_sha256=sha(Path(__file__)),
         stress_run_id=run["run_id"], stress_run_started_utc=run["created_utc"],
         stress_checkout_head_at_run=run["source_commit"], measured_sources_sha256=measured_sources,
         stress_raw_inventory_sha256=stress["source_inventory_sha256"],
         stress_analysis_inventory_sha256=sha(a.stress / "sha256sum_results.txt"),
         stress_shell_inventory_sha256=sha(a.stress_capture / "shell.sha256"),
         burst_started=(a.burst_capture / "run.log").read_text().splitlines()[0],
         burst_trace_sha256=burst_config["trace_sha256"],
         burst_raw_inventory_sha256=burst["source_inventory_sha256"],
         burst_analysis_inventory_sha256=sha(a.burst / "sha256sum_results.txt"),
         burst_shell_inventory_sha256=sha(a.burst_capture / "shell.sha256"),
         echo_inventory_sha256=sha(a.echo / "sha256sum_results.txt"),
         t1_receipt_sha256=sha(a.t1_receipt), t1_log_sha256=sha(a.t1_log),
         parity_inventory_sha256=run["parity_inventory_sha256"],
         packet_manifest_sha256=run["packet_manifest_sha256"]))
    seal(out, "sha256sum_export.txt")
    print("WEEK11_EXPORT_OK", out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("stress", "stress-capture", "burst", "burst-capture", "echo",
                  "t1-receipt", "t1-log", "output"):
        parser.add_argument("--" + field, type=Path, required=True)
    export(parser.parse_args())
