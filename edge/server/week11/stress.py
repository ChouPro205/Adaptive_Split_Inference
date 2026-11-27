"""Stress the existing KV260 model cache and review sealed results off-board."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import random
import shutil
from statistics import median
import sys
import time
import uuid

SPLITS = tuple(range(10))
FULL_SWITCHES = 10_000
WARMUP = 20
SAMPLE_EVERY = 100


def load(path):
    return json.loads(path.read_text())


def core_import(path):
    sys.path.insert(0, str(path.resolve()))


def workload(vectors, seed, switches):
    by_split = {s: [v for v in vectors if v["split_point_s"] == s] for s in SPLITS}
    if not all(by_split.values()):
        raise ValueError("Need authenticated inputs for every native split")
    plan = [("first_load", by_split[s][0]) for s in SPLITS]
    plan += [("warmup", v) for s in SPLITS
             for v in (by_split[s][i % len(by_split[s])] for i in range(WARMUP))]
    rng = random.Random(seed)
    previous = SPLITS[-1]
    for _ in range(switches):
        next_split = rng.randrange(9)
        if next_split >= previous:
            next_split += 1
        plan.append(("random_switch", rng.choice(by_split[next_split])))
        previous = next_split
    return plan


def inputs(a):
    if platform.system() != "Linux" or platform.machine() != "aarch64":
        raise ValueError("Hardware mode requires Linux ARM64 on the KV260")
    core_import(a.session / "source/edge/server/week10")
    from backend import authenticated_backend
    from evidence import package, sha, verify
    from analyze import read_run

    verify(a.session, "sha256sum_prepare.txt")
    vectors = package(a.session / "inputs/packets")
    backend = authenticated_backend(a.worker, a.deploy, a.cpu_ops, a.session / "config/backend.json")
    old, old_summary, old_rows, complete = read_run(a.baseline)
    if (not complete or old["mode"] != "parity" or old["backend"] != backend
            or old_summary["parity_mismatches"] != 0
            or not all(r["baseline_bit_exact"] is True for r in old_rows)
            or old["preparation_inventory_sha256"] != sha(a.session / "sha256sum_prepare.txt")):
        raise ValueError("Need sealed parity for this preparation, worker, models and plugins")
    baseline = load(a.baseline / "baseline.json")
    if set(baseline) != {str(v["vector_index"]) for v in vectors}:
        raise ValueError("Parity has a different vector inventory")
    for v in vectors:
        ref = baseline[str(v["vector_index"])]
        row = old_rows[v["vector_index"]]
        if (ref["split_s"] != v["split_point_s"]
                or ref["logits_hex_le"] != row["logits_hex_le"]):
            raise ValueError("Baseline differs from authenticated vector or sealed parity result")
    return vectors, backend, baseline


def proc_kib(path, keys):
    found = dict.fromkeys(keys)
    try:
        with Path(path).open() as source:
            for line in source:
                key, _, values = line.partition(":")
                if key in found:
                    amount, unit = values.split()
                    if unit != "kB":
                        raise ValueError("Unexpected procfs memory unit")
                    found[key] = int(amount)
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return found
    return found


def memory_sample(pid, phase, switches, start_ns):
    import psutil

    sample = dict(rss_source="psutil", phase=phase, completed_switches=switches,
                  elapsed_s=(time.monotonic_ns() - start_ns) / 1e9)
    for name, process_id in (("worker", pid), ("driver", os.getpid())):
        status = proc_kib(f"/proc/{process_id}/status", ("VmRSS", "VmHWM"))
        rollup = proc_kib(f"/proc/{process_id}/smaps_rollup",
                          ("Pss", "Private_Clean", "Private_Dirty"))
        private = (rollup["Private_Clean"], rollup["Private_Dirty"])
        sample.update({
            f"{name}_rss_kib": psutil.Process(process_id).memory_info().rss // 1024, f"{name}_peak_rss_kib": status["VmHWM"],
            f"{name}_pss_kib": rollup["Pss"],
            f"{name}_private_kib": None if None in private else sum(private),
        })
    system = proc_kib("/proc/meminfo", ("MemAvailable", "CmaFree", "SwapFree"))
    sample.update({f"{key}_kib": value for key, value in system.items()})
    return sample


def run(a):
    vectors, identity, baseline = inputs(a)
    from backend import CacheBackend
    from bench import packet_data
    from evidence import PACKAGE_SHA, save, seal, sha
    from service import Receiver, i1

    plan = workload(vectors, a.seed, a.switches)
    packet_dir = a.session / "inputs/packets"
    profile = i1.load_profile(a.session / "source/contracts/sv3_week5_approved_registry_v2.json")
    decoded = {v["vector_index"]: packet_data(packet_dir, v, profile)[1:3] for v in vectors}
    a.output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, a.output / "stress.py")
    shutil.copyfile(a.baseline / "baseline.json", a.output / "baseline.json")
    run_id = a.output.name + "-" + uuid.uuid4().hex[:12]
    save(a.output / "plan.json", [
        dict(phase=phase, split_s=v["split_point_s"], vector_index=v["vector_index"])
        for phase, v in plan
    ])
    save(a.output / "run.json", {
        "mode": "stress", "run_id": run_id, "seed": a.seed,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "OFFLINE_I1_KV260_ROOT_CPU_DPU",
        "switches": a.switches, "warmup_per_split": WARMUP, "memory_every_switches": SAMPLE_EVERY,
        "source_commit": a.source_commit,
        "python": sys.version, "uname": list(platform.uname()), "backend": identity,
        "packet_manifest_sha256": PACKAGE_SHA,
        "parity_inventory_sha256": sha(a.baseline / "sha256sum_results.txt"),
        "preparation_inventory_sha256": sha(a.session / "sha256sum_prepare.txt"),
        "plan_sha256": sha(a.output / "plan.json"),
    })
    worker = None
    rows = mismatches = switches_done = 0
    error = returncode = pid = None
    started = time.monotonic_ns()

    try:
        with (a.output / "requests.jsonl").open("x", buffering=1) as raw, \
                (a.output / "memory.jsonl").open("x", buffering=1) as memory:
            worker = CacheBackend(a.worker, a.deploy, a.cpu_ops, a.session / "config/backend.json",
                                  a.output / "worker.log")
            pid = worker.transport.process.pid
            receiver = Receiver(worker)

            def sample(phase):
                entry = memory_sample(pid, phase, switches_done, started)
                memory.write(json.dumps(entry, allow_nan=False) + "\n")
                if entry["worker_rss_kib"] is None or entry["driver_rss_kib"] is None:
                    raise RuntimeError("Missing RSS for worker or driver")
                print("RAM", phase, f"switches={switches_done}",
                      f"worker={entry['worker_rss_kib']} KiB driver={entry['driver_rss_kib']} KiB",
                      flush=True)

            print(f"STRESS_READY worker_pid={pid} run={a.output}", flush=True)
            sample("before_load")
            for index, (phase, vector) in enumerate(plan):
                v = vector["vector_index"]
                s = vector["split_point_s"]
                req, q = decoded[v]
                packet = i1.encode_request(index + 1, req.model_profile_id, req.split.split_id,
                                           req.split.channels, req.split.length, req.scales, q)
                _, row = receiver.handle("OFFLINE_WEEK11", packet, time.monotonic_ns() / 1e6)
                bit_exact = row["logits_hex_le"] == baseline[str(v)]["logits_hex_le"]
                reported_split = row["split_s"]
                row.update(index=index, phase=phase, run_id=run_id, vector_index=v, split_s=s,
                           reported_split_s=reported_split,
                           model_sha256=identity["models"][str(s)], baseline_bit_exact=bit_exact)
                raw.write(json.dumps(row, allow_nan=False) + "\n")
                rows += 1
                mismatches += not bit_exact
                if (row["result"] != "OK" or not bit_exact or row["response_cache_hit"]
                        or reported_split != s or row.get("worker_pid") != pid):
                    raise RuntimeError(f"Request {index + 1} failed; inspect preserved row")
                if phase == "random_switch":
                    if row["previous_s"] == s or not row["model_cache_hit"] or row["contexts_count"] != 10:
                        raise RuntimeError(f"Invalid native switch at request {index + 1}")
                    switches_done += 1
                    if switches_done % SAMPLE_EVERY == 0:
                        sample("random_switch")
                elif index == len(SPLITS) - 1:
                    sample("after_load")
                elif index == len(SPLITS) * (1 + WARMUP) - 1:
                    sample("after_warmup")
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if worker is not None:
            try:
                worker.close()
                returncode = worker.transport.process.returncode
                if returncode != 0 and error is None:
                    error = f"Native shutdown returned {returncode}"
            except BaseException as exc:
                if error is None:
                    error = f"Worker cleanup: {type(exc).__name__}: {exc}"
        save(a.output / "summary.json", {
            "status": "INCOMPLETE" if error else "EXECUTION_COMPLETE_NUMERIC_REVIEW_PENDING",
            "run_id": run_id, "rows": rows, "planned": len(plan),
            "parity_mismatches": mismatches, "error": error,
            "completed_switches": switches_done, "worker_pid": pid, "worker_returncode": returncode,
        })
        seal(a.output)
    if error:
        raise RuntimeError(error)
    print("STRESS_SAVED_REVIEW_REQUIRED", a.output)


def analyze(a):
    core_import(a.core)
    from analyze import read_run, stats
    from evidence import save, seal, sha

    meta, summary, rows, complete = read_run(a.run)
    plan = load(a.run / "plan.json")
    baseline = load(a.run / "baseline.json")
    vectors = [dict(vector_index=int(idx), split_point_s=ref["split_s"])
               for idx, ref in sorted(baseline.items(), key=lambda pair: int(pair[0]))]
    expected = workload(vectors, meta["seed"], meta["switches"])
    if (meta["mode"] != "stress" or meta["switches"] not in (100, FULL_SWITCHES)
            or plan != [dict(phase=phase, split_s=v["split_point_s"], vector_index=v["vector_index"])
                        for phase, v in expected]):
        raise ValueError("Saved workload differs from seed or configuration")
    memory = [json.loads(line) for line in (a.run / "memory.jsonl").read_text().splitlines()]
    for r in rows:
        if r["result"] == "OK" and (r["worker_pid"] != summary["worker_pid"]
                or r["request_id"] != r["index"] + 1 or r["rho"] != "P0"
                or r["reported_split_s"] != r["split_s"]
                or r["baseline_bit_exact"] != (
                    r["logits_hex_le"] == baseline[str(r["vector_index"])]["logits_hex_le"])):
            raise ValueError("Request does not match worker, request sequence or baseline")
    switches = [r for r in rows if r["phase"] == "random_switch" and r["result"] == "OK"
                and r["baseline_bit_exact"] and r["previous_s"] != r["split_s"]
                and r["model_cache_hit"] and r["contexts_count"] == 10]
    pairs = {(r["previous_s"], r["split_s"]) for r in switches}
    expected_samples = [("before_load", 0), ("after_load", 0), ("after_warmup", 0)]
    expected_samples += [("random_switch", i)
                         for i in range(SAMPLE_EVERY, meta["switches"] + 1, SAMPLE_EVERY)]
    observed_samples = [(r["phase"], r["completed_switches"]) for r in memory]
    sampled = (observed_samples == expected_samples and
               all(isinstance(r[k], int) and r[k] > 0 for r in memory
                   for k in ("worker_rss_kib", "driver_rss_kib")) and
               all(x["elapsed_s"] <= y["elapsed_s"] for x, y in zip(memory, memory[1:])))
    complete = bool(complete and sampled and summary["worker_returncode"] == 0
                    and not summary["parity_mismatches"]
                    and len(switches) == summary["completed_switches"] == meta["switches"])
    warm = [r for r in memory if r["phase"] in ("after_warmup", "random_switch")]
    # Compare equal quarters of the random-switch interval. No leak threshold is assumed.
    windows = []
    for block in range(4):
        lower, upper = meta["switches"] * block / 4, meta["switches"] * (block + 1) / 4
        group = [r for r in warm if lower < r["completed_switches"] <= upper]
        if group:
            windows.append(dict(from_exclusive=lower, to_inclusive=upper, sample_count=len(group),
                                worker_rss_median_kib=median(r["worker_rss_kib"] for r in group)
                                if all(r["worker_rss_kib"] is not None for r in group) else None,
                                driver_rss_median_kib=median(r["driver_rss_kib"] for r in group)
                                if all(r["driver_rss_kib"] is not None for r in group) else None))
    memory_stats = {}
    if warm:
        for field in ("worker_rss_kib", "driver_rss_kib", "worker_private_kib",
                      "driver_private_kib", "MemAvailable_kib", "CmaFree_kib", "SwapFree_kib"):
            vals = [r[field] for r in warm]
            if None not in vals:
                memory_stats[field] = dict(start=vals[0], end=vals[-1], min=min(vals),
                                           max=max(vals), end_minus_start=vals[-1] - vals[0])
    slopes = {}
    if len(warm) >= 2:
        x = [r["completed_switches"] / 1000 for r in warm]
        center = sum(x) / len(x)
        variance = sum((value - center) ** 2 for value in x)
        for name in ("worker_rss_kib", "driver_rss_kib"):
            if variance and all(r.get(name) is not None for r in warm):
                # Convert Linux KiB to decimal KB before reporting KB per 1000 switches.
                slopes[name] = sum((v - center) * r[name] * 1.024 for v, r in zip(x, warm)) / variance
    tail_stats = stats([r["tail_ms"] for r in switches])
    tail_stats.pop("at_or_above_50_count")
    report = dict(run_id=meta["run_id"], execution_complete=complete, scope=meta["scope"],
                  full_workload=meta["switches"] == FULL_SWITCHES, seed=meta["seed"],
                  planned_switches=meta["switches"], validated_switches=len(switches),
                  request_rows=len(rows), directed_pairs=len(pairs), max_directed_pairs=90,
                  worker_pid=summary["worker_pid"], worker_returncode=summary["worker_returncode"],
                  parity_mismatches=summary["parity_mismatches"], error=summary["error"],
                  memory_samples=len(memory), memory_samples_complete=sampled, memory_stats=memory_stats,
                  rss_slope_KB_per_1000=slopes,
                  rss_source=sorted({r.get("rss_source", "procfs") for r in memory}),
                  observed_elapsed_s=memory[-1]["elapsed_s"] if memory else None,
                  memory_review="PENDING_OBSERVED_TREND_REVIEW", acceptance="PENDING",
                  quarter_medians=windows, switch=stats([r["switch_ms"] for r in switches]),
                  tail=tail_stats,
                  source_commit=meta["source_commit"], backend=meta["backend"],
                  source_inventory_sha256=sha(a.run / "sha256sum_results.txt"))
    a.output.mkdir(parents=True, exist_ok=False)
    save(a.output / "summary.json", report)
    for name, records in (("memory", memory), ("switches", switches)):
        fields = (list(memory[0]) if name == "memory" and memory else
                  ["index", "previous_s", "split_s", "switch_ms", "tail_ms"] if name == "switches" else
                  ["phase", "completed_switches", "elapsed_s", "worker_rss_kib", "driver_rss_kib"])
        with (a.output / f"{name}.csv").open("x", newline="") as target:
            csv_writer = csv.DictWriter(target, fieldnames=fields, extrasaction="ignore")
            csv_writer.writeheader()
            csv_writer.writerows(records)
    seal(a.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("STRESS_ANALYSIS_SAVED", a.output)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_subparsers(dest="mode", required=True)
    for mode in ("probe", "run"):
        cmd = modes.add_parser(mode)
        for name in ("session", "worker", "deploy", "cpu-ops", "baseline"):
            cmd.add_argument(f"--{name}", type=Path, required=True)
        if mode == "run":
            cmd.add_argument("--seed", type=int, default=11)
            cmd.add_argument("--switches", type=int, choices=(100, FULL_SWITCHES), default=FULL_SWITCHES)
            cmd.add_argument("--source-commit", required=True)
            cmd.add_argument("--output", type=Path, required=True)
    cmd = modes.add_parser("analyze")
    for name in ("run", "core", "output"):
        cmd.add_argument(f"--{name}", type=Path, required=True)
    a = p.parse_args()
    if a.mode == "probe":
        vectors, identity, _ = inputs(a)
        print("BOARD_INPUTS_OK", len(vectors), identity["worker_sha256"])
    elif a.mode == "run":
        run(a)
    else:
        analyze(a)


if __name__ == "__main__":
    main()
