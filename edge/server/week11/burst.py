"""Replay a bounded FIFO burst on KV260 and verify its captured results on HOST."""
import argparse
import csv
import json
import math
from pathlib import Path
import random
import shutil
from statistics import mean
import sys
import time

REFERENCE_MS_PER_JOB = 51.7
SPLIT = 2


def trace(candidates, seed):
    rng = random.Random(seed)
    return [dict(job_id=group * 16 + slot + 1, t_arrival_ms=group * 3000 + slot,
                 service_ms_nominal=REFERENCE_MS_PER_JOB, vector_index=rng.choice(candidates))
            for group in range(3) for slot in range(16)]


def write_csv(path, rows):
    with path.open("x", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


def collect(a):
    # Import the tool and the verifier used for the sealed Week 11 stress run.
    sys.path.insert(0, str(a.stress_tool.resolve()))
    from stress import inputs
    vectors, identity, baseline = inputs(a)
    from backend import CacheBackend
    from bench import packet_data
    from evidence import save, seal, sha
    from service import hex_logits, i1
    from shared_queue import Dispatcher

    selected = [v for v in vectors if v["split_point_s"] == SPLIT]
    profile = i1.load_profile(a.session / "source/contracts/sv3_week5_approved_registry_v2.json")
    tensors = {v["vector_index"]: packet_data(a.session / "inputs/packets", v, profile)[3]
               for v in selected}
    plan = trace(list(tensors), a.seed)
    output = a.output
    output.mkdir(parents=True, exist_ok=False)
    write_csv(output / "trace.csv", plan)
    save(output / "config.json", dict(seed=a.seed, split_s=SPLIT, planned_jobs=len(plan),
         scenario="3 deterministic bursts, 16 arrivals per burst, 1 ms spacing, 3 s between bursts",
         duration_ms=plan[-1]["t_arrival_ms"], max_pending_background_jobs=a.max_pending_background_jobs,
         baseline_reference_ms_per_job=REFERENCE_MS_PER_JOB, backend=identity,
         trace_sha256=sha(output / "trace.csv"), parity_sha256=sha(a.baseline / "sha256sum_results.txt")))
    for filename in ("burst.py", "shared_queue.py", "delivery.sha256"):
        shutil.copyfile(Path(__file__).parent / filename, output / filename)

    worker = CacheBackend(a.worker, a.deploy, a.cpu_ops, a.session / "config/backend.json",
                          output / "worker.log")
    dispatch = None
    submitted = []
    try:
        for i in range(20):
            index = selected[i % len(selected)]["vector_index"]
            result = worker.infer(SPLIT, tensors[index])
            if hex_logits(result["logits"]) != baseline[str(index)]["logits_hex_le"]:
                raise ValueError("Warm-up logits differ from sealed parity")
        dispatch = Dispatcher(worker, output, limit=a.max_pending_background_jobs)
        origin = time.monotonic_ns()
        for row in plan:
            planned_ns = origin + row["t_arrival_ms"] * 1000000
            time.sleep(max(0.0, (planned_ns - time.monotonic_ns()) / 1e9))
            index = row["vector_index"]
            job = dispatch.submit(SPLIT, tensors[index], background=True, planned_ns=planned_ns,
                                  context={"vector_index": index})
            if job is not None:
                submitted.append(job)
    finally:
        try:
            if dispatch is not None:
                dispatch.close()
        finally:
            worker.close()
    parity_errors = sum(job["result"] is None or
                        hex_logits(job["result"]["logits"]) != baseline[str(job["vector_index"])]["logits_hex_le"]
                        for job in submitted)
    save(output / "board_result.json", dict(clock_origin_ns=origin, parity_errors=parity_errors,
         worker_returncode=worker.transport.process.returncode,
         scope="KV260_ROOT_CPU_DPU_BACKGROUND_FIFO", warmup_requests=20))
    seal(output)
    print("BURST_CAPTURE_SAVED", output)


def analyze(a):
    sys.path.insert(0, str(a.core.resolve()))
    from evidence import save, seal, sha, verify

    r = a.run
    verify(r)
    config = json.loads((r / "config.json").read_text())
    board = json.loads((r / "board_result.json").read_text())
    queue = json.loads((r / "queue_summary.json").read_text())
    if sha(r / "trace.csv") != config["trace_sha256"]:
        raise ValueError("Trace SHA differs from config")
    with (r / "trace.csv").open() as stream:
        plan = {int(row["job_id"]): row for row in csv.DictReader(stream)}
    events = [json.loads(line) for line in (r / "jobs.jsonl").read_text().splitlines()]
    groups = {kind: {} for kind in ("enqueue", "finished", "drop_capacity")}
    for row in events:
        group = groups[row["event"]]
        job_id = row["job_id"]
        entry = plan[job_id]
        if (job_id in group or row["kind"] != "background" or row["split_s"] != config["split_s"]
                or row["vector_index"] != int(entry["vector_index"])
                or row["planned_ns"] != board["clock_origin_ns"] + int(entry["t_arrival_ms"]) * 1000000):
            raise ValueError("Job ledger differs from the trace")
        group[job_id] = row
    accepted, finished, dropped = (groups[k] for k in ("enqueue", "finished", "drop_capacity"))
    if (set(accepted) & set(dropped) or set(accepted) | set(dropped) != set(plan)
            or set(accepted) != set(finished) or queue["background_arrived"] != len(plan)
            or queue["background_dropped"] != len(dropped) or len(plan) != config["planned_jobs"]):
        raise ValueError("Job inventory or counts differ")
    by_depth = {}
    failed = 0
    for job_id, event in finished.items():
        entry = accepted[job_id]
        expected_wait = (event["start_ns"] - entry["enqueued_ns"]) / 1e6
        if event["enqueued_ns"] != entry["enqueued_ns"] or event["queue_wait_ms"] != expected_wait:
            raise ValueError("Queue timing differs from monotonic timestamps")
        if event["error"] is not None or event["cancelled"]:
            failed += 1
        else:
            by_depth.setdefault(entry["queue_length_jobs"], []).append(expected_wait)
    if queue["completed"] != len(finished) - failed:
        raise ValueError("Completed count differs from job log")
    if not by_depth:
        raise ValueError("No successful jobs to analyze")
    summary_rows = [dict(q=q, samples=len(values), mean_wait_ms=mean(values),
                         p95_wait_ms=sorted(values)[math.ceil(.95 * len(values)) - 1],
                         reference_51_7_ms_per_job=REFERENCE_MS_PER_JOB)
                    for q, values in sorted(by_depth.items())]
    xs = [q for q, values in by_depth.items() for _ in values]
    ys = [value for values in by_depth.values() for value in values]
    x_avg = mean(xs)
    variance = sum((q-x_avg)**2 for q in xs)
    slope = sum((q-x_avg)*wait for q, wait in zip(xs, ys)) / variance if variance else None
    max_q = max(row["queue_length_jobs"] for row in accepted.values())
    passed = (max_q >= 12 and not dropped and not failed and not queue["failure"]
              and board["parity_errors"] == 0 and board["worker_returncode"] == 0
              and board["scope"] == "KV260_ROOT_CPU_DPU_BACKGROUND_FIFO"
              and config["backend"]["backend"] == "KV260_ROOT_CPU_DPU_MODEL_CACHE")
    a.output.mkdir(parents=True, exist_ok=False)
    write_csv(a.output / "wait_by_q.csv", summary_rows)
    save(a.output / "summary.json", dict(workload_pass=passed, scope=board["scope"],
         seed=config["seed"], arrived=len(plan), completed=queue["completed"], dropped=len(dropped),
         failed=failed, parity_errors=board["parity_errors"], q_max=max_q,
         q_definition="Pending jobs after enqueue including the new job; excludes active job",
         worker_returncode=board["worker_returncode"], queue_wait_slope_ms_per_job=slope,
         week10_reference_ms_per_job=REFERENCE_MS_PER_JOB,
         delta_from_reference_ms_per_job=None if slope is None else slope-REFERENCE_MS_PER_JOB,
         source_inventory_sha256=sha(r / "sha256sum_results.txt")))
    seal(a.output)
    print("BURST_WORKLOAD_OK" if passed else "BURST_WORKLOAD_REVIEW_REQUIRED", a.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    run = modes.add_parser("run")
    for field in ("session", "worker", "baseline", "deploy", "cpu-ops", "stress-tool", "output"):
        run.add_argument("--" + field, type=Path, required=True)
    run.add_argument("--seed", type=int, default=11)
    run.add_argument("--max-pending-background-jobs", type=int, default=32, choices=range(1, 65))
    review = modes.add_parser("analyze")
    for field in ("core", "run", "output"):
        review.add_argument("--" + field, type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "run":
        collect(args)
    else:
        analyze(args)


if __name__ == "__main__":
    main()
