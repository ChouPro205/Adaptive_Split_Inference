"""Authenticate the complete joint NoPeek grid, aggregate seeds, lock candidates."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import math
from pathlib import Path, PurePosixPath

import numpy as np
import torch

from run_week8_nopeek import ROOT, CLASSES, atomic_json, config_digest, validate_config
from week3_common import CHECKPOINT, need, read_json, sha

SEEDS = [20261021, 20261022, 20261023]
SPLITS = [2, 5, 8]
LAMBDAS = [0, 0.1, 0.5, 1, 2, 5]
VAL_SUPPORT = [13003, 1493, 876, 11, 5]
METRICS = ["accuracy", "ce", "dcor", "macro_f1"] + [f"recall_{c}" for c in CLASSES]


def member(root, name):
    need(isinstance(name, str) and name and "\\" not in name and ":" not in name and
         not PurePosixPath(name).is_absolute() and all(p not in ("", ".", "..") for p in name.split("/")),
         "Unsafe evidence member")
    target = (root / name).resolve()
    need(root.resolve() in target.parents and target.is_file(), "Missing evidence member: " + name)
    return target


def relative(path, fallback_root):
    path = path.resolve()
    if path.is_relative_to(ROOT):
        return path.relative_to(ROOT).as_posix(), "repo_root"
    return path.relative_to(fallback_root.resolve()).as_posix(), "supplied_artifacts_root"


def validate_rule(rule):
    need(rule["schema_version"] == 1 and rule["status"] == "LOCKED_IMPLEMENTATION_RULE_BEFORE_GRID_COMPLETION" and
         rule["seeds"] == SEEDS and rule["requires_complete_grid"] is True and
         rule["lambda_selection_within_split"] == "Smallest arithmetic mean validation CE of the three independently selected seed checkpoints" and
         rule["lambda_tie_break"] == "Smaller lambda1" and
         rule["cross_split_optimization"] == "OUT_OF_SCOPE; keep separate s2/s5/s8 candidates" and
         rule["deployment_status"] == "EXPERIMENT_ONLY_NOT_APPROVED", "Candidate rule differs")


def validate_validation(value):
    need(value["samples"] == value["dcor_samples"] == 15388 and value["batch_size"] == 32,
         "Validation samples/batch differ")
    for key in ("accuracy", "ce", "dcor", "macro_f1"):
        need(type(value[key]) in (int, float) and math.isfinite(value[key]) and value[key] >= 0,
             "Invalid validation metric: " + key)
    need(all(value[k] <= 1 for k in ("accuracy", "dcor", "macro_f1")), "Metric outside [0,1]")
    matrix = np.asarray(value["confusion_matrix"])
    need(matrix.shape == (5, 5) and np.issubdtype(matrix.dtype, np.integer) and
         bool((matrix >= 0).all()) and matrix.sum(1).tolist() == VAL_SUPPORT,
         "Confusion matrix/support differs from full validation")
    tp, support, predicted = matrix.diagonal(), matrix.sum(1), matrix.sum(0)
    precision = np.divide(tp, predicted, out=np.zeros(5), where=predicted != 0)
    recall = tp / support
    f1 = np.divide(2*precision*recall, precision+recall, out=np.zeros(5), where=precision+recall != 0)
    need(math.isclose(value["accuracy"], float(tp.sum()/15388), abs_tol=1e-12, rel_tol=0) and
         math.isclose(value["macro_f1"], float(f1.mean()), abs_tol=1e-12, rel_tol=0),
         "Accuracy/F1 differs from confusion matrix")
    for i, name in enumerate(CLASSES):
        item = value["per_class"][name]
        need(item["support"] == int(support[i]) and
             math.isclose(item["recall"], float(recall[i]), abs_tol=1e-12, rel_tol=0),
             "Per-class support/recall differs")


def expected_export(summary, identity):
    v = summary["validation"]
    result = {"run_id": summary["run_id"], "mode": "grid", "split": summary["split"],
              "lambda1": summary["lambda1"], "seed": summary["seed"], "best_epoch": summary["best_epoch"],
              "epochs_completed": summary["epochs_completed"],
              **{k: v[k] for k in ("accuracy", "ce", "dcor", "macro_f1", "samples", "dcor_samples", "batch_size")},
              "checkpoint_sha256": summary["checkpoint_sha256"],
              "selected_samples_sha256": identity["selected_samples_sha256"],
              "confusion_matrix": v["confusion_matrix"]}
    result.update({f"recall_{c}": v["per_class"][c]["recall"] for c in CLASSES})
    return result


def authenticate(experiment, artifacts):
    config = read_json(experiment / "config.json")
    validate_config(config, "grid")
    need(config["seeds"] == SEEDS and config["train_scope"] == "head_and_tail" and
         config["device"] == "cuda" and config["batch_size"] == 32 and
         config["training_policy"]["max_epochs"] == 30 and config["training_policy"]["early_stopping_patience"] == 5,
         "Approved joint grid config differs")
    identity = read_json(experiment / "identity.json")
    need(identity["mode"] == "grid" and config_digest(config) == identity["config_sha256"], "Config/identity binding differs")
    for path, digest in identity["source_sha256"].items():
        need(sha(member(experiment / "sources", path)) == digest, "Training source snapshot changed")
    selected = read_json(experiment / "selected_samples.json")
    need(set(selected) == {"train", "val"} and config_digest(selected) == identity["selected_samples_sha256"],
         "Selected data IDs changed")
    sets, patients = {}, {}
    for split, count in (("train", 81094), ("val", 15388)):
        entries = selected[split]
        sets[split] = {s["sample_id"] for s in entries}
        patients[split] = {s["patient_id"] for s in entries}
        need(len(entries) == len(sets[split]) == count and [s["row_index"] for s in entries] == list(range(count)),
             "Full frozen sample inventory differs: " + split)
    need(not sets["train"] & sets["val"] and not patients["train"] & patients["val"], "Data leakage")
    need(np.bincount([s["class_index"] for s in selected["val"]], minlength=5).tolist() == VAL_SUPPORT,
         "Full validation class IDs differ")
    audit = read_json(experiment / "data-audit.json")
    need(audit["test_arrays_opened"] is False and audit["normalization_fit"] == "train" and
         audit["bindings"] == identity["dataset"] and audit["splits"]["val"]["class_counts"] == VAL_SUPPORT,
         "Data audit/test policy differs")
    for split in ("train", "val"):
        need(audit["splits"][split]["samples"] == len(selected[split]) and
             set(audit["splits"][split]["patients"]) == patients[split], "Audit patient binding differs")
    inventory = read_json(experiment / "inventory.json")
    expected = {f"s{s}-lambda{l:g}-seed{k}": (s, l, k) for s in SPLITS for l in LAMBDAS for k in SEEDS}
    need(len(inventory) == 54 and len({r["run_id"] for r in inventory}) == 54 and
         {r["run_id"] for r in inventory} == set(expected), "Incomplete/duplicate grid inventory")
    root_status = read_json(experiment / "status.json")
    need(root_status["status"] == "COMPLETED" and root_status["expected_runs"] == root_status["completed_runs"] == 54,
         "Grid not completed")
    analysis = experiment / "analysis"
    exported = read_json(analysis / "summary.json")
    need(exported["mode"] == "grid" and exported["full_grid_complete"] is True and
         exported["completed_runs"] == exported["expected_runs"] == 54 and exported["missing"] == [] and
         exported["source_identity"] == identity, "Exporter is incomplete or identity differs")
    required = {"metrics.json", "metrics.csv", "plot-data.json", "validation-accuracy-lambda.png", "validation-accuracy-lambda.svg"}
    need(required.issubset(exported["files"]), "Exporter file inventory incomplete")
    for path, digest in exported["files"].items():
        need(sha(member(analysis, path)) == digest, "Exported file hash differs: " + path)
    exported_rows = read_json(analysis / "metrics.json")
    need(len(exported_rows) == 54 and len({r["run_id"] for r in exported_rows}) == 54, "Exporter duplicate/missing rows")
    by_id = {r["run_id"]: r for r in exported_rows}
    records = []
    for row in inventory:
        run_id = row["run_id"]
        need(row["status"] == "COMPLETED" and (row["split"], row["lambda1"], row["seed"]) == expected[run_id],
             "Incomplete or changed run")
        summary = read_json(experiment / run_id / "summary.json")
        status = read_json(experiment / run_id / "status.json")
        run_identity = summary["identity"]
        need(summary["status"] == status["status"] == "COMPLETED" and status["identity"] == run_identity and
             run_identity["experiment_identity"] == identity and summary["run_id"] == run_id and
             (summary["split"], summary["lambda1"], summary["seed"]) == expected[run_id] and
             (run_identity["split"], run_identity["lambda1"], run_identity["seed"]) == expected[run_id] and
             run_identity["initial_checkpoint_sha256"] == CHECKPOINT, "Run identity differs")
        name = f"best-epoch-{summary['best_epoch']:03d}.pt"
        need(summary["best_checkpoint"] == name, "Invalid selected checkpoint path")
        checkpoint_path = member(artifacts / run_id, name)
        need(sha(checkpoint_path) == summary["checkpoint_sha256"] == row["checkpoint_sha256"], "Checkpoint hash differs")
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        history = read_json(experiment / run_id / "history.json")
        need(1 <= summary["epochs_completed"] <= 30 and [h["epoch"] for h in history] ==
             list(range(1, summary["epochs_completed"]+1)), "Epoch history incomplete")
        need(all(math.isfinite(h["validation"]["ce"]) and h["validation"]["ce"] >= 0 for h in history), "Invalid history CE")
        chosen = min(history, key=lambda h: h["validation"]["ce"])
        need(checkpoint["identity"] == run_identity and checkpoint["best"] == summary["validation"] == chosen["validation"] and
             checkpoint["best_epoch"] == summary["best_epoch"] == checkpoint["epoch"] == chosen["epoch"] and
             checkpoint["history"] == history[:chosen["epoch"]], "Checkpoint metrics/selection differs")
        need(summary["reload_validation_exact"] is True and summary["deployment_status"] ==
             checkpoint["deployment_status"] == "EXPERIMENT_ONLY_NOT_APPROVED", "Run approval/reload status differs")
        validate_validation(summary["validation"])
        need(by_id.get(run_id) == expected_export(summary, identity), "Exported metrics differ from selected checkpoint")
        checkpoint_reference, base = relative(checkpoint_path, artifacts)
        records.append({"split": row["split"], "lambda1": row["lambda1"], "seed": row["seed"], "run_id": run_id,
                        "best_epoch": summary["best_epoch"], "epochs_completed": summary["epochs_completed"],
                        "checkpoint_path": checkpoint_reference, "checkpoint_path_base": base,
                        "checkpoint_sha256": summary["checkpoint_sha256"], "validation": summary["validation"],
                        "summary_sha256": sha(experiment / run_id / "summary.json"),
                        "history_sha256": sha(experiment / run_id / "history.json")})
    with (analysis / "metrics.csv").open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    need(len(csv_rows) == 54 and len({r.get("run_id") for r in csv_rows}) == 54, "Exported CSV rows differ")
    for row in csv_rows:
        expected_row = by_id.get(row["run_id"])
        need(expected_row is not None and row == {k: str(v) for k, v in expected_row.items() if k != "confusion_matrix"},
             "Exported CSV metrics differ from checkpoint-bound JSON")
    expected_plot = []
    for s in SPLITS:
        for l in LAMBDAS:
            values = [r["validation"]["accuracy"] for r in records if r["split"] == s and r["lambda1"] == l]
            expected_plot.append({"split": s, "lambda1": l, "seeds_completed": 3,
                                  "accuracy_mean": float(np.mean(values)), "accuracy_std_sample": float(np.std(values, ddof=1))})
    need(read_json(analysis / "plot-data.json") == expected_plot, "Exporter plot data differs from checkpoint metrics")
    return config, identity, audit, records


def aggregate(records):
    rows = []
    for split in SPLITS:
        for lambda1 in LAMBDAS:
            group = sorted((r for r in records if r["split"] == split and r["lambda1"] == lambda1), key=lambda r: r["seed"])
            need([r["seed"] for r in group] == SEEDS, "Missing/duplicate seed in aggregation")
            row = {"split": split, "lambda1": lambda1, "seeds": SEEDS, "seed_count": 3,
                   "validation_samples_per_seed": 15388}
            for metric in METRICS:
                values = [r["validation"]["per_class"][metric[7:]]["recall"] if metric.startswith("recall_")
                          else r["validation"][metric] for r in group]
                row[metric + "_mean"] = float(np.mean(values))
                row[metric + "_std_sample"] = float(np.std(values, ddof=1))
            rows.append(row)
    return rows


def candidates(aggregates, records):
    result = []
    for split in SPLITS:
        chosen = min((r for r in aggregates if r["split"] == split), key=lambda r: (r["ce_mean"], r["lambda1"]))
        seeds = sorted((r for r in records if r["split"] == split and r["lambda1"] == chosen["lambda1"]), key=lambda r: r["seed"])
        result.append({"split": split, "lambda1": chosen["lambda1"], "mean_validation_ce": chosen["ce_mean"],
                       "seeds": [{k: r[k] for k in ("seed", "run_id", "best_epoch", "checkpoint_path", "checkpoint_path_base",
                                                     "checkpoint_sha256", "validation", "summary_sha256", "history_sha256")} for r in seeds]})
    return result


def write_csv(path, rows):
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def analyze(experiment, artifacts, rule_path, output):
    experiment, artifacts, rule_path, output = (Path(p).resolve() for p in (experiment, artifacts, rule_path, output))
    need(not output.exists(), "Refuse to overwrite grid analysis")
    rule = read_json(rule_path)
    validate_rule(rule)
    config, identity, audit, records = authenticate(experiment, artifacts)
    aggregates = aggregate(records)
    chosen = candidates(aggregates, records)
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output / "aggregate-metrics.json", aggregates)
    write_csv(output / "aggregate-metrics.csv", [{k: v for k, v in r.items() if k != "seeds"} for r in aggregates])
    atomic_json(output / "per-seed-metrics.json", records)
    flat = []
    for record in records:
        v = record["validation"]
        row = {k: record[k] for k in ("split", "lambda1", "seed", "run_id", "best_epoch", "checkpoint_path", "checkpoint_sha256")}
        row.update({k: v[k] for k in ("samples", "accuracy", "ce", "dcor", "macro_f1")})
        for c in CLASSES:
            row["support_"+c], row["recall_"+c] = v["per_class"][c]["support"], v["per_class"][c]["recall"]
        flat.append(row)
    write_csv(output / "per-seed-metrics.csv", flat)
    rule_reference = rule_path.relative_to(ROOT).as_posix() if rule_path.is_relative_to(ROOT) else "supplied_rule"
    experiment_reference = experiment.relative_to(ROOT).as_posix() if experiment.is_relative_to(ROOT) else "supplied_experiment"
    atomic_json(output / "candidate-lock.json", {
        "schema_version": 1, "status": "CANDIDATES_LOCKED_VALIDATION_ONLY", "locked_at_utc": datetime.now(timezone.utc).isoformat(),
        "expected_runs": 54, "completed_runs": 54, "seeds": SEEDS,
        "validation": {"samples": 15388, "selected_samples_sha256": identity["selected_samples_sha256"],
                       "patients": audit["splits"]["val"]["patients"], "per_class_support": VAL_SUPPORT},
        "config": {"sha256": identity["config_sha256"], "file_sha256": sha(experiment / "config.json"),
                   "protocol_id": config["protocol_id"], "approval_scope": config["approval"].get("scope")},
        "source": {"training_git_head": identity["git_head"], "training_source_sha256": identity["source_sha256"],
                   "analysis_source_sha256": sha(Path(__file__)), "analysis_tests_sha256": sha(Path(__file__).with_name("test_week8_grid_analysis.py"))},
        "data": {"dataset_bindings": identity["dataset"], "selected_samples_sha256": identity["selected_samples_sha256"]},
        "rule": {"path": rule_reference, "sha256": sha(rule_path)},
        "experiment": {"path": experiment_reference, "identity_sha256": sha(experiment / "identity.json"),
                       "inventory_sha256": sha(experiment / "inventory.json"), "analysis_summary_sha256": sha(experiment / "analysis/summary.json")},
        "candidates": chosen, "deployment_status": "EXPERIMENT_ONLY_NOT_APPROVED",
        "test_status": "NOT_READ_BY_CANDIDATE_SELECTION", "cross_split_optimization": "OUT_OF_SCOPE",
        "variation": "Sample standard deviation across seeds (ddof=1), not patient-cohort uncertainty"})
    atomic_json(output / "summary.json", {"status": "PASS_COMPLETE_GRID_ANALYSIS", "completed_runs": 54,
                "aggregate_rows": 18, "candidates": 3, "checkpoints_per_candidate": 3,
                "files": {p.name: sha(p) for p in output.iterdir() if p.is_file()}})
    return chosen


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--rule", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    analyze(args.experiment, args.artifacts, args.rule, args.output)
