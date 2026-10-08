"""Reject checkout drift before invoking the immutable numerical engine."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import verify_week4_current as current
import week4_handoff_auth as policy

ROOT = Path(__file__).resolve().parents[2]


class CurrentCheckoutRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Inside the ignored artifact folder, Git can read the real pinned
        # objects through the parent repo; no synthetic source blobs are used.
        scratch_parent = ROOT/"ml/artifacts/week4"
        scratch_parent.mkdir(parents=True, exist_ok=True)
        cls.scratch = tempfile.TemporaryDirectory(prefix="current-r4-test-", dir=scratch_parent)
        cls.repo = Path(cls.scratch.name)
        for name in (policy.R3, policy.R4, policy.PACKAGE):
            shutil.copytree(ROOT/name, cls.repo/name)
        cls.manifest = json.loads((ROOT/policy.R4/"manifest.json").read_bytes())
        for row in cls.manifest["source_files"]:
            target = cls.repo/row["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/row["path"], target)
        cls.original = {row["path"]: subprocess.check_output([
            "git", "show", f"89109fd352d84a5fe0815d7e045e52538de7bad8:{row['path']}"
        ], cwd=ROOT) for row in cls.manifest["source_files"]}

    @classmethod
    def tearDownClass(cls):
        # Windows scanners can briefly hold newly copied headers open. Retry
        # cleanup, but never turn a persistent cleanup failure into a SKIP.
        for attempt in range(20):
            try:
                cls.scratch.cleanup()
                return
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.1)

    def rejects_before_engine(self, path, raw, message):
        target = self.repo/path
        saved = target.read_bytes()
        try:
            target.write_bytes(raw)
            with patch.object(current, "run_historical_engine") as engine:
                with self.assertRaisesRegex(ValueError, message):
                    current.verify(self.repo, compiler="unavailable")
                engine.assert_not_called()
        finally:
            target.write_bytes(saved)

    def test_device_and_ml_use_same_authenticator(self):
        self.assertIs(current.authenticate_handoff, policy.authenticate_handoff)

    def test_current_pr22_gate_and_numerical_engine_pass(self):
        report = current.verify(self.repo, compiler=os.environ.get("CC", "gcc"))
        self.assertEqual(report["status"], "WEEK4_CURRENT_CHECKS_PASS")
        self.assertEqual(report["numerical_verification"]["golden_cases_bitwise"], 220)
        self.assertEqual(len(report["handoff_authentication"]["verified_current_source_updates"]), 3)
        self.assertFalse(report["historical_numerical_engine"]["current_checkout_is_historical_snapshot"])

    def test_original_r4_current_gate_passes(self):
        saved = {name: (self.repo/name).read_bytes() for name in policy.PR22_R4_SOURCE_HASHES}
        try:
            for name in saved:
                (self.repo/name).write_bytes(self.original[name])
            _, _, proof = current.authenticate_handoff(self.repo)
            self.assertEqual(proof["verified_current_source_updates"], [])
        finally:
            for name, raw in saved.items():
                (self.repo/name).write_bytes(raw)

    def test_each_current_source_mutation_rejected_before_engine(self):
        for row in self.manifest["source_files"]:
            with self.subTest(path=row["path"]):
                raw = (self.repo/row["path"]).read_bytes()
                self.rejects_before_engine(row["path"], raw+b"\n# unauthorized\n", "Pinned ML source mismatch")

    def test_each_partial_update_rejected_before_engine(self):
        for name in policy.PR22_R4_SOURCE_HASHES:
            with self.subTest(path=name):
                self.rejects_before_engine(name, self.original[name], "Incomplete verified PR22")

    def test_swapped_verified_sources_rejected(self):
        left, right = list(policy.PR22_R4_SOURCE_HASHES)[:2]
        self.rejects_before_engine(left, (self.repo/right).read_bytes(), "Pinned ML source mismatch")

    def test_manifest_and_payload_changes_rejected_before_engine(self):
        for name in (policy.R4+"/manifest.json", policy.R3+"/manifest.json",
                     policy.PACKAGE+"/manifest.json", policy.R4+"/model_graph.json",
                     policy.PACKAGE+"/models/tail_0.onnx", policy.R3+"/firmware/head_parameters.h"):
            with self.subTest(path=name):
                self.rejects_before_engine(name, (self.repo/name).read_bytes()+b"tamper", "mismatch")

    def test_wrong_anchor_rejected_before_engine(self):
        with patch.object(current, "run_historical_engine") as engine:
            with self.assertRaisesRegex(ValueError, "trust anchor"):
                current.verify(self.repo, "0"*64)
            engine.assert_not_called()

    def test_historical_proof_does_not_certify_current_mutation(self):
        name = "ml/scripts/verify_week3_sv2.py"
        target = self.repo/name
        saved = target.read_bytes()
        try:
            target.write_bytes(saved+b"\n# unauthorized current change\n")
            _, _, proof = current.authenticate_handoff(self.repo, source_mode="historical")
            self.assertEqual(proof["historical_source_commit"], policy.SOURCE_COMMITS["r4"])
            self.assertNotIn("current_source_revision", proof)
            with self.assertRaisesRegex(ValueError, "Pinned ML source mismatch"):
                current.authenticate_handoff(self.repo)
        finally:
            target.write_bytes(saved)


if __name__ == "__main__":
    unittest.main(verbosity=2)
