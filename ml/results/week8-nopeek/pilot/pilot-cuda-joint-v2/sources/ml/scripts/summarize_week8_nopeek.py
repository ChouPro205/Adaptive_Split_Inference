"""Authenticate completed Week 8 runs and export metrics plus validation curves."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml/src"))
import numpy as np
import torch
from week3_common import need, read_json, sha
from run_week8_nopeek import atomic_json, config_digest


def summarize(experiment, artifacts, output):
    experiment, artifacts, output = (Path(p).resolve() for p in (experiment, artifacts, output))
    need(not output.exists(), "Refuse to overwrite summary evidence")
    identity, config = read_json(experiment / "identity.json"), read_json(experiment / "config.json")
    mode = identity["mode"]
    need(config_digest(config) == identity["config_sha256"], "Experiment config hash differs")
    need(config_digest(read_json(experiment / "selected_samples.json")) == identity["selected_samples_sha256"], "Selected sample IDs changed")
    for relative, digest in identity["source_sha256"].items():
        need(sha(experiment / "sources" / relative) == digest, "Source snapshot changed: " + relative)
    inventory = read_json(experiment / "inventory.json")
    policy = config["pilot"] if mode == "pilot" else config
    expected = {(s, float(l), k) for s in policy["splits"] for l in policy["lambda1"] for k in policy["seeds"]}
    actual = [(row["split"], float(row["lambda1"]), row["seed"]) for row in inventory]
    need(len(actual) == len(expected) and set(actual) == expected, "Missing/duplicate inventory combinations")
    rows, missing = [], []
    for row in inventory:
        run_id = f"s{row['split']}-lambda{row['lambda1']:g}-seed{row['seed']}"
        need(row["run_id"] == run_id, "Invalid run path")
        if row["status"] != "COMPLETED":
            missing.append(row)
            continue
        status = read_json(experiment / run_id / "status.json")
        summary = read_json(experiment / run_id / "summary.json")
        need(status["status"] == summary["status"] == "COMPLETED" and
             status["identity"] == summary["identity"] and
             summary["identity"]["experiment_identity"] == identity, "Run status/identity differs")
        need((summary["split"], float(summary["lambda1"]), summary["seed"]) ==
             (row["split"], float(row["lambda1"]), row["seed"]), "Run combination differs")
        name = f"best-epoch-{summary['best_epoch']:03d}.pt"
        need(summary["best_checkpoint"] == name and sha(artifacts / run_id / name) ==
             summary["checkpoint_sha256"] == row["checkpoint_sha256"], "Checkpoint hash differs")
        checkpoint = torch.load(artifacts / run_id / name, map_location="cpu", weights_only=True)
        history = read_json(experiment / run_id / "history.json")
        need([h["epoch"] for h in history] == list(range(1, summary["epochs_completed"]+1)), "Incomplete epoch history")
        chosen = min(history, key=lambda h: h["validation"]["ce"])
        need(checkpoint["identity"] == summary["identity"] and checkpoint["best"] == summary["validation"] and
             checkpoint["best_epoch"] == summary["best_epoch"] == chosen["epoch"] and
             chosen["validation"] == summary["validation"], "Checkpoint metrics/selection binding differs")
        v = summary["validation"]
        value = {"run_id": run_id, "mode": mode, "split": row["split"], "lambda1": row["lambda1"],
                 "seed": row["seed"], "best_epoch": summary["best_epoch"], "epochs_completed": summary["epochs_completed"],
                 **{k: v[k] for k in ("accuracy", "ce", "dcor", "macro_f1", "samples", "dcor_samples", "batch_size")},
                 "checkpoint_sha256": summary["checkpoint_sha256"], "selected_samples_sha256": identity["selected_samples_sha256"]}
        value.update({f"recall_{c}": v["per_class"][c]["recall"] for c in ("N", "S", "V", "F", "Q")})
        value["confusion_matrix"] = v["confusion_matrix"]
        rows.append(value)
    need(rows, "No completed runs to summarize")
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output / "metrics.json", rows)
    flat = [{k: v for k, v in row.items() if k != "confusion_matrix"} for row in rows]
    with (output / "metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)
    plot_data = []
    for s in policy["splits"]:
        for l in policy["lambda1"]:
            values = [r["accuracy"] for r in rows if r["split"] == s and r["lambda1"] == l]
            if values:
                plot_data.append({"split": s, "lambda1": l, "seeds_completed": len(values),
                                  "accuracy_mean": float(np.mean(values)),
                                  "accuracy_std_sample": float(np.std(values, ddof=1)) if len(values) > 1 else None})
    atomic_json(output / "plot-data.json", plot_data)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), sharey=True)
    for ax, s in zip(axes, policy["splits"]):
        points = [p for p in plot_data if p["split"] == s]
        # Missing combinations remain gaps. A partial/pilot curve cannot impersonate a full grid.
        lookup = {p["lambda1"]: p for p in points}
        xs = policy["lambda1"]
        ys = [lookup[l]["accuracy_mean"] * 100 if l in lookup else np.nan for l in xs]
        errors = [(lookup[l]["accuracy_std_sample"] or 0)*100 if l in lookup else 0 for l in xs]
        ax.errorbar(xs, ys, yerr=errors, marker="o", capsize=3)
        ax.set(title=f"s{s}", xlabel="lambda1", xticks=xs)
        ax.grid(alpha=.3)
    axes[0].set_ylabel("Validation accuracy (%)")
    label = "PILOT - subset validation, not the Week 8 grid" if mode == "pilot" else "Week 8 - frozen validation"
    fig.suptitle(label + f" | {len(rows)}/{len(expected)} runs; {len(policy['seeds'])} seed(s)")
    fig.tight_layout()
    fig.savefig(output / "validation-accuracy-lambda.png", dpi=180)
    fig.savefig(output / "validation-accuracy-lambda.svg")
    plt.close(fig)
    atomic_json(output / "summary.json", {"mode": mode, "completed_runs": len(rows), "expected_runs": len(expected),
                "full_grid_complete": mode == "grid" and not missing, "missing": missing,
                "source_identity": identity, "privacy_claim": "NOT_EVALUATED",
                "dcor_conditions": config["validation_policy"],
                "files": {p.name: sha(p) for p in output.iterdir() if p.is_file()}})
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summarize(args.experiment, args.artifacts, args.output)
