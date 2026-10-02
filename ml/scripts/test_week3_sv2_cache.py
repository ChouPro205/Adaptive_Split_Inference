"""Regression for runtime caches; fixtures are disposable, release bytes immutable.

Run with the project interpreter: python -B ml/scripts/test_week3_sv2_cache.py
The frozen-loader test uses local v1 when available and otherwise reports SKIP.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import importlib.util
import json
import marshal
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import torch

from week3_common import load_model, sha
from week3_sv2_common import SCRIPTS, authenticate, inventory
from verify_week3_sv2 import verify

SCRIPTS_ROOT = Path(__file__).resolve().parent
V1 = SCRIPTS_ROOT.parent / "artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1"


def python(code, cwd, *args):
    env = os.environ.copy()
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    env.pop("PYTHONPYCACHEPREFIX", None)
    return subprocess.run([sys.executable, "-c", code, *map(str, args)],
                          cwd=cwd, env=env, check=True, capture_output=True, text=True)


class CacheRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="week3_cache_")
        self.addCleanup(self.tmp.cleanup)
        self.package = Path(self.tmp.name) / "package"
        self.package.mkdir()
        for directory, name in (("scripts", "week3_common"), ("model", "mitdb_baseline_model")):
            root = self.package / directory
            root.mkdir()
            (root / (name + ".py")).write_bytes(b"value = 7\n")
        self.files = inventory(self.package)
        (self.package / "manifest.json").write_text(json.dumps({"files": self.files}), encoding="utf-8")
        self.expected = sha(self.package / "manifest.json")

    def caches(self):
        # Actual Python imports, with bytecode writes explicitly enabled in child.
        python("import sys; sys.dont_write_bytecode=False; "
               "sys.path[:0]=['scripts','model']; import week3_common,mitdb_baseline_model",
               self.package)
        paths = list(self.package.rglob("*.pyc"))
        self.assertEqual(len(paths), 2)
        return paths

    def test_clean_then_real_caches_after_manifest_and_repeat(self):
        self.assertEqual(authenticate(self.package, self.expected)["files"], self.files)
        self.caches()
        for _ in range(3):
            self.assertEqual(authenticate(self.package, self.expected)["files"], self.files)

    def test_preexisting_caches_and_other_cpython_versions(self):
        for cache in self.caches():
            shutil.copyfile(cache, cache.with_name(cache.name.replace(sys.implementation.cache_tag, "cpython-312")))
            shutil.copyfile(cache, cache.with_name(cache.name.replace(".pyc", ".opt-1.pyc")))
        self.assertEqual(inventory(self.package), self.files)
        self.assertEqual(authenticate(self.package, self.expected)["files"], self.files)

    def test_regular_extra_file_rejected(self):
        (self.package / "extra.txt").write_bytes(b"extra\n")
        with self.assertRaisesRegex(ValueError, "Inventory differs"):
            authenticate(self.package, self.expected)

    def test_unrecognized_cache_contents_rejected(self):
        paths = ["scripts/__pycache__/extra.txt", "model/__pycache__/orphan.cpython-311.pyc",
                 "scripts/__pycache__/week3_common.pyc", "other/__pycache__/week3_common.cpython-311.pyc",
                 "scripts/week3_common.pyc", "scripts/__pycache__/week3_common.cpython-311.opt-9.pyc"]
        for relative in paths:
            with self.subTest(path=relative):
                p = self.package / relative
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"\xcb\x00")
                with self.assertRaises(ValueError) as exc:
                    authenticate(self.package, self.expected)
                self.assertIn(relative, str(exc.exception))
                self.assertIn("unexpected binary", str(exc.exception))
                p.unlink()

    def test_extra_source_cannot_authorize_an_extra_cache(self):
        source = self.package / "scripts/extra.py"
        source.write_bytes(b"value = 8\n")
        cache = source.parent / "__pycache__/extra.cpython-311.pyc"
        cache.parent.mkdir()
        cache.write_bytes(b"\xcb")
        with self.assertRaisesRegex(ValueError, "scripts/__pycache__/extra"):
            inventory(self.package)

    def test_mutation_missing_and_external_hash_rejected(self):
        source = self.package / "scripts/week3_common.py"
        original = source.read_bytes()
        source.write_bytes(b"value = 9\n")
        with self.assertRaisesRegex(ValueError, "File hash/size mismatch"):
            authenticate(self.package, self.expected)
        source.write_bytes(original)
        self.caches()
        source.unlink()
        with self.assertRaisesRegex(ValueError, "File hash/size mismatch"):
            authenticate(self.package, self.expected)
        with self.assertRaisesRegex(ValueError, "Manifest SHA-256 mismatch"):
            authenticate(self.package, "0" * 64)

    def test_symlinks_rejected_before_cache_exception(self):
        target = self.package / "scripts/week3_common.py"
        link = target.parent / "__pycache__/week3_common.cpython-311.pyc"
        link.parent.mkdir()
        try:
            link.symlink_to(target)
        except OSError as exc:
            self.skipTest(f"OS disallows symlink creation: {exc}")
        with self.assertRaisesRegex(ValueError, "Package symlinks forbidden.*__pycache__"):
            inventory(self.package)
        link.unlink()
        # A directory symlink must be rejected too, not silently skipped.
        link = self.package / "model/__pycache__"
        link.symlink_to(self.package / "scripts", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Package symlinks forbidden"):
            inventory(self.package)

    def test_cache_symlink_guard_without_os_privilege(self):
        cache = self.caches()[0]
        original = Path.is_symlink
        # Exercise production ordering even on Windows without symlink privilege.
        with patch.object(Path, "is_symlink", lambda p: p == cache or original(p)):
            with self.assertRaisesRegex(ValueError, "Package symlinks forbidden"):
                inventory(self.package)

    def test_entrypoints_without_B_do_not_write_cache(self):
        for name in SCRIPTS:
            shutil.copyfile(SCRIPTS_ROOT / name, self.package / "scripts" / name)
        for entry in ("verify_week3_sv2.py", "test_week3_sv2.py", "export_week3_sv2.py"):
            with self.subTest(entry=entry):
                env = os.environ.copy()
                env.pop("PYTHONDONTWRITEBYTECODE", None)
                env.pop("PYTHONPYCACHEPREFIX", None)
                result = subprocess.run([sys.executable, str(self.package / "scripts" / entry), "--help"],
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)
                self.assertEqual(list(self.package.rglob("*.pyc")), [])

    @unittest.skipUnless(V1.is_dir(), "Local immutable v1 unavailable for full regression")
    def test_real_v1_cache_reproduces_bug_then_full_verifier_repeats(self):
        fixture = Path(self.tmp.name) / V1.name
        shutil.copytree(V1, fixture)
        expected = "a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6"
        self.assertEqual(sha(fixture / "manifest.json"), expected)
        # Execute ORIGINAL bundled imports on a copy. This creates actual script
        # and model caches and reproduces the pre-fix UnicodeDecodeError.
        result = python("import sys; sys.dont_write_bytecode=False; "
                        "sys.path[:0]=['scripts','model']; "
                        "import week3_sv2_common,mitdb_baseline_model; from pathlib import Path; "
                        "\ntry: week3_sv2_common.inventory(Path('.'))"
                        "\nexcept UnicodeDecodeError: print('ORIGINAL_UTF8_CRASH')"
                        "\nelse: raise RuntimeError('Original inventory did not reproduce')", fixture)
        self.assertIn("ORIGINAL_UTF8_CRASH", result.stdout)
        self.assertTrue(list((fixture / "scripts/__pycache__").glob("*.pyc")))
        self.assertTrue(list((fixture / "model/__pycache__").glob("*.pyc")))
        before = {str(p.relative_to(fixture)): sha(p) for p in fixture.rglob("*") if p.is_file()}
        for _ in range(2):
            completed = subprocess.run([sys.executable, str(SCRIPTS_ROOT / "verify_week3_sv2.py"),
                                        "--package", str(fixture), "--expected-manifest-sha256", expected],
                                       capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertEqual(report["status"], "SV2_FP32_REFERENCE_CHECKS_PASS")
            self.assertEqual(report["comparisons"], 200)
        self.assertEqual(before, {str(p.relative_to(fixture)): sha(p) for p in fixture.rglob("*") if p.is_file()})
        # Separate environment fault: unchanged production gate rejects 3.12.
        from week3_sv2_common import versions
        wrong = {**versions(), "python": "3.12.0"}
        with patch("verify_week3_sv2.versions", return_value=wrong):
            with self.assertRaisesRegex(ValueError, "Runtime versions differ"):
                verify(fixture, expected)

    @unittest.skipUnless(V1.is_dir(), "Local immutable v1 unavailable for frozen-model regression")
    def test_frozen_loader_ignores_valid_header_forged_cache(self):
        source = self.package / "model/mitdb_baseline_model.py"
        shutil.copyfile(V1 / "model/mitdb_baseline_model.py", source)
        checkpoint = V1 / "model/checkpoint.pt"
        clean, _ = load_model(checkpoint, source)
        marker = self.package / "executed_untrusted_cache"
        evil = compile(f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise RuntimeError('forged cache executed')\n",
                       str(source), "exec")
        cache = Path(importlib.util.cache_from_source(str(source)))
        cache.parent.mkdir(exist_ok=True)
        stat = source.stat()
        cache.write_bytes(importlib.util.MAGIC_NUMBER + struct.pack("<III", 0, int(stat.st_mtime), stat.st_size)
                          + marshal.dumps(evil))
        # Prove the forged timestamp/size header is accepted even with -B-like
        # suppression of writes. A conventional loader executes the evil code.
        python("import sys,importlib.util; sys.dont_write_bytecode=True; "
               "s=importlib.util.spec_from_file_location('probe',sys.argv[1]); "
               "m=importlib.util.module_from_spec(s); "
               "\ntry: s.loader.exec_module(m)\nexcept RuntimeError as e: assert str(e)=='forged cache executed'",
               self.package, source)
        self.assertTrue(marker.is_file())
        marker.unlink()
        loaded, _ = load_model(checkpoint, source)
        self.assertFalse(marker.exists())
        for name, tensor in clean.state_dict().items():
            self.assertTrue(torch.equal(tensor, loaded.state_dict()[name]), name)
        with torch.inference_mode():
            x = torch.zeros(1, 1, 360)
            self.assertTrue(torch.equal(clean(x), loaded(x)))
        self.assertFalse(any(m.training for m in loaded.modules()))


if __name__ == "__main__":
    unittest.main(verbosity=2)