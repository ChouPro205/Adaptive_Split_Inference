"""Exercise trusted R3/R4 compatibility and reject source/payload tampering."""
from __future__ import annotations

import copy
import hashlib
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


class R3ReportBindingRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Read the original committed evidence, never a potentially edited HEAD.
        cls.lf = subprocess.check_output([
            "git", "show", "efc0af72aeae3ef6ff872ad3cae19e6304899530:results/week4/week4_mcu_validation.json"
        ], cwd=REPO)
        if b"\r" in cls.lf:
            raise ValueError("Historical R3 fixture must contain only LF newlines")
        cls.crlf = cls.lf.replace(b"\n", b"\r\n")
        cls.expected_hashes = (
            "022a5172edd75c60826d27db16761df9d5236caaa1cad312c14ce59c1dd5ab21",
            "4a0342593270485b409465741a6c555659dc98b541c277b264d9727da4605a4d",
        )
        if tuple(hashlib.sha256(raw).hexdigest() for raw in (cls.lf, cls.crlf)) != cls.expected_hashes:
            raise ValueError("Historical R3 fixture does not reproduce both reviewed anchors")

    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="sv1-r3-report-")
        self.addCleanup(scratch.cleanup)
        self.repo = Path(scratch.name)
        self.report = self.repo / "results/week4/week4_mcu_validation.json"
        self.report.parent.mkdir(parents=True)
        self.provenance = json.loads(self.lf)["provenance"]
        for name in self.provenance["compiled_source_sha256"]:
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / name, target)
        for name in self.provenance["generated_header_sha256"]:
            target = self.repo / "device/generated" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / "device/generated" / name, target)

    def check_report(self, raw, expected):
        self.report.write_bytes(raw)
        proof = handoff.accepted_r3_provenance(self.repo)
        self.assertEqual(proof["accepted_report_sha256"], expected)
        self.assertEqual(proof["measurement_revision"], "r3")
        self.assertEqual(proof["validated_at"], self.provenance["validated_at"])
        self.assertEqual(proof["elf_sha256"], self.provenance["elf_sha256"])

    def test_historical_lf_report_passes(self):
        self.check_report(self.lf, self.expected_hashes[0])

    def test_same_historical_crlf_report_passes(self):
        self.check_report(self.crlf, self.expected_hashes[1])

    def test_changed_report_content_rejected_for_both_newlines(self):
        changed = json.loads(self.lf)
        changed["provenance"]["validated_at"] = "2026-10-03T00:00:00+07:00"
        lf = json.dumps(changed, indent=2).encode("utf-8") + b"\n"
        for raw in (lf, lf.replace(b"\n", b"\r\n")):
            with self.subTest(crlf=b"\r\n" in raw):
                self.report.write_bytes(raw)
                with self.assertRaisesRegex(ValueError, "Accepted R3 report anchor mismatch"):
                    handoff.accepted_r3_provenance(self.repo)

    def test_other_byte_representations_rejected(self):
        for raw in (self.lf + b" ", self.lf.replace(b"\n", b"\r\n", 1),
                    self.lf.replace(b"\n", b"\r"), b"\xef\xbb\xbf" + self.lf):
            with self.subTest(sha256=hashlib.sha256(raw).hexdigest()):
                self.report.write_bytes(raw)
                with self.assertRaisesRegex(ValueError, "Accepted R3 report anchor mismatch"):
                    handoff.accepted_r3_provenance(self.repo)


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
        cls.r4_git_blobs = {entry["path"]: subprocess.check_output(
            ["git", "show", f"89109fd352d84a5fe0815d7e045e52538de7bad8:{entry['path']}"], cwd=REPO)
            for entry in cls.r4["source_files"]}
        cls.pr22_git_blobs = {name: subprocess.check_output(
            ["git", "show", f"add8503d58c6f707a35b4502bf98aff91109c1cd:{name}"], cwd=REPO)
            for name in ("ml/scripts/verify_week3_sv2.py", "ml/scripts/test_week3_sv2.py",
                         "ml/scripts/test_week3_sv2_cache.py")}

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
            self.assertIn(commit, handoff.SOURCE_COMMITS.values())
            blobs = self.git_blobs if commit == handoff.SOURCE_COMMITS["r3"] else self.r4_git_blobs
            return blobs[name]
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

    def test_pr22_update_matches_independent_historical_hashes(self):
        # Fixed expectations from independently reviewed old/new Git blobs,
        # not computed from the loader's allowlist or current checkout.
        expected = {
            "ml/scripts/verify_week3_sv2.py": (
                "b4c9562ee74c4922fd6180bc9a1a85ffc8a44871fd45ed87610728f2e31230ce",
                "c783c81a12439618c3ede435b495f7a2e605bc216dc9efa1fe04ecc9f35e31cb"),
            "ml/scripts/test_week3_sv2.py": (
                "c6bad027185bf63c280dc9abc2c9e9a96d809eabd6e42853a7b2cbd732b7fda6",
                "215e11a614986cd2fbacb67ac8ed2fd4711e8525180cfab28a5a8ec176ec7041"),
            "ml/scripts/test_week3_sv2_cache.py": (
                "9c7a2b6cdba237145ad127a45e5938e7d657b20caa1faaafbf7f5e885232b9b4",
                "7d448049234882f159401d0d1d5dfc703309d207730d01d4661a9c51bdb87f0f"),
        }
        self.assertEqual(handoff.PR22_R4_SOURCE_HASHES, expected)
        for name, hashes in expected.items():
            with self.subTest(path=name):
                actual = (handoff.source_hash(self.r4_git_blobs[name]),
                          handoff.source_hash(self.pr22_git_blobs[name]))
                self.assertEqual(actual, hashes)
                self.assertEqual((self.repo/name).read_bytes(), self.pr22_git_blobs[name])
        _, _, proof = handoff.authenticate_handoff(self.repo)
        updates = {row["path"]: row for row in proof["verified_current_source_updates"]}
        self.assertEqual(set(updates), set(expected))
        self.assertEqual(proof["current_source_manifest_sha256"], handoff.R4_MANIFEST)
        for name, row in updates.items():
            self.assertEqual(row["r4_manifest_sha256"], expected[name][0])
            self.assertEqual(row["current_source_sha256"], expected[name][1])
            self.assertEqual(row["reviewed_source_commit"], "add8503d58c6f707a35b4502bf98aff91109c1cd")
            self.assertEqual(row["reviewed_merge_commit"], "e6d3e8cc40323227d0f15a4bb4091957f2498744")

    def test_original_r4_sources_still_authenticate(self):
        saved = {name: (self.repo/name).read_bytes() for name in self.pr22_git_blobs}
        try:
            for name in saved:
                (self.repo/name).write_bytes(self.r4_git_blobs[name])
            _, _, proof = handoff.authenticate_handoff(self.repo)
            self.assertEqual(proof["verified_current_source_updates"], [])
            self.assertEqual(proof["current_source_bindings_checked"], 21)
        finally:
            for name, raw in saved.items():
                (self.repo/name).write_bytes(raw)

    def test_partial_pr22_source_update_rejected(self):
        for name in self.pr22_git_blobs:
            target = self.repo/name
            raw = target.read_bytes()
            try:
                target.write_bytes(self.r4_git_blobs[name])
                with self.subTest(path=name), self.assertRaisesRegex(ValueError, "Incomplete verified PR22"):
                    handoff.authenticate_handoff(self.repo)
            finally:
                target.write_bytes(raw)

    def test_pr22_sources_cannot_replace_historical_r4(self):
        for name, new in self.pr22_git_blobs.items():
            old = self.r4_git_blobs[name]
            try:
                self.r4_git_blobs[name] = new
                with self.subTest(path=name), self.assertRaisesRegex(ValueError, "r4 historical"):
                    handoff.check_sources(self.repo, self.r4, "r4", historical=True)
            finally:
                self.r4_git_blobs[name] = old

    def test_pr22_exception_cannot_repin_original_manifest(self):
        for name in self.pr22_git_blobs:
            for digest in ("0"*64, handoff.source_hash(self.pr22_git_blobs[name])):
                changed = copy.deepcopy(self.r4)
                next(row for row in changed["source_files"] if row["path"]==name)["sha256"] = digest
                with self.subTest(path=name, digest=digest), self.assertRaisesRegex(ValueError, "Unsupported verified source update binding"):
                    handoff.check_sources(self.repo, changed, "r4", historical=False)

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
