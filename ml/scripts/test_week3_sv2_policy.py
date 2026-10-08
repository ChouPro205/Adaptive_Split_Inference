"""Regression of scoped numerical budgets and exact evidence semantics."""
from __future__ import annotations
import sys
sys.dont_write_bytecode = True
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from week3_common import read_json
from verify_week3_sv2 import LEGACY, PORTABLE, check_evidence, compare_activation
from verify_week3_sv2 import verify

V1 = Path(__file__).resolve().parents[1] / "artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1"
ANCHOR = "a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6"


class NumericalPolicyRegression(unittest.TestCase):
    def test_dense_roundoff_allowed_only_in_explicit_policy(self):
        original = np.array([[15.718518257141113]], dtype=np.float32)
        linux = np.array([[15.718520164489746]], dtype=np.float32)
        self.assertFalse(compare_activation(original, linux, 9, PORTABLE)["same_bits"])
        for policy, s in ((LEGACY, 9), (PORTABLE, 8)):
            with self.assertRaisesRegex(ValueError, "bits differ"):
                compare_activation(original, linux, s, policy)

    def test_strict_dense_and_logit_boundaries(self):
        zero = np.zeros((1, 1), dtype=np.float32)
        for s, boundary in ((9, 1e-5), (10, 1e-3)):
            # First representable FP32 value above the decimal strict boundary.
            above = np.float32(boundary)
            if float(above) < boundary:
                above = np.nextafter(above, np.float32(np.inf))
            below = np.nextafter(above, np.float32(0))
            compare_activation(zero, np.array([[below]], dtype=np.float32), s, PORTABLE)
            with self.assertRaisesRegex(ValueError, "tolerance failure"):
                compare_activation(zero, np.array([[above]], dtype=np.float32), s, PORTABLE)

    def test_nonfinite_shape_and_dtype_rejected(self):
        original = np.zeros((1, 32), dtype=np.float32)
        for invalid in (np.ones((1, 31), dtype=np.float32), original.astype(np.float64),
                        np.full_like(original, np.nan), np.full_like(original, np.inf),
                        np.full_like(original, -np.inf)):
            with self.subTest(shape=invalid.shape, dtype=invalid.dtype, first=invalid.flat[0]):
                with self.assertRaises(ValueError):
                    compare_activation(original, invalid, 9, PORTABLE)

    def evidence(self):
        return read_json(V1 / "evidence/numerical_verification.json")

    def test_run_specific_error_values_and_worst_case_can_change(self):
        saved = self.evidence()
        observed = copy.deepcopy(saved)
        observed["rows"][0]["onnx_max_abs_error"] = 4e-6
        observed["per_split"][0]["onnx_worst"] = 4e-6
        observed["global_worst"] = copy.deepcopy(observed["rows"][0])
        check_evidence(saved, observed)

    def test_evidence_errors_metadata_and_summaries_rejected(self):
        saved = self.evidence()
        for label in ("nan", "inf", "negative", "over", "summary", "worst", "identity", "sample", "order", "graph", "count", "extra"):
            observed = copy.deepcopy(saved)
            if label in ("nan", "inf", "negative", "over"):
                observed["rows"][0]["onnx_max_abs_error"] = {"nan": float("nan"), "inf": float("inf"), "negative": -1e-6, "over": 1e-3}[label]
            elif label == "summary": observed["per_split"][0]["onnx_worst"] = 0
            elif label == "worst": observed["global_worst"] = observed["rows"][1]
            elif label == "identity": observed["s10_identity_rows"][0]["onnx_max_abs_error"] = 0
            elif label == "sample": observed["rows"][0]["sample_id"] = "wrong"
            elif label == "order": observed["rows"][0], observed["rows"][1] = observed["rows"][1], observed["rows"][0]
            elif label == "graph": observed["onnx_models"][0]["opset"] = 14
            elif label == "count": observed["comparisons"] = 199
            elif label == "extra": observed["rows"][0]["extra"] = 0
            with self.subTest(case=label):
                with self.assertRaises(ValueError): check_evidence(saved, observed)

    def test_full_verifier_rejects_changed_computation_with_original_anchor(self):
        # Keep original files/anchor. Inject a recomputation fault, not a forged
        # golden, and require the production policy to reject it before ONNX.
        import verify_week3_sv2 as verifier
        original = verifier.references
        def corrupt(*args):
            full, activations, errors = original(*args)
            activations[9][0, 0] += np.float32(1e-4)
            return full, activations, errors
        with patch.object(verifier, "references", side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, "tolerance failure: s=9"):
                verify(V1, ANCHOR, PORTABLE)

    def test_full_verifier_accepts_small_recomputation_only(self):
        import verify_week3_sv2 as verifier
        original = verifier.references
        def roundoff(*args):
            full, activations, errors = original(*args)
            activations[9][0, 0] += np.float32(2e-6)
            return full, activations, errors
        with patch.object(verifier, "references", side_effect=roundoff):
            result = verify(V1, ANCHOR, PORTABLE)
            self.assertEqual(result["recomputation_policy"], PORTABLE)
            self.assertFalse(result["legacy_contract_pass"])
            self.assertEqual(result["comparisons"], 200)

    def test_full_verifier_rejects_conv_drift_and_logit_fault(self):
        import verify_week3_sv2 as verifier
        original = verifier.references
        for s, delta, message in ((8, 1e-7, "bits differ: s=8"), (10, 1e-2, "tolerance failure: s=10")):
            def corrupt(*args):
                full, activations, errors = original(*args)
                activations[s].flat[0] += np.float32(delta)
                return full, activations, errors
            with self.subTest(split=s), patch.object(verifier, "references", side_effect=corrupt):
                with self.assertRaisesRegex(ValueError, message):
                    verify(V1, ANCHOR, PORTABLE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
