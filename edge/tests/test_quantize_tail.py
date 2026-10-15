"""Host checks for edge/quantize_tail.py; never a DPU/VART result.

Run from the repository root with the project venv:
    python -B edge/tests/test_quantize_tail.py
The vai_q_pytorch API is replaced by a stub only to check file handling.
"""
import json
import sys
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8", errors="replace")  # Vietnamese logs on Windows consoles.
sys.path.insert(0, str(ROOT / "edge"))
import quantize_tail as qt  # noqa: E402

PACKAGE = ROOT / "ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1"


class StubQuantizer:
    """Records calls like vai_q_pytorch.torch_quantizer without quantizing."""

    def __init__(self, quant_mode, module, input_args, output_dir, device):
        self.quant_model, self.output_dir = module, Path(output_dir)

    def export_quant_config(self):
        (self.output_dir / "quant_info.json").write_text("{}", encoding="utf-8")

    def export_xmodel(self, output_dir, deploy_check):
        (Path(output_dir) / "Sequential_int.xmodel").write_bytes(b"stub xmodel")


class QuantizeTailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)

    def test_split_matches_frozen_goldens(self):
        full = qt.load_full_model(qt.DEFAULT_CHECKPOINT)
        logits = np.load(PACKAGE / "golden/z_s10.npy", allow_pickle=False)
        inputs = np.load(PACKAGE / "golden/z_s0.npy", allow_pickle=False)
        for s in range(10):
            golden = np.load(PACKAGE / f"golden/z_s{s}.npy", allow_pickle=False)
            head, tail = qt.split_modules(full, s)
            with torch.no_grad():
                z = head(torch.from_numpy(inputs)).numpy()
                out = tail(torch.from_numpy(golden)).numpy()
            self.assertEqual(z.shape[1:], qt.SHAPES[s][1:])
            self.assertLess(float(np.max(np.abs(z.astype(np.float64) - golden))), 1e-3, f"head s={s}")
            self.assertLess(float(np.max(np.abs(out.astype(np.float64) - logits))), 1e-3, f"tail s={s}")

    def test_missing_or_unapproved_checkpoint_fails(self):
        with self.assertRaisesRegex(qt.TailQuantizationError, "not found"):
            qt.load_full_model(self.out / "missing.pt")
        other = self.out / "other.pt"
        torch.save({"state_dict": qt.baseline_model().state_dict()}, other)
        with self.assertRaisesRegex(qt.TailQuantizationError, "differs from the approved"):
            qt.load_full_model(other)

    def test_calibration_split_policy(self):
        for split, count in (("test", 4), ("train", 0)):
            with self.assertRaises(qt.TailQuantizationError):
                qt.calibration_inputs(split, count)
        first, source = qt.calibration_inputs("train", 16)
        again, _ = qt.calibration_inputs("train", 16)
        self.assertEqual(first.shape, (16, 1, 360))
        self.assertEqual(first.tobytes(), again.tobytes())
        self.assertEqual((source["split"], source["samples"]), ("train", 16))
        val, source = qt.calibration_inputs("val", 8)
        self.assertEqual((val.shape, source["split"]), ((8, 1, 360), "val"))

    def test_provided_activations_need_declared_split_and_shape(self):
        full = qt.load_full_model(qt.DEFAULT_CHECKPOINT)
        path = self.out / "z.npy"
        np.save(path, np.zeros((4, 16, 180), np.float32))
        with self.assertRaisesRegex(qt.TailQuantizationError, "declaring"):
            qt.get_calibration_data(2, full, "train", 4, path, None)
        with self.assertRaisesRegex(qt.TailQuantizationError, "must be finite"):
            qt.get_calibration_data(3, full, "train", 4, path, "val")
        samples, source = qt.get_calibration_data(2, full, "train", 4, path, "val")
        self.assertEqual((len(samples), source["declared_split"]), (4, "val"))

    def test_run_records_provenance_and_marks_synthetic(self):
        apis = types.ModuleType("pytorch_nndct.apis")
        apis.torch_quantizer = StubQuantizer
        stub = {"pytorch_nndct": types.ModuleType("pytorch_nndct"), "pytorch_nndct.apis": apis}
        real = self.out / "real"
        with unittest.mock.patch.dict(sys.modules, stub):
            for mode in ("calib", "test"):
                self.assertEqual(qt.run_quantization(4, mode, real, qt.DEFAULT_CHECKPOINT, calib_samples=8), 0)
            record = json.loads((real / qt.PROVENANCE_NAME).read_text(encoding="utf-8"))
            self.assertEqual((record["synthetic"], record["acceptance_evidence"]), (False, True))
            self.assertEqual(record["checkpoint"]["sha256"], qt.CHECKPOINT_SHA256)
            self.assertEqual(record["calibration"]["split"], "train")
            self.assertTrue((real / "tail_4_int.xmodel").is_file())
            synthetic = self.out / "synthetic"
            self.assertEqual(qt.run_quantization(4, "test", synthetic, None, calib_samples=2, synthetic=True), 0)
            self.assertTrue((synthetic / qt.SYNTHETIC_MARKER).is_file())
            self.assertTrue((synthetic / "tail_4_SYNTHETIC_int.xmodel").is_file())
            self.assertFalse((synthetic / "tail_4_int.xmodel").exists())
            with self.assertRaisesRegex(qt.TailQuantizationError, "synthetic results"):
                qt.run_quantization(4, "test", synthetic, qt.DEFAULT_CHECKPOINT, calib_samples=2)

    def test_dry_run_creates_no_xmodel(self):
        out = self.out / "dry"
        self.assertEqual(qt.run_quantization(9, "test", out, qt.DEFAULT_CHECKPOINT, dry_run=True, calib_samples=4), 0)
        self.assertEqual(sorted(p.name for p in out.iterdir()), [qt.PROVENANCE_NAME])


if __name__ == "__main__":
    unittest.main(verbosity=2)
