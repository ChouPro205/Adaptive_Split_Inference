"""Exercise ZIP authentication, atomic preflight and immutable revision protection."""
from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from release_week4 import hydrate, release
from week3_common import sha


class ReleaseRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="week4_release_test_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.checkout = self.root / "checkout"
        self.checkout.mkdir()
        self.archive = self.root / "release.zip"
        self.names = ["ml/results/week4-r3/a.json", "ml/results/week4-r3/b.json"]
        with zipfile.ZipFile(self.archive, "w") as zipped:
            for name in self.names:
                zipped.writestr(name, b"{}\n")
        import hashlib
        self.files = [{"path": name, "sha256": hashlib.sha256(b"{}\n").hexdigest(),
                       "file_size_bytes": 3} for name in self.names]

    def hydrate(self, **overrides):
        args = dict(repo=self.checkout, archive=self.archive, expected_sha256=sha(self.archive),
                    expected_size=self.archive.stat().st_size, files=self.files)
        args.update(overrides)
        hydrate(**args)

    def test_authenticated_hydration_can_repeat_without_overwrite(self):
        self.hydrate()
        self.hydrate()
        for name in self.names:
            self.assertEqual((self.checkout / name).read_bytes(), b"{}\n")

    def test_wrong_zip_hash_and_size_rejected_before_write(self):
        for args in ({"expected_sha256": "0" * 64}, {"expected_size": 1}):
            with self.assertRaisesRegex(ValueError, "ZIP hash/size mismatch"):
                self.hydrate(**args)
        self.assertEqual(list(self.checkout.rglob("*")), [])

    def test_rehashed_member_and_extra_inventory_rejected(self):
        with zipfile.ZipFile(self.archive, "w") as zipped:
            zipped.writestr(self.names[0], b"tampered")
            zipped.writestr(self.names[1], b"{}\n")
        with self.assertRaisesRegex(ValueError, "ZIP member differs"):
            self.hydrate()
        with zipfile.ZipFile(self.archive, "a") as zipped:
            zipped.writestr("extra", b"unlisted")
        with self.assertRaisesRegex(ValueError, "ZIP inventory differs"):
            self.hydrate()
        self.assertEqual(list(self.checkout.rglob("*")), [])

    def test_existing_checkout_mismatch_never_overwritten_or_partially_hydrated(self):
        existing = self.checkout / self.names[1]
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b"trusted checkout")
        with self.assertRaisesRegex(ValueError, "refusing overwrite"):
            self.hydrate()
        self.assertEqual(existing.read_bytes(), b"trusted checkout")
        self.assertFalse((self.checkout / self.names[0]).exists())

    def test_unsafe_path_and_duplicate_receipt_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate release inventory"):
            self.hydrate(files=[*self.files, self.files[0]])
        with zipfile.ZipFile(self.archive, "w") as zipped:
            zipped.writestr("../escape", b"{}\n")
        with self.assertRaisesRegex(ValueError, "Unsafe package path"):
            self.hydrate(files=[{**self.files[0], "path": "../escape"}])
        self.assertFalse((self.root / "escape").exists())

    def test_existing_revision_rejected_before_any_mutation(self):
        marker = self.checkout / "ml/provenance/week4-r2/keep.txt"
        marker.parent.mkdir(parents=True)
        marker.write_bytes(b"immutable")
        with self.assertRaisesRegex(ValueError, "Release revision exists"):
            release(self.checkout, "unavailable", "r2")
        self.assertEqual(marker.read_bytes(), b"immutable")
        self.assertFalse((self.checkout / "ml/results").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
