"""Behavioral checks for the Week 8 runner; CPU, synthetic samples, frozen model."""
from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import torch
from torch.nn import functional as F

import run_week8_nopeek as runner
import summarize_week8_nopeek as exporter
from distance_correlation import distance_correlation
from nopeek import nopeek_loss
from train_mitdb_baseline import set_determinism
from week3_common import load_model, read_json

ROOT = runner.ROOT
CONFIG_PATH = ROOT / "ml/configs/week8_nopeek_protocol_v1.json"


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline, _ = load_model(ROOT / "ml/data/week2/mitdb_baseline/best_checkpoint.pt",
                                     ROOT / "ml/src/mitdb_baseline_model.py")

    def setUp(self):
        self.config = read_json(CONFIG_PATH)
        self.config.update(batch_size=8, threads=1)
        set_determinism(137, 1)
        torch.backends.mkldnn.enabled = False
        rng = np.random.default_rng(19)
        self.arrays = {s: (rng.normal(size=(n, 1, 360)).astype(np.float32),
                           (np.arange(n) % 5).astype(np.int64))
                       for s, n in (("train", 32), ("val", 17))}

    def optimizer(self, model):
        return torch.optim.Adam([p for p in model.parameters() if p.requires_grad], lr=1e-4)

    def one(self, output, artifacts, identity=None, resume=False, epochs=3, patience=5):
        return runner.run_one(self.baseline, self.arrays, self.config, 5, 0.5, 137,
                              output, artifacts, identity or {"test": "resume-v1"},
                              epochs, patience, resume=resume)

    def test_lambda_zero_matches_ce_loss_gradients_and_adam_for_both_scopes(self):
        x, y = (torch.from_numpy(a[:8].copy()) for a in self.arrays["train"])
        for scope in ("head_only", "head_and_tail"):
            with self.subTest(scope=scope):
                a, ah, at = runner.configure_model(self.baseline, 5, scope, "cpu")
                b, bh, bt = runner.configure_model(self.baseline, 5, scope, "cpu")
                runner.set_mode(a, ah, at, True, scope)
                runner.set_mode(b, bh, bt, True, scope)
                torch.manual_seed(191)
                plain = F.cross_entropy(a(x), y)
                torch.manual_seed(191)
                z = bh(x)
                objective, parts = nopeek_loss(bt(z), y, x, z, 0)
                self.assertIs(objective, parts["ce"])
                self.assertTrue(torch.equal(plain, objective))
                plain.backward()
                objective.backward()
                for p, q in zip(a.parameters(), b.parameters()):
                    if p.requires_grad:
                        self.assertTrue(torch.equal(p.grad, q.grad))
                    else:
                        self.assertIsNone(p.grad)
                        self.assertIsNone(q.grad)
                self.optimizer(a).step()
                self.optimizer(b).step()
                self.assertEqual(runner.state_digest(a), runner.state_digest(b))

    def test_isolated_dcor_gradient_reaches_all_three_heads(self):
        x = torch.from_numpy(self.arrays["train"][0][:8].copy())
        for split in (2, 5, 8):
            with self.subTest(split=split):
                model, head, tail = runner.configure_model(self.baseline, split, "head_only", "cpu")
                loss = distance_correlation(x, head(x))
                grads = torch.autograd.grad(loss, tuple(head.parameters()))
                self.assertTrue(bool(torch.isfinite(loss)))
                self.assertTrue(all(bool(torch.isfinite(g).all()) for g in grads))
                self.assertGreater(sum(float(g.square().sum()) for g in grads), 0)
                self.assertTrue(all(p.grad is None for p in tail.parameters()))

    def test_head_training_keeps_tail_frozen_and_restores_modes_each_phase(self):
        model, head, tail = runner.configure_model(self.baseline, 5, "head_only", "cpu")
        tail_before = runner.state_digest(tail)
        head_before = runner.state_digest(head)
        initial = runner.state_digest(self.baseline)
        train = runner.epoch_metrics(model, head, tail, self.arrays["train"], np.arange(32),
                                     self.config, 0.5, self.optimizer(model))
        self.assertTrue(all(m.training for m in head.modules()))
        self.assertTrue(all(not m.training for m in tail.modules()))
        self.assertEqual(runner.state_digest(tail), tail_before)
        self.assertNotEqual(runner.state_digest(head), head_before)
        self.assertEqual(runner.state_digest(self.baseline), initial)
        self.assertTrue(all(np.isfinite(train[k]) for k in ("ce", "dcor", "total")))
        runner.epoch_metrics(model, head, tail, self.arrays["val"], np.arange(17), self.config, 0.5)
        self.assertTrue(all(not m.training for m in model.modules()))
        runner.epoch_metrics(model, head, tail, self.arrays["train"], np.arange(32),
                             self.config, 0.5, self.optimizer(model))
        self.assertTrue(head.training)
        self.assertFalse(tail.training)

    def test_joint_scope_enables_dropout_during_train_only(self):
        model, head, tail = runner.configure_model(self.baseline, 5, "head_and_tail", "cpu")
        dropout = [m for m in model.modules() if isinstance(m, torch.nn.Dropout)]
        self.assertTrue(dropout)
        self.assertTrue(all(p.requires_grad for p in model.parameters()))
        runner.set_mode(model, head, tail, True, "head_and_tail")
        self.assertTrue(all(m.training for m in dropout))
        runner.set_mode(model, head, tail, False, "head_and_tail")
        self.assertTrue(all(not m.training for m in model.modules()))

    def test_validation_preserves_weights_and_existing_gradients_including_singleton(self):
        model, head, tail = runner.configure_model(self.baseline, 5, "head_only", "cpu")
        runner.epoch_metrics(model, head, tail, self.arrays["train"], np.arange(32),
                             self.config, 0.5, self.optimizer(model))
        weights = runner.state_digest(model)
        gradients = [None if p.grad is None else p.grad.clone() for p in model.parameters()]
        result = runner.epoch_metrics(model, head, tail, self.arrays["val"], np.arange(17), self.config, 0.5)
        self.assertEqual(runner.state_digest(model), weights)
        for p, grad in zip(model.parameters(), gradients):
            if grad is None:
                self.assertIsNone(p.grad)
            else:
                self.assertTrue(torch.equal(p.grad, grad))
        self.assertEqual((result["samples"], result["dcor_samples"], result["batches"]), (17, 16, 3))
        self.assertEqual(result["dropped_samples"], 0)
        self.assertEqual(sum(map(sum, result["confusion_matrix"])), 17)
        self.assertEqual([result["per_class"][c]["support"] for c in "NSVFQ"], [4, 4, 3, 3, 3])
        again = runner.epoch_metrics(model, head, tail, self.arrays["val"], np.arange(17), self.config, 0.5)
        self.assertEqual(result, again)

    def test_train_drops_incomplete_batch_while_validation_retains_it(self):
        model, head, tail = runner.configure_model(self.baseline, 2, "head_only", "cpu")
        result = runner.epoch_metrics(model, head, tail, self.arrays["train"], np.arange(31),
                                      self.config, 0, self.optimizer(model))
        self.assertEqual((result["samples"], result["dropped_samples"]), (24, 7))
        result = runner.epoch_metrics(model, head, tail, self.arrays["train"], np.arange(31), self.config, 0)
        self.assertEqual((result["samples"], result["dcor_samples"], result["dropped_samples"]), (31, 31, 0))

    def test_ce_selection_ignores_accuracy_and_keeps_earliest_tie(self):
        self.assertTrue(runner.selection(None, {"ce": 1.0}))
        self.assertTrue(runner.selection({"ce": 1.0, "accuracy": 0.9}, {"ce": 0.9, "accuracy": 0.1}))
        self.assertFalse(runner.selection({"ce": 1.0, "accuracy": 0.1}, {"ce": 1.0, "accuracy": 0.9}))
        self.assertFalse(runner.selection({"ce": 1.0}, {"ce": 1.01}))

    def test_checkpoint_selection_patience_and_reload_choose_earlier_best(self):
        real = runner.epoch_metrics
        ce_values = iter((1.0, 0.9, 0.95, 0.96, 0.9))
        def controlled(*args, **kwargs):
            metrics = real(*args, **kwargs)
            training = (len(args) >= 8 and args[7] is not None) or kwargs.get("optimizer") is not None
            if not training:
                metrics["ce"] = next(ce_values)
            return metrics
        with tempfile.TemporaryDirectory() as directory:
            output, artifacts = Path(directory) / "out", Path(directory) / "art"
            with patch.object(runner, "epoch_metrics", side_effect=controlled):
                summary = self.one(output, artifacts, epochs=8, patience=2)
            self.assertEqual((summary["best_epoch"], summary["epochs_completed"], summary["stop_reason"]), (2, 4, "patience"))
            self.assertTrue(summary["reload_validation_exact"])
            checkpoint = torch.load(artifacts / summary["best_checkpoint"], map_location="cpu", weights_only=True)
            self.assertEqual(checkpoint["epoch"], 2)
            self.assertEqual(checkpoint["best"]["ce"], 0.9)
            self.assertEqual(checkpoint["deployment_status"], "EXPERIMENT_ONLY_NOT_APPROVED")

    def test_interruption_resume_reproduces_uninterrupted_state_and_metrics(self):
        # Exercise RNG recovery with active Dropout, not only deterministic frozen-tail training.
        self.config["train_scope"] = "head_and_tail"
        real = runner.epoch_metrics
        training_calls = 0
        def interrupt_second_train(*args, **kwargs):
            nonlocal training_calls
            training = (len(args) >= 8 and args[7] is not None) or kwargs.get("optimizer") is not None
            if training:
                training_calls += 1
                if training_calls == 2:
                    raise KeyboardInterrupt()
            return real(*args, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out, art = root / "resumed", root / "weights"
            with patch.object(runner, "epoch_metrics", side_effect=interrupt_second_train):
                with self.assertRaises(KeyboardInterrupt):
                    self.one(out, art)
            self.assertEqual(read_json(out / "status.json")["status"], "INTERRUPTED")
            last = torch.load(art / "last.pt", map_location="cpu", weights_only=True)
            self.assertEqual(last["epoch"], 1)
            resumed = self.one(out, art, resume=True)
            uninterrupted = self.one(root / "complete", root / "complete-weights")
            for key in ("best_epoch", "epochs_completed", "validation", "final_state_sha256"):
                self.assertEqual(resumed[key], uninterrupted[key])
            a, b = read_json(out / "history.json"), read_json(root / "complete/history.json")
            for row in a + b:
                row.pop("seconds")
            self.assertEqual(a, b)
            self.assertEqual(read_json(out / "status.json")["status"], "COMPLETED")

    def test_resume_rejects_changed_identity_and_tampered_completed_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out, art = root / "out", root / "art"
            summary = self.one(out, art, epochs=1)
            before = (out / "status.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "identity changed"):
                self.one(out, art, identity={"test": "changed"}, resume=True, epochs=1)
            self.assertEqual((out / "status.json").read_bytes(), before)
            checkpoint = art / summary["best_checkpoint"]
            checkpoint.write_bytes(checkpoint.read_bytes() + b"tamper")
            with self.assertRaisesRegex(ValueError, "checkpoint changed"):
                self.one(out, art, resume=True, epochs=1)

    def test_existing_run_is_never_overwritten_and_baseline_is_fresh(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out, art = root / "out", root / "art"
            initial = runner.state_digest(self.baseline)
            first = self.one(out, art, epochs=1)
            summary_bytes = (out / "summary.json").read_bytes()
            with self.assertRaises(FileExistsError):
                self.one(out, art, epochs=1)
            self.assertEqual((out / "summary.json").read_bytes(), summary_bytes)
            second = self.one(root / "out2", root / "art2", epochs=1)
            self.assertEqual(runner.state_digest(self.baseline), initial)
            self.assertEqual(first["identity"]["initial_state_sha256"], initial)
            self.assertEqual(first["final_state_sha256"], second["final_state_sha256"])

    def test_nonfinite_batch_marks_failed_without_completed_summary(self):
        self.arrays["train"][0][0, 0, 0] = np.nan
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out, art = root / "out", root / "art"
            with self.assertRaises(ValueError):
                self.one(out, art)
            self.assertEqual(read_json(out / "status.json")["status"], "FAILED")
            self.assertFalse((out / "summary.json").exists())

    def test_orphan_best_checkpoint_is_preserved_and_resume_refuses_overwrite(self):
        real = runner.atomic_torch
        def interrupt_before_last(path, value):
            if path.name == "last.pt":
                raise KeyboardInterrupt()
            return real(path, value)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out, art = root / "out", root / "art"
            with patch.object(runner, "atomic_torch", side_effect=interrupt_before_last):
                with self.assertRaises(KeyboardInterrupt):
                    self.one(out, art, epochs=1)
            orphan = art / "best-epoch-001.pt"
            before = orphan.read_bytes()
            self.assertFalse((art / "last.pt").exists())
            with self.assertRaisesRegex(ValueError, "Orphan best checkpoint"):
                self.one(out, art, epochs=1, resume=True)
            self.assertEqual(orphan.read_bytes(), before)
            self.assertEqual(read_json(out / "status.json")["status"], "FAILED")


class ProtocolSafetyTests(unittest.TestCase):
    def setUp(self):
        self.config = read_json(CONFIG_PATH)

    def test_proposed_protocol_allows_pilot_but_blocks_grid(self):
        runner.validate_config(self.config, "pilot")
        with self.assertRaisesRegex(ValueError, "recorded protocol approval"):
            runner.validate_config(self.config, "grid")
        self.config["approval"] = {"status": "APPROVED", "authority": "test-only", "evidence": "test-only"}
        runner.validate_config(self.config, "grid")
        self.config["approval"]["evidence"] = None
        with self.assertRaisesRegex(ValueError, "recorded protocol approval"):
            runner.validate_config(self.config, "grid")

    def test_rejects_invalid_seeds_grid_scope_and_selection_policy(self):
        for key, value in (("seeds", []), ("seeds", [7, 7]), ("seeds", [True]),
                           ("seeds", [-1]), ("lambda1", [0, 0.5]), ("splits", [2, 5]),
                           ("batch_size", 2), ("class_weighting", "balanced")):
            with self.subTest(key=key, value=value):
                changed = copy.deepcopy(self.config)
                changed[key] = value
                with self.assertRaises(ValueError):
                    runner.validate_config(changed, "pilot")
        for key, value in (("select_by", "test_accuracy"), ("max_epochs", 0), ("ties", "latest_epoch")):
            changed = copy.deepcopy(self.config)
            changed["training_policy"][key] = value
            with self.assertRaises(ValueError):
                runner.validate_config(changed, "pilot")

    def test_missing_seed_or_policy_is_rejected(self):
        for key in ("seeds", "training_policy"):
            changed = copy.deepcopy(self.config)
            del changed[key]
            with self.assertRaises((ValueError, KeyError)):
                runner.validate_config(changed, "pilot")

    def test_refuses_output_outside_pilot_root_before_loading_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(runner, "load_model", side_effect=AssertionError("must not load data")):
                with self.assertRaisesRegex(ValueError, "Week8 pilot/grid roots"):
                    runner.run(CONFIG_PATH, root / "out", root / "art", "pilot")
            self.assertFalse((root / "out").exists())
            self.assertFalse((root / "art").exists())

    def test_inventory_rejects_missing_duplicate_changed_and_invalid_status(self):
        policy = self.config["pilot"]
        inventory = [{"run_id": f"s{s}-lambda{l:g}-seed{k}", "split": s,
                      "lambda1": l, "seed": k, "status": "NOT_STARTED"}
                     for k in policy["seeds"] for s in policy["splits"] for l in policy["lambda1"]]
        runner.validate_inventory(inventory, policy)
        for broken in (inventory[:-1], inventory[:-1] + [inventory[0]]):
            with self.assertRaisesRegex(ValueError, "Missing/duplicate"):
                runner.validate_inventory(broken, policy)
        changed = copy.deepcopy(inventory)
        changed[0]["split"] = 8
        with self.assertRaisesRegex(ValueError, "combination changed"):
            runner.validate_inventory(changed, policy)
        changed = copy.deepcopy(inventory)
        changed[0]["status"] = "PASS"
        with self.assertRaisesRegex(ValueError, "Invalid run status"):
            runner.validate_inventory(changed, policy)

    def test_exclusive_checkpoint_lock_is_preserved_and_partial_lock_released(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / "ml/results/week8-nopeek/pilot/run"
            art = root / "ml/artifacts/week8-nopeek/pilot/run"
            art.parent.mkdir(parents=True)
            lock = art.with_name(art.name + ".lock")
            lock.write_text("existing process", encoding="utf-8")
            with patch.object(runner, "ROOT", root), patch.object(runner, "_run") as execution:
                with self.assertRaises(FileExistsError):
                    runner.run(CONFIG_PATH, out, art, "pilot", resume=True)
                execution.assert_not_called()
            self.assertEqual(lock.read_text(encoding="utf-8"), "existing process")
            self.assertFalse(out.with_name(out.name + ".lock").exists())


class SummarizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        root = Path(cls.fixture.name)
        cls.experiment, cls.artifacts = root / "experiment", root / "artifacts"
        cls.experiment.mkdir()
        cls.artifacts.mkdir()
        config = read_json(CONFIG_PATH)
        config.update(batch_size=8, threads=1, seeds=[137])
        config["pilot"].update(seeds=[137], train_samples=8, validation_samples=9, max_epochs=1, patience=1)
        samples = {"train": list(range(8)), "val": list(range(9))}
        source = cls.experiment / "sources" / "test-fixture.py"
        source.parent.mkdir()
        source.write_text("# Synthetic fixture source identity.\n", encoding="utf-8")
        identity = {"mode": "pilot", "config_sha256": runner.config_digest(config),
                    "selected_samples_sha256": runner.config_digest(samples),
                    "source_sha256": {"test-fixture.py": runner.sha(source)}}
        runner.atomic_json(cls.experiment / "identity.json", identity)
        runner.atomic_json(cls.experiment / "config.json", config)
        runner.atomic_json(cls.experiment / "selected_samples.json", samples)
        baseline, _ = load_model(ROOT / "ml/data/week2/mitdb_baseline/best_checkpoint.pt",
                                 ROOT / "ml/src/mitdb_baseline_model.py")
        set_determinism(137, 1)
        torch.backends.mkldnn.enabled = False
        rng = np.random.default_rng(8)
        arrays = {s: (rng.normal(size=(n, 1, 360)).astype(np.float32), (np.arange(n) % 5).astype(np.int64))
                  for s, n in (("train", 8), ("val", 9))}
        inventory = []
        for split in (2, 5, 8):
            for value in (0, 0.5):
                name = f"s{split}-lambda{value:g}-seed137"
                summary = runner.run_one(baseline, arrays, config, split, value, 137,
                                          cls.experiment / name, cls.artifacts / name, identity, 1, 1)
                inventory.append({"run_id": name, "split": split, "lambda1": value, "seed": 137,
                                  "status": "COMPLETED", "checkpoint_sha256": summary["checkpoint_sha256"]})
        runner.atomic_json(cls.experiment / "inventory.json", inventory)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        root = Path(self.workspace.name)
        self.experiment, self.artifacts, self.output = root / "experiment", root / "artifacts", root / "summary"
        shutil.copytree(type(self).experiment, self.experiment)
        shutil.copytree(type(self).artifacts, self.artifacts)

    def tearDown(self):
        self.workspace.cleanup()

    def test_export_authenticates_six_pilot_runs_and_produces_csv_three_panels(self):
        rows = exporter.summarize(self.experiment, self.artifacts, self.output)
        self.assertEqual(len(rows), 6)
        self.assertEqual({r["split"] for r in rows}, {2, 5, 8})
        summary = read_json(self.output / "summary.json")
        self.assertEqual((summary["completed_runs"], summary["expected_runs"], summary["mode"]), (6, 6, "pilot"))
        self.assertFalse(summary["full_grid_complete"])
        self.assertEqual(summary["privacy_claim"], "NOT_EVALUATED")
        self.assertEqual(summary["missing"], [])
        with (self.output / "metrics.csv").open(encoding="utf-8", newline="") as handle:
            csv_rows = list(csv.DictReader(handle))
        self.assertEqual(len(csv_rows), 6)
        self.assertTrue(all(f"recall_{c}" in csv_rows[0] for c in "NSVFQ"))
        self.assertEqual(len(read_json(self.output / "plot-data.json")), 6)
        svg = (self.output / "validation-accuracy-lambda.svg").read_text(encoding="utf-8")
        for label in ("s2", "s5", "s8", "PILOT", "6/6 runs"):
            self.assertIn(label, svg)
        from PIL import Image
        with Image.open(self.output / "validation-accuracy-lambda.png") as image:
            self.assertEqual(image.size, (2160, 720))
        for name, digest in summary["files"].items():
            self.assertEqual(runner.sha(self.output / name), digest)
        with self.assertRaisesRegex(ValueError, "Refuse to overwrite"):
            exporter.summarize(self.experiment, self.artifacts, self.output)

    def test_export_rejects_tampered_source_snapshot_before_creating_output(self):
        (self.experiment / "sources/test-fixture.py").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Source snapshot changed"):
            exporter.summarize(self.experiment, self.artifacts, self.output)
        self.assertFalse(self.output.exists())

    def test_export_rejects_metrics_that_differ_from_selected_checkpoint(self):
        row = read_json(self.experiment / "inventory.json")[0]
        path = self.experiment / row["run_id"] / "summary.json"
        summary = read_json(path)
        summary["validation"]["accuracy"] += 0.01
        runner.atomic_json(path, summary)
        with self.assertRaisesRegex(ValueError, "Checkpoint metrics/selection binding differs"):
            exporter.summarize(self.experiment, self.artifacts, self.output)
        self.assertFalse(self.output.exists())

    def test_export_rejects_missing_inventory_combination(self):
        inventory = read_json(self.experiment / "inventory.json")
        runner.atomic_json(self.experiment / "inventory.json", inventory[:-1])
        with self.assertRaisesRegex(ValueError, "Missing/duplicate inventory combinations"):
            exporter.summarize(self.experiment, self.artifacts, self.output)
        self.assertFalse(self.output.exists())

    def test_partial_pilot_exports_honest_counts_and_a_gap_for_missing_lambda(self):
        inventory = read_json(self.experiment / "inventory.json")
        inventory[1]["status"] = "FAILED"
        runner.atomic_json(self.experiment / "inventory.json", inventory)
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib.axes import Axes
        original = Axes.errorbar
        plotted = []
        def record(axis, xs, ys, *args, **kwargs):
            plotted.append((list(xs), list(ys)))
            return original(axis, xs, ys, *args, **kwargs)
        with patch.object(Axes, "errorbar", new=record):
            rows = exporter.summarize(self.experiment, self.artifacts, self.output)
        self.assertEqual(len(rows), 5)
        summary = read_json(self.output / "summary.json")
        self.assertEqual((summary["completed_runs"], summary["expected_runs"]), (5, 6))
        self.assertFalse(summary["full_grid_complete"])
        self.assertEqual(summary["missing"], [inventory[1]])
        self.assertEqual(len(read_json(self.output / "plot-data.json")), 5)
        self.assertEqual(len(plotted), 3)
        self.assertEqual(plotted[0][0], [0, 0.5])
        self.assertTrue(np.isfinite(plotted[0][1][0]))
        self.assertTrue(np.isnan(plotted[0][1][1]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
