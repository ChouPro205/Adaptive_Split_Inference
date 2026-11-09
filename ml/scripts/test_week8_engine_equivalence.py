"""Check grouped finite guards against the authenticated initial Week 8 engine."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import statistics
import sys
import time
import types
import unittest

import numpy as np
import torch
import run_week8_nopeek as current
from week3_common import load_model, read_json
from train_mitdb_baseline import set_determinism

ROOT = current.ROOT
OLD = ROOT / "ml/results/week8-nopeek/pilot/pilot-cuda-joint-v1/sources/ml/scripts/run_week8_nopeek.py"
OLD_SHA = "2ea61d0dd9ae571a02b38413005cfa660e8814e71682061bba197b9b2ecbfcf0"


def original_module():
    source = OLD.read_bytes()
    if hashlib.sha256(source).hexdigest() != OLD_SHA:
        raise ValueError("Initial engine snapshot hash mismatch")
    module = types.ModuleType("authenticated_initial_week8_engine")
    module.__file__ = str(ROOT / "ml/scripts/run_week8_nopeek.py")
    exec(compile(source, str(OLD), "exec"), module.__dict__)
    return module


class EngineEquivalence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = original_module()
        cls.baseline, _ = load_model(ROOT / "ml/data/week2/mitdb_baseline/best_checkpoint.pt",
                                     ROOT / "ml/src/mitdb_baseline_model.py")
        rng = np.random.default_rng(713)
        cls.arrays = (rng.normal(size=(128, 1, 360)).astype(np.float32),
                      (np.arange(128) % 5).astype(np.int64))
        cls.config = read_json(ROOT / "ml/configs/week8_nopeek_approved_3seed_joint_v1.json")
        torch.backends.mkldnn.enabled = False

    def test_grouped_guards_reject_each_nonfinite_tensor(self):
        for device in ("cpu", "cuda") if torch.cuda.is_available() else ("cpu",):
            for dtype in (torch.float32, torch.float64):
                for bad in (float("nan"), float("inf"), -float("inf")):
                    values = [torch.ones(2, device=device, dtype=dtype), torch.tensor(bad, device=device, dtype=dtype)]
                    self.assertFalse(current.finite_tensors(values))
                x = torch.randn(5, device=device, dtype=dtype, requires_grad=True)
                rng = torch.get_rng_state().clone()
                self.assertTrue(current.finite_tensors((x, x[:1])))
                self.assertIsNone(x.grad)
                self.assertTrue(torch.equal(rng, torch.get_rng_state()))

    def test_loss_metrics_weights_gradients_and_rng_are_bit_exact(self):
        for device in ("cpu", "cuda") if torch.cuda.is_available() else ("cpu",):
            config = copy.deepcopy(self.config)
            config.update(device=device, threads=1)
            for split in (2, 5, 8):
                for lambda1 in (0, 0.5):
                    with self.subTest(device=device, split=split, lambda1=lambda1):
                        results = []
                        for engine in (self.old, current):
                            set_determinism(137, 1)
                            torch.backends.cudnn.allow_tf32 = False
                            model, head, tail = engine.configure_model(self.baseline, split, "head_and_tail", device)
                            opt = torch.optim.Adam(model.parameters(), lr=1e-4)
                            metrics = engine.epoch_metrics(model, head, tail, self.arrays, np.arange(128), config, lambda1, opt)
                            results.append((metrics, engine.state_digest(model), [p.grad.detach().cpu().clone() for p in model.parameters()],
                                            torch.get_rng_state().clone(), torch.cuda.get_rng_state().cpu() if device == "cuda" else None))
                        self.assertEqual(results[0][:2], results[1][:2])
                        for a, b in zip(results[0][2], results[1][2]):
                            self.assertTrue(torch.equal(a, b))
                        self.assertTrue(torch.equal(results[0][3], results[1][3]))
                        if device == "cuda":
                            self.assertTrue(torch.equal(results[0][4], results[1][4]))


def benchmark():
    """Report timing only; timing variance is not a correctness gate."""
    if not torch.cuda.is_available():
        return
    fixture = EngineEquivalence
    config = copy.deepcopy(fixture.config)
    config.update(device="cuda", threads=4)
    for engine in (fixture.old, current):
        durations = []
        for repeat in range(4):
            set_determinism(137, 4)
            model, head, tail = engine.configure_model(fixture.baseline, 5, "head_and_tail", "cuda")
            opt = torch.optim.Adam(model.parameters(), lr=1e-4)
            torch.cuda.synchronize()
            start = time.monotonic()
            engine.epoch_metrics(model, head, tail, fixture.arrays, np.arange(128), config, .5, opt)
            torch.cuda.synchronize()
            if repeat:
                durations.append(time.monotonic()-start)
        print(engine.__name__, "CUDA 4-batch median seconds:", statistics.median(durations), flush=True)


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False).result
    if not result.wasSuccessful():
        sys.exit(1)
    benchmark()
