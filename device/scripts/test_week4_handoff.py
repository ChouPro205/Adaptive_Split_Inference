"""Exercise trusted R3/R4 compatibility and reject source/payload tampering."""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import week4_handoff as handoff
from generate_week4_inputs import generate
from verify_week4_host import validate_reuse

REPO = Path(__file__).resolve().parents[2]


class HandoffRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory(prefix="sv1-r3-r4-")
        cls.repo = Path(cls.scratch.name)
        for name in (handoff.R3, handoff.R4, handoff.PACKAGE):
            shutil.copytree(REPO / name, cls.repo / name)
        cls.r3 = json.loads((cls.repo / handoff.R3 / "manifest.json").read_text())
        cls.r4 = json.loads((cls.repo / handoff.R4 / "manifest.json").read_text())
        for entry in cls.r4["source_files"]:
            target = cls.repo / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / entry["path"], target)
        cls.git_blobs = {entry["path"]: subprocess.check_output(
            ["git", "show", f"{handoff.SOURCE_COMMITS['r3']}:{entry['path']}"], cwd=REPO)
            for entry in cls.r3["source_files"]}

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def setUp(self):
        # Supply actual blobs of the fixed trusted commit to fixture-only reads.
        # Current checkout bytes and all manifests/payloads still authenticate.
        def read_blob(command, cwd):
            self.assertEqual(Path(cwd), self.repo)
            self.assertEqual(command[:2], ["git", "show"])
            commit, name = command[2].split(":", 1)
            self.assertEqual(commit, handoff.SOURCE_COMMITS["r3"])
            return self.git_blobs[name]
        self.blob_patch = patch("week4_handoff.subprocess.check_output", side_effect=read_blob)
        self.blob_patch.start()
        self.addCleanup(self.blob_patch.stop)

    def test_current_r4_historical_r3_and_generated_bytes(self):
        _, _, proof = handoff.authenticate_handoff(self.repo)
        self.assertEqual(proof["historical_r3_source_bindings_checked"], len(self.r3["source_files"]))
        self.assertEqual(proof["current_source_bindings_checked"], len(self.r4["source_files"]))
        self.assertEqual(proof["r3_r4_identical_payload_files"], len(self.r3["files"]))
        output = self.repo / "generated-test"
        generate(self.repo, generated_dir=output)
        for name in ("week4_inputs.h", "week4_graph.h"):
            self.assertEqual((output/name).read_bytes(), (REPO/"device/generated"/name).read_bytes())

    def test_every_current_source_binding_rejects_tamper(self):
        for entry in self.r4["source_files"]:
            with self.subTest(path=entry["path"]):
                target = self.repo/entry["path"]
                raw = target.read_bytes()
                try:
                    target.write_bytes(raw+b"\n# tampered\n")
                    with self.assertRaisesRegex(ValueError, "Pinned ML source mismatch"):
                        handoff.authenticate_handoff(self.repo)
                finally:
                    target.write_bytes(raw)

    def test_every_historical_source_binding_rejects_tamper(self):
        for name in self.git_blobs:
            with self.subTest(path=name):
                raw = self.git_blobs[name]
                try:
                    self.git_blobs[name] = raw+b"\n# tampered\n"
                    with self.assertRaisesRegex(ValueError, "r3 historical"):
                        handoff.authenticate_handoff(self.repo)
                finally:
                    self.git_blobs[name] = raw

    def test_wrong_anchor_and_unknown_revision(self):
        for revision, anchor in (("r4", handoff.WEEK4_MANIFEST), ("r3", handoff.R4_MANIFEST), ("r4", "0"*64)):
            with self.subTest(revision=revision, anchor=anchor), self.assertRaisesRegex(ValueError, "trust anchor"):
                handoff.authenticate_handoff(self.repo, revision, anchor)
        with self.assertRaisesRegex(ValueError, "Unsupported source revision"):
            handoff.authenticate_handoff(self.repo, "r5")

    def test_tampered_manifest_rejected(self):
        for root in (handoff.R3, handoff.R4, handoff.PACKAGE):
            target = self.repo/root/"manifest.json"
            raw = target.read_bytes()
            try:
                target.write_bytes(raw+b" ")
                with self.assertRaisesRegex(ValueError, "Manifest anchor mismatch"):
                    handoff.authenticate_handoff(self.repo)
            finally:
                target.write_bytes(raw)

    def test_payload_tamper_rejected_before_compatibility(self):
        for root, name in ((handoff.R4,"model_graph.json"), (handoff.R3,"firmware/head_parameters.h"),
                           (handoff.PACKAGE,"golden/z_s2.npy")):
            target = self.repo/root/name
            raw = target.read_bytes()
            try:
                target.write_bytes(raw+b"tamper")
                with self.assertRaisesRegex(ValueError, "Pinned file mismatch"):
                    handoff.authenticate_handoff(self.repo)
            finally:
                target.write_bytes(raw)

    def test_scientific_and_source_binding_changes_rejected(self):
        changed = copy.deepcopy(self.r4)
        changed["files"][0]["sha256"] = "0"*64
        with self.assertRaisesRegex(ValueError, "scientific bindings differ"):
            handoff.check_payload_parity(self.repo, self.r3, changed)
        changed = copy.deepcopy(self.r4)
        changed["source_files"][0]["path"] = "ml/scripts/unknown.py"
        with self.assertRaisesRegex(ValueError, "source binding inventory"):
            handoff.check_payload_parity(self.repo, self.r3, changed)
        for field, value in (("source_git_commit", "1"*40), ("source_hash_policy", "raw")):
            changed = copy.deepcopy(self.r4)
            changed[field] = value
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                handoff.check_sources(self.repo, changed, "r4", historical=False)

    def test_current_r4_cannot_claim_current_r3(self):
        with self.assertRaisesRegex(ValueError, "r3 current"):
            handoff.authenticate_handoff(self.repo, "r3")

    def test_explicit_current_r3_uses_all_pinned_bindings(self):
        saved = {name:(self.repo/name).read_bytes() for name in self.git_blobs}
        try:
            for name, raw in self.git_blobs.items():
                (self.repo/name).write_bytes(raw)
            _, _, proof = handoff.authenticate_handoff(self.repo, "r3", handoff.WEEK4_MANIFEST)
            self.assertEqual(proof["current_source_revision"], "r3")
            self.assertEqual(proof["r3_r4_identical_payload_files"], 0)
        finally:
            for name, raw in saved.items():
                (self.repo/name).write_bytes(raw)

    def test_host_reuse_requires_complete_revision_and_hash_bindings(self):
        _, _, proof = handoff.authenticate_handoff(self.repo)
        sources = {"device/scripts/week4_handoff.py": "source-hash"}
        generated = {"generated/week4_graph.h": "generated-hash"}
        report = {"status": "PASS", "scope": "HOST_C_ONLY", "threshold_strict": 1e-3,
                  "primary_tensors": 220, "reverse_order_tensors": 220, "week3_p2_bitwise_samples": 20,
                  "week4_manifest_sha256": handoff.WEEK4_MANIFEST,
                  "all_split_manifest_sha256": handoff.ALL_SPLIT_MANIFEST,
                  "handoff_authentication": proof, "source_sha256": sources,
                  "generated_sha256": generated, "skips": []}
        validate_reuse(report, proof, sources, generated)
        for key, value in (("handoff_authentication", None), ("source_sha256", {}),
                           ("generated_sha256", {}), ("week4_manifest_sha256", handoff.R4_MANIFEST),
                           ("reverse_order_tensors", 219), ("threshold_strict", 1e-2)):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "stale or unsupported"):
                validate_reuse({**report, key:value}, proof, sources, generated)

    def test_measured_firmware_provenance_and_tampering(self):
        for name in ("results/week4/week4_mcu_validation.json", *json.loads(
                (REPO/"results/week4/week4_mcu_validation.json").read_text())["provenance"]["compiled_source_sha256"]):
            target = self.repo/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO/name, target)
        shutil.copytree(REPO/"device/generated", self.repo/"device/generated", dirs_exist_ok=True)
        provenance = handoff.accepted_r3_provenance(self.repo)
        self.assertEqual(provenance["measurement_revision"], "r3")
        self.assertIn("2026-10-02", provenance["validated_at"])
        for name in ("device/src/main_week4.c", "device/generated/week4_inputs.h",
                     "results/week4/week4_mcu_validation.json"):
            target = self.repo/name
            raw = target.read_bytes()
            try:
                target.write_bytes(raw+b"tamper")
                with self.assertRaises(ValueError):
                    handoff.accepted_r3_provenance(self.repo)
            finally:
                target.write_bytes(raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
