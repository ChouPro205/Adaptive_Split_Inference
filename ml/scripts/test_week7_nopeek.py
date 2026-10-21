"""Mathematical, gradient, objective and real-data isolation checks for Week 7."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml/src"))

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.nn import functional as F

from distance_correlation import distance_correlation
from nopeek import nopeek_loss
import nopeek_data
from week3_common import load_model
from week1_common import ValidationError
from run_week7_nopeek import run as run_smoke


def independent_reference(x, y):
    """Raw Python distances + three-term covariance identity (no double centering).

    V² = mean(a*b) + mean(a)*mean(b) - 2*mean(rowmean(a)*rowmean(b)).
    Uses Python float/math.fsum rather than torch/cdist or our normalizer.
    """
    x, y = [list(map(float, row)) for row in x], [list(map(float, row)) for row in y]
    def distances(rows):
        return [[math.sqrt(math.fsum((a-b)**2 for a, b in zip(i, j))) for j in rows] for i in rows]
    a, b = distances(x), distances(y)
    n = len(x)
    def cov(u, v):
        ru, rv = [math.fsum(r)/n for r in u], [math.fsum(r)/n for r in v]
        return (math.fsum(u[i][j]*v[i][j] for i in range(n) for j in range(n))/n**2
                + math.fsum(ru)*math.fsum(rv)/n**2
                - 2*math.fsum(c*d for c, d in zip(ru, rv))/n)
    xx, yy = cov(a, a), cov(b, b)
    return math.sqrt(max(0, cov(a, b)) / math.sqrt(xx*yy)) if xx*yy > 0 else 0.0


class DistanceCorrelationTests(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(30)
        torch.set_num_threads(1)

    def test_self_shapes_and_noncontiguous(self):
        for dtype, atol in ((torch.float32, 2e-6), (torch.float64, 1e-12)):
            for shape in ((31,), (31, 4), (31, 3, 9)):
                x = torch.randn(shape, dtype=dtype)
                if x.ndim == 3:
                    x = x.transpose(1, 2)
                self.assertAlmostEqual(float(distance_correlation(x, x)), 1, delta=atol)

    def test_independent_low_dimensional_noise(self):
        # Biased finite-sample R is positive. Low dimension and n=1024 are
        # intentional; this threshold is not applicable to ECG d=360/B=32.
        values = []
        for seed in (7, 30, 20261021):
            generator = torch.Generator().manual_seed(seed)
            x, y = (torch.randn(1024, 1, dtype=torch.float64, generator=generator) for _ in range(2))
            value = float(distance_correlation(x, y))
            self.assertGreater(value, 0)
            self.assertLess(value, 0.12)
            values.append(value)
        print("independent_noise_Rn_n1024_d1 seeds7_30_20261021:", values)

    def test_independent_reference_and_not_squared(self):
        fixtures = [([[0], [1], [2], [3]], [[0], [1], [0], [2]]),
                    ([[0, 1], [2, 3], [0, 1], [8, -1], [4, 2]], [[3], [1], [1], [2], [6]])]
        for x, y in fixtures:
            expected = independent_reference(x, y)
            actual = float(distance_correlation(torch.tensor(x, dtype=torch.float64), torch.tensor(y, dtype=torch.float64)))
            self.assertAlmostEqual(actual, expected, delta=1e-12)
            self.assertGreater(abs(actual - expected**2), 0.03)
            print("reference_Rn:", expected, "torch_Rn:", actual)

    def test_symmetry_scale_translation_and_axis_semantics(self):
        x, y = torch.randn(17, 2, 5, dtype=torch.float64), torch.randn(17, 3, dtype=torch.float64)
        value = distance_correlation(x, y)
        for actual in (distance_correlation(y, x), distance_correlation(x.reshape(17, -1), y),
                       distance_correlation(x * -1e-100, y * 1e100), distance_correlation(x+7, y-4)):
            torch.testing.assert_close(value, actual, rtol=1e-12, atol=1e-12)

    def test_constant_rows_zero_gradients_and_extreme_finite(self):
        for dtype in (torch.float32, torch.float64):
            for constant in (0.0, 2.0, torch.finfo(dtype).max):
                x = torch.full((9, 2, 4), constant, dtype=dtype, requires_grad=True)
                y = torch.randn(9, 5, dtype=dtype, requires_grad=True)
                for a, b in ((x, y), (y, x), (x, x)):
                    value = distance_correlation(a, b)
                    self.assertEqual(float(value), 0)
                    gradients = torch.autograd.grad(value, (x, y), allow_unused=True)
                    for grad in gradients:
                        if grad is not None:
                            self.assertTrue(bool(torch.isfinite(grad).all()))
                            self.assertEqual(int(torch.count_nonzero(grad)), 0)
            # Repeated observations may contain different feature values.
            x = torch.tensor([[1., 2., -3.]] * 9, dtype=dtype, requires_grad=True)
            y = torch.randn(9, 2, dtype=dtype, requires_grad=True)
            self.assertEqual(float(distance_correlation(x, y)), 0)

    def test_duplicate_points_finite_backward(self):
        x = torch.tensor([[0., 1.], [0., 1.], [2., 3.], [-1., 2.]], requires_grad=True)
        y = torch.randn(4, 3, requires_grad=True)
        distance_correlation(x, y).backward()
        self.assertTrue(bool(torch.isfinite(x.grad).all() and torch.isfinite(y.grad).all()))

    def test_small_batch_and_invalid_inputs(self):
        x = torch.randn(5, 3)
        invalid = [(torch.tensor(1.), x), (torch.empty(0, 3), x), (torch.ones(1, 3), torch.ones(1, 2)),
                   (torch.empty(5, 0), x), (x, torch.randn(6, 2)), (x, x.double()),
                   (x, torch.ones(5, 1, dtype=torch.int64)), (x.half(), x.half()),
                   (x, torch.full((5, 2), float('nan'))), (x, torch.full((5, 2), float('inf'))), ([], x)]
        for a, b in invalid:
            with self.assertRaises((TypeError, ValueError)):
                distance_correlation(a, b)
        self.assertAlmostEqual(float(distance_correlation(torch.tensor([0., 1.]), torch.tensor([3., 8.]))), 1, delta=2e-6)

    def test_gradcheck_first_derivatives_both_inputs(self):
        x, y = torch.randn(6, 3, dtype=torch.float64, requires_grad=True), torch.randn(6, 2, dtype=torch.float64, requires_grad=True)
        self.assertTrue(torch.autograd.gradcheck(distance_correlation, (x, y), eps=1e-6, atol=1e-5, rtol=1e-3))

    def test_real_optimizer_step_reduces_privacy_objective(self):
        x = torch.randn(32, 5, dtype=torch.float64)
        head = nn.Linear(5, 3, bias=False).double()
        optimizer = torch.optim.SGD(head.parameters(), lr=0.01)
        before = distance_correlation(x, head(x))
        before.backward()
        self.assertGreater(float(head.weight.grad.norm()), 0)
        optimizer.step()
        after = distance_correlation(x, head(x))
        self.assertLess(float(after), float(before))
        print("one_SGD_step_Rn:", float(before.detach()), "->", float(after.detach()))

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA unavailable; CPU is required evidence")
    def test_cuda_value_and_gradient_parity(self):
        x, y = torch.randn(12, 7, dtype=torch.float64), torch.randn(12, 4, dtype=torch.float64)
        xc, yc = x.requires_grad_(), y.requires_grad_()
        xg, yg = x.detach().cuda().requires_grad_(), y.detach().cuda().requires_grad_()
        a, b = distance_correlation(xc, yc), distance_correlation(xg, yg)
        a.backward(); b.backward()
        torch.testing.assert_close(a, b.cpu(), atol=1e-12, rtol=1e-12)
        torch.testing.assert_close(xc.grad, xg.grad.cpu(), atol=1e-10, rtol=1e-9)


class ObjectiveTests(unittest.TestCase):
    def test_lambda0_exact_loss_gradient_update(self):
        torch.manual_seed(7)
        a = nn.Sequential(nn.Linear(4, 6), nn.ReLU(), nn.Linear(6, 5))
        b = copy.deepcopy(a)
        x, y = torch.randn(16, 4), torch.arange(16) % 5
        plain = F.cross_entropy(a(x), y)
        z = b[:2](x)
        loss, parts = nopeek_loss(b[2](z), y, x, z, 0)
        self.assertIs(loss, parts["ce"])
        self.assertTrue(torch.equal(loss, plain))
        plain.backward(); loss.backward()
        for p, q in zip(a.parameters(), b.parameters()):
            self.assertTrue(torch.equal(p.grad, q.grad))
        torch.optim.Adam(a.parameters(), lr=1e-4).step()
        torch.optim.Adam(b.parameters(), lr=1e-4).step()
        for p, q in zip(a.parameters(), b.parameters()):
            self.assertTrue(torch.equal(p, q))

    def test_positive_lambda_gradient_difference_is_privacy(self):
        torch.manual_seed(7)
        head, tail = nn.Linear(4, 6), nn.Linear(6, 5)
        x, y = torch.randn(16, 4), torch.arange(16) % 5
        z = head(x)
        loss, parts = nopeek_loss(tail(z), y, x, z, 0.5)
        params = tuple(head.parameters())
        total_g = torch.autograd.grad(loss, params, retain_graph=True)
        ce_g = torch.autograd.grad(parts["ce"], params, retain_graph=True)
        privacy_g = torch.autograd.grad(parts["dcor"], params)
        self.assertGreater(float(privacy_g[0].norm()), 0)
        for total, ce, privacy in zip(total_g, ce_g, privacy_g):
            torch.testing.assert_close(total-ce, 0.5*privacy, atol=1e-7, rtol=1e-5)

    def test_bad_lambda(self):
        for value in (-1, float('nan'), float('inf'), True, "0.5"):
            with self.assertRaises(ValueError):
                nopeek_loss(None, None, None, None, value)


class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.checkpoint = load_model(ROOT / "ml/data/week2/mitdb_baseline/best_checkpoint.pt",
                                       ROOT / "ml/src/mitdb_baseline_model.py")

    def test_authenticated_trainval_and_no_test_reads(self):
        original_np, original_pd = np.load, pd.read_csv
        paths = []
        def guard(function):
            def wrapped(path, *args, **kwargs):
                self.assertFalse(Path(path).name.startswith("test_"), "Test data opened")
                paths.append(Path(path).name)
                return function(path, *args, **kwargs)
            return wrapped
        with patch.object(nopeek_data.np, "load", guard(original_np)), patch.object(nopeek_data.pd, "read_csv", guard(original_pd)):
            _, _, arrays, metadata = nopeek_data.load_train_val(self.checkpoint)
        self.assertEqual(set(arrays), {"train", "val"})
        self.assertEqual(arrays["train"][0].shape, (81094, 1, 360))
        self.assertEqual(arrays["val"][0].shape, (15388, 1, 360))
        self.assertFalse(set(metadata["train"].patient_id) & set(metadata["val"].patient_id))
        self.assertEqual(len(paths), 6)  # four NPY arrays + two metadata CSVs

    def test_changed_checkpoint_dataset_binding_rejected(self):
        bad = copy.deepcopy(self.checkpoint)
        bad["provenance"]["dataset_artifacts"]["normalization_sha256"] = "0"*64
        with self.assertRaisesRegex(ValidationError, "identifiers differ"):
            nopeek_data.load_train_val(bad)

    def test_tampered_real_train_label_file_rejected_before_numpy(self):
        # Redirect only one artifact hash read to a corrupt copy, never mutate
        # hardlinks, originals or the authenticated checkpoint/provenance.
        original = nopeek_data.artifact_sha256
        with tempfile.TemporaryDirectory() as temporary:
            corrupt = Path(temporary) / "train_y.npy"
            payload = bytearray((ROOT / "ml/data/processed/mitdb/train_y.npy").read_bytes())
            payload[-1] ^= 1
            corrupt.write_bytes(payload)
            def hash_file(path):
                return original(corrupt if Path(path).name == "train_y.npy" else path)
            with patch.object(nopeek_data, "artifact_sha256", hash_file), patch.object(nopeek_data.np, "load", side_effect=AssertionError("must hash before load")):
                with self.assertRaisesRegex(ValidationError, "hash mismatch: train_y.npy"):
                    nopeek_data.load_train_val(self.checkpoint)


class RunnerSafetyTests(unittest.TestCase):
    def test_refuses_existing_output_without_changing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence"
            output.mkdir()
            sentinel = output / "keep.txt"
            sentinel.write_text("existing evidence")
            with self.assertRaisesRegex(ValueError, "Refuse to overwrite"):
                run_smoke(ROOT / "ml/configs/week7_nopeek_smoke.json", output, Path(directory) / "weights")
            self.assertEqual(sentinel.read_text(), "existing evidence")

    def test_refuses_outputs_outside_week7_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "fresh children of Week7"):
                run_smoke(ROOT / "ml/configs/week7_nopeek_smoke.json", Path(directory) / "new", Path(directory) / "weights")
            self.assertFalse((Path(directory) / "new").exists())

    def test_refuses_running_the_full_lambda_grid(self):
        with tempfile.TemporaryDirectory() as directory:
            config = json.loads((ROOT / "ml/configs/week7_nopeek_smoke.json").read_text())
            config["lambda1"] = [0, 0.1, 0.5, 1, 2, 5]
            path = Path(directory) / "grid.json"
            path.write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, "not the Week8 grid"):
                run_smoke(path, Path(directory) / "new", Path(directory) / "weights")


if __name__ == "__main__":
    unittest.main(verbosity=2)
