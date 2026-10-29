"""CPU-only synthetic evidence checks for complete-grid aggregation and locking."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np
import torch

import analyze_week8_grid as analysis
from run_week8_nopeek import config_digest
from week3_common import CHECKPOINT, read_json, sha


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False) + "\n", encoding="utf-8")


def fixture(root):
    experiment, artifacts = root / "experiment", root / "artifacts"
    config = read_json(analysis.ROOT / "ml/configs/week8_nopeek_approved_3seed_joint_v1.json")
    rule = read_json(analysis.ROOT / "ml/provenance/week8-grid-20261029/candidate-selection-rule.json")
    write(root / "rule.json", rule)
    write(experiment / "config.json", config)
    source = experiment / "sources/synthetic.py"
    source.parent.mkdir(parents=True)
    source.write_text("# Synthetic source fixture\n", encoding="utf-8")
    labels = np.repeat(np.arange(5), analysis.VAL_SUPPORT).tolist()
    selected = {
        "train": [{"row_index": i, "sample_id": f"train:{i}", "patient_id": "train-patient", "class_index": 0} for i in range(81094)],
        "val": [{"row_index": i, "sample_id": f"val:{i}", "patient_id": "val-patient", "class_index": c} for i, c in enumerate(labels)]}
    write(experiment / "selected_samples.json", selected)
    identity = {"git_head": "a"*40, "mode": "grid", "source_sha256": {"synthetic.py": sha(source)},
                "config_sha256": config_digest(config), "selected_samples_sha256": config_digest(selected),
                "dataset": {"patient_manifest_sha256": "b"*64}}
    write(experiment / "identity.json", identity)
    write(experiment / "data-audit.json", {"test_arrays_opened": False, "normalization_fit": "train", "bindings": identity["dataset"],
          "splits": {"train": {"samples": 81094, "patients": ["train-patient"], "class_counts": [81094, 0, 0, 0, 0]},
                     "val": {"samples": 15388, "patients": ["val-patient"], "class_counts": analysis.VAL_SUPPORT}}})
    matrix = np.zeros((5, 5), dtype=np.int64)
    matrix[:, 0] = analysis.VAL_SUPPORT
    precision = analysis.VAL_SUPPORT[0]/15388
    f1 = 2*precision/(precision+1)/5
    inventory, exports = [], []
    for s in analysis.SPLITS:
        for l_index, l in enumerate(analysis.LAMBDAS):
            for index, seed in enumerate(analysis.SEEDS):
                run_id = f"s{s}-lambda{l:g}-seed{seed}"
                run_identity = {"experiment_identity": identity, "split": s, "lambda1": l, "seed": seed,
                                "initial_checkpoint_sha256": CHECKPOINT, "initial_state_sha256": "c"*64}
                value = {"accuracy": precision, "ce": [0.3, 0.2, 0.2, 0.4, 0.5, 0.6][l_index] + index*.01,
                         "dcor": .4 + index*.1, "macro_f1": f1, "samples": 15388, "dcor_samples": 15388, "batch_size": 32,
                         "confusion_matrix": matrix.tolist(), "per_class": {c: {"support": analysis.VAL_SUPPORT[i], "recall": float(i == 0)}
                                                                            for i, c in enumerate(analysis.CLASSES)}}
                history = [{"epoch": 1, "validation": value, "selected": True, "seconds": 0.1}]
                checkpoint = {"identity": run_identity, "best": value, "best_epoch": 1, "epoch": 1, "history": history,
                              "state_dict": {"synthetic_weight": torch.tensor([index])}, "deployment_status": "EXPERIMENT_ONLY_NOT_APPROVED"}
                target = artifacts / run_id / "best-epoch-001.pt"
                target.parent.mkdir(parents=True)
                torch.save(checkpoint, target)
                summary = {"status": "COMPLETED", "identity": run_identity, "run_id": run_id, "split": s, "lambda1": l,
                           "seed": seed, "best_epoch": 1, "epochs_completed": 1, "best_checkpoint": target.name,
                           "checkpoint_sha256": sha(target), "validation": value, "reload_validation_exact": True,
                           "deployment_status": "EXPERIMENT_ONLY_NOT_APPROVED"}
                write(experiment / run_id / "summary.json", summary)
                write(experiment / run_id / "status.json", {"status": "COMPLETED", "identity": run_identity})
                write(experiment / run_id / "history.json", history)
                inventory.append({"status": "COMPLETED", "run_id": run_id, "split": s, "lambda1": l, "seed": seed,
                                  "checkpoint_sha256": sha(target)})
                exports.append(analysis.expected_export(summary, identity))
    write(experiment / "inventory.json", inventory)
    write(experiment / "status.json", {"status": "COMPLETED", "expected_runs": 54, "completed_runs": 54})
    write(experiment / "analysis/metrics.json", exports)
    flat = [{k: v for k, v in row.items() if k != "confusion_matrix"} for row in exports]
    with (experiment / "analysis/metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)
    write(experiment / "analysis/plot-data.json", [
        {"split": s, "lambda1": l, "seeds_completed": 3,
         "accuracy_mean": float(np.mean([precision]*3)),
         "accuracy_std_sample": float(np.std([precision]*3, ddof=1))}
        for s in analysis.SPLITS for l in analysis.LAMBDAS])
    # Image bytes are opaque evidence; authentication binds their bytes.
    for name in ("validation-accuracy-lambda.png", "validation-accuracy-lambda.svg"):
        (experiment / "analysis" / name).write_bytes(b"synthetic-exporter-fixture\n")
    write(experiment / "analysis/summary.json", {"mode": "grid", "full_grid_complete": True, "completed_runs": 54,
          "expected_runs": 54, "missing": [], "source_identity": identity,
          "files": {p.name: sha(p) for p in (experiment / "analysis").iterdir() if p.is_file()}})


class GridAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.base_temp.name)
        fixture(cls.base)

    @classmethod
    def tearDownClass(cls):
        cls.base_temp.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "copy"
        shutil.copytree(self.base, self.root)
        self.experiment, self.artifacts = self.root / "experiment", self.root / "artifacts"
        self.output = self.root / "output"

    def run_analysis(self):
        return analysis.analyze(self.experiment, self.artifacts, self.root / "rule.json", self.output)

    def modify(self, path, fn):
        target = self.root / path
        value = read_json(target)
        fn(value)
        write(target, value)

    def test_complete_grid_exports_sample_std_and_all_seed_candidates_without_pooling(self):
        selected = self.run_analysis()
        rows = read_json(self.output / "aggregate-metrics.json")
        self.assertEqual(len(rows), 18)
        self.assertAlmostEqual(rows[0]["ce_std_sample"], .01)
        self.assertAlmostEqual(rows[0]["dcor_std_sample"], .1)
        self.assertEqual(rows[0]["validation_samples_per_seed"], 15388)
        self.assertEqual([r["lambda1"] for r in selected], [.1, .1, .1])
        self.assertTrue(all([s["seed"] for s in r["seeds"]] == analysis.SEEDS for r in selected))
        records = read_json(self.output / "per-seed-metrics.json")
        self.assertEqual(len(records), 54)
        self.assertTrue(all(sum(map(sum, r["validation"]["confusion_matrix"])) == 15388 for r in records))
        lock = read_json(self.output / "candidate-lock.json")
        self.assertEqual(lock["deployment_status"], "EXPERIMENT_ONLY_NOT_APPROVED")
        self.assertEqual(lock["test_status"], "NOT_READ_BY_CANDIDATE_SELECTION")
        self.assertEqual(lock["rule"]["sha256"], sha(self.root / "rule.json"))
        self.assertEqual(lock["completed_runs"], 54)
        for row in lock["candidates"]:
            for seed in row["seeds"]:
                self.assertEqual(sha(self.artifacts / seed["checkpoint_path"]), seed["checkpoint_sha256"])
        manifest = read_json(self.output / "summary.json")
        self.assertTrue(all(sha(self.output / p) == h for p, h in manifest["files"].items()))

    def test_existing_analysis_output_is_preserved(self):
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_text("keep")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.run_analysis()
        self.assertEqual(sentinel.read_text(), "keep")

    def test_incomplete_duplicate_and_missing_seed_inventory_refused(self):
        for kind in ("incomplete", "duplicate", "seed"):
            with self.subTest(kind=kind):
                inventory = read_json(self.base / "experiment/inventory.json")
                if kind == "incomplete":
                    inventory.pop()
                elif kind == "duplicate":
                    inventory[-1] = inventory[0]
                else:
                    inventory[-1]["seed"] = 1
                write(self.experiment / "inventory.json", inventory)
                with self.assertRaisesRegex(ValueError, "inventory|changed run"):
                    self.run_analysis()
                self.assertFalse(self.output.exists())

    def test_config_and_test_data_policy_changes_refused(self):
        self.modify("experiment/config.json", lambda v: v.update(train_scope="head_only"))
        with self.assertRaisesRegex(ValueError, "joint grid config"):
            self.run_analysis()
        shutil.copyfile(self.base / "experiment/config.json", self.experiment / "config.json")
        self.modify("experiment/data-audit.json", lambda v: v.update(test_arrays_opened=True))
        with self.assertRaisesRegex(ValueError, "Data audit/test policy"):
            self.run_analysis()

    def test_changed_selected_ids_rejected(self):
        self.modify("experiment/selected_samples.json", lambda v: v["val"][0].update(sample_id="changed"))
        with self.assertRaisesRegex(ValueError, "Selected data IDs"):
            self.run_analysis()

    def test_export_metrics_and_checkpoint_hash_tamper_refused(self):
        metrics = self.experiment / "analysis/metrics.json"
        metrics.write_bytes(metrics.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "Exported file hash"):
            self.run_analysis()
        shutil.copyfile(self.base / "experiment/analysis/metrics.json", metrics)
        target = next(self.artifacts.glob("*/best-epoch-001.pt"))
        target.write_bytes(target.read_bytes() + b"tamper")
        with self.assertRaisesRegex(ValueError, "Checkpoint hash"):
            self.run_analysis()

    def test_exported_metrics_rehashed_but_not_matching_checkpoint_refused(self):
        self.modify("experiment/analysis/metrics.json", lambda v: v[0].update(ce=77))
        manifest = read_json(self.experiment / "analysis/summary.json")
        manifest["files"]["metrics.json"] = sha(self.experiment / "analysis/metrics.json")
        write(self.experiment / "analysis/summary.json", manifest)
        with self.assertRaisesRegex(ValueError, "Exported metrics differ"):
            self.run_analysis()

    def test_wrong_checkpoint_selection_history_refused(self):
        row = read_json(self.experiment / "inventory.json")[0]
        self.modify("experiment/" + row["run_id"] + "/history.json", lambda v: v[0]["validation"].update(ce=.00001))
        with self.assertRaisesRegex(ValueError, "selection differs"):
            self.run_analysis()

    def test_export_csv_or_plot_data_rehashed_but_incorrect_refused(self):
        for filename, message in (("metrics.csv", "CSV metrics differ"), ("plot-data.json", "plot data differs")):
            with self.subTest(filename=filename):
                path = self.experiment / "analysis" / filename
                original = path.read_bytes()
                if filename == "metrics.csv":
                    path.write_bytes(original.replace(b"0.3", b"7.3", 1))
                else:
                    self.modify("experiment/analysis/plot-data.json", lambda v: v[0].update(accuracy_mean=.01))
                manifest = read_json(self.experiment / "analysis/summary.json")
                manifest["files"][filename] = sha(path)
                write(self.experiment / "analysis/summary.json", manifest)
                with self.assertRaisesRegex(ValueError, message):
                    self.run_analysis()
                path.write_bytes(original)
                manifest["files"][filename] = sha(path)
                write(self.experiment / "analysis/summary.json", manifest)

    def test_invalid_rule_and_unfinished_grid_refused(self):
        self.modify("rule.json", lambda v: v.update(lambda_tie_break="Larger lambda1"))
        with self.assertRaisesRegex(ValueError, "Candidate rule"):
            self.run_analysis()
        shutil.copyfile(self.base / "rule.json", self.root / "rule.json")
        self.modify("experiment/status.json", lambda v: v.update(status="RUNNING", completed_runs=53))
        with self.assertRaisesRegex(ValueError, "Grid not completed"):
            self.run_analysis()

    def test_aggregation_requires_three_independent_seeds_and_tie_is_order_independent(self):
        _, _, _, records = analysis.authenticate(self.experiment, self.artifacts)
        with self.assertRaisesRegex(ValueError, "Missing/duplicate seed"):
            analysis.aggregate(records[:-1])
        groups = analysis.aggregate(records)
        chosen = analysis.candidates(list(reversed(groups)), list(reversed(records)))
        self.assertEqual([r["lambda1"] for r in chosen], [.1]*3)
        self.assertTrue(all([s["seed"] for s in r["seeds"]] == analysis.SEEDS for r in chosen))


if __name__ == "__main__":
    unittest.main(verbosity=2)
