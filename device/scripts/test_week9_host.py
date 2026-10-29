#!/usr/bin/env python3
"""Host tests of the week 9 firmware modules and laptop tools (no dongle).

1. Plan (W9-D4): week9_common.plan_splits() (splitmix64 known-answer, every round a permutation,
   50 cycles per split) equals plan.csv, the generated week9_plan.h compiled into
   device/week9/host_test/dev_shim.c, and WEEK9_PLAN_SHA256.
2. q/scale (W9-D6): dev_shim.c + week7/head_fast.c + week5/quantization.c (gcc on PATH or CC, -O2
   -ffp-contract=off -fno-fast-math, the steps of dev_cycle.c dev_head()) on the 50 samples at every
   s equal refs.csv; refs.csv shapes/bytes equal tensor_sizes.csv and s=2 equals the W8-D3 samples.csv.
3. check_week9.py verify/session PASS on host-made captures and FAIL on a changed q hash, a missing VQ
   line, a wrong device plan digest, a DWT mean outside the rule, a reordered cycle, a failed cycle and
   wrong payload bytes. With --week8-build, check_week9_build.py FAILS on a week 8 radio image.
Host evidence only: not MCU evidence.
Run: device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\test_week9_host.py --samples <W8-D3 dir>
     --plan <plan dir> --refs <refs dir> [--week8-build <week 8 build report dir>]
"""
from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_week9  # noqa: E402
import generate_week9_refs as gen_refs  # noqa: E402
import week9_common as w9  # noqa: E402

w8 = w9.w8
TMP = Path(tempfile.mkdtemp(prefix="week9_host_"))
SAMPLES: Path | None = None
PLAN: Path | None = None
REFS: Path | None = None
WEEK8_BUILD: Path | None = None


class Plan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = gen_refs.build_shim(TMP, SAMPLES, PLAN)
        cls.plan = w9.load_plan(PLAN)

    def test_splitmix64_known_answer(self):
        # Reference outputs of splitmix64 seeded with 0 (Vigna's splitmix64.c).
        state, out = 0, []
        for _ in range(3):
            state, x = w9._splitmix64(state)
            out.append(x)
        self.assertEqual(out, [0xE220A8397B1DCDAF, 0x6E789E6AA1B965F4, 0x06C45D188009454F])

    def test_plan_properties(self):
        splits = w9.plan_splits()
        self.assertEqual(len(splits), w9.CYCLES)
        for k in range(w9.ROUNDS):
            self.assertEqual(sorted(splits[11 * k:11 * k + 11]), list(range(11)), k)
        self.assertEqual([splits.count(s) for s in range(11)], [50] * 11)
        self.assertNotEqual(splits[:11], list(range(11)))
        self.assertNotEqual(w9.plan_splits(seed=w9.PLAN_SEED + 1), splits)
        self.assertEqual(w9.plan_sha256(splits), w9.PLAN_SHA256)

    def test_plan_csv_and_c_header_equal_generator(self):
        splits = w9.plan_splits()
        self.assertEqual(list(self.plan.rows), w9.plan_rows(splits))
        self.assertEqual(self.lib.shim_plan_cycles(), w9.CYCLES)
        self.assertEqual(self.lib.shim_plan_rounds(), w9.ROUNDS)
        self.assertEqual(self.lib.shim_plan_seed(), w9.PLAN_SEED)
        self.assertEqual(self.lib.shim_plan_sha256().decode(), w9.PLAN_SHA256)
        c_splits = list(ctypes.string_at(self.lib.shim_plan_splits(), w9.CYCLES))
        self.assertEqual(c_splits, splits)

    def test_load_plan_rejects_changed_csv(self):
        bad = TMP / "plan_bad"
        bad.mkdir()
        for name in ("manifest.json", "week9_plan.h"):
            (bad / name).write_bytes((PLAN / name).read_bytes())
        text = (PLAN / "plan.csv").read_text(encoding="utf-8").replace("\n0,0,0,3\n", "\n0,0,0,4\n", 1)
        (bad / "plan.csv").write_text(text, encoding="utf-8", newline="\n")
        with self.assertRaises(ValueError):
            w9.load_plan(bad)


class References(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.set = w8.load_set(SAMPLES)
        cls.refs = w9.load_refs(REFS, cls.set)
        (TMP / "refs").mkdir()
        cls.lib = gen_refs.build_shim(TMP / "refs", SAMPLES)

    def test_shim_550_equal_refs(self):
        for n in range(w9.ROUNDS):
            for s in range(w9.SPLITS):
                c, length, q, scale = gen_refs.head_quant(self.lib, n, s)
                r = self.refs[(n, s)]
                self.assertEqual((c, length, len(q) + len(scale)), (r.channels, r.length, r.bytes_payload))
                self.assertEqual((w9.sha256_hex(q), w9.sha256_hex(scale)), (r.q_sha256, r.scale_sha256), (n, s))

    def test_payload_bytes_per_split(self):
        want = {0: 362, 1: 5792, 2: 2912, 3: 5824, 4: 2944, 5: 4416, 6: 2256, 7: 3008, 8: 1536, 9: 96, 10: 15}
        self.assertEqual({s: self.refs[(0, s)].bytes_payload for s in range(11)}, want)

    def test_s2_equal_week8(self):
        for n in range(w9.ROUNDS):
            sample = self.set.samples[n]
            self.assertEqual((self.refs[(n, 2)].q_sha256, self.refs[(n, 2)].scale_sha256),
                             (sample.q_sha256, sample.scale_sha256))


def verify_capture(refs: dict, set_sha: str, plan_digest: str = w9.PLAN_SHA256, td_scale: float = 1.0) -> list:
    """The lines a dev-usb image prints for STATUS, VERIFY ALL and TDEV ALL, from the host references
    (TD head = week 7 BENCH FAST x td_scale)."""
    lines = [f"READY WEEK9 build=host variant=dev-usb kernel=FAST rounds=50 splits=11 cycles=550 samples=50 "
             f"set_sha256={set_sha} plan_sha256={w9.PLAN_SHA256} plan_device_sha256={plan_digest} "
             f"plan_ok={int(plan_digest == w9.PLAN_SHA256)}"]
    for s in range(w9.SPLITS):
        for n in range(w9.ROUNDS):
            r = refs[(n, s)]
            lines.append(f"VQ n={n} id={r.sample_id} s={s} C={r.channels} L={r.length} bytes={r.bytes_payload} "
                         f"q_sha256={r.q_sha256} scale_sha256={r.scale_sha256}")
    lines.append(f"VERIFY END kernel=FAST samples=50 splits=ALL set_sha256={set_sha}")
    bench = w9.bench_fast_ms()
    for s in range(w9.SPLITS):
        head = round(bench[s] * td_scale * w9.CPU_HZ / 1000.0)
        for n in range(w9.ROUNDS):
            lines.append(f"TD s={s} n={n} head_cyc={head} quant_cyc=900 total_cyc={head + 920}")
        lines.append(f"TDSUM s={s} runs=50 warmup=20 irq=locked cpu_hz=64000000 head_min={head} head_max={head} "
                     f"head_mean_x100={head * 100} quant_mean_x100=90000 total_min={head + 920} "
                     f"total_max={head + 920} total_mean_x100={(head + 920) * 100}")
    lines.append("TDEV END kernel=FAST splits=ALL")
    return [(i, t) for i, t in enumerate(lines)]


def session_capture(refs: dict, first: int = 0, count: int = w9.CYCLES, rows=None) -> list:
    rows = rows if rows is not None else w9.plan_rows(w9.plan_splits())[first:first + count]
    lines = [f"SESSION BEGIN first={first} count={count} gap_ms=0 plan_sha256={w9.PLAN_SHA256}"]
    for i, k, n, s in rows:
        r = refs[(n, s)]
        lines.append(f"CYCLE i={i} round={k} n={n} id={r.sample_id} s={s} bytes={r.bytes_payload} ctrl_cyc=12800 "
                     f"head_cyc={1000 + 64000 * s} quant_cyc=900 head_us={(1000 + 64000 * s) // 64} res=OK")
    lines.append(f"SESSION END first={first} count={count} ok={count} failed=0")
    return [(i, t) for i, t in enumerate(lines)]


class Checkers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.set = w8.load_set(SAMPLES)
        cls.refs = w9.load_refs(REFS, cls.set)

    def failed_verify(self, capture) -> list:
        return [k for k, ok in check_week9.check_verify(capture, self.set, self.refs)["checks"].items() if not ok]

    def failed_session(self, capture, first=0, count=w9.CYCLES) -> list:
        return [k for k, ok in check_week9.check_session(capture, self.refs, first, count)["checks"].items() if not ok]

    def test_verify_passes_host_capture(self):
        result = check_week9.check_verify(verify_capture(self.refs, self.set.set_sha256), self.set, self.refs)
        self.assertTrue(all(result["checks"].values()), result["checks"])
        self.assertEqual(len(result["t_dev_table"]), 11)

    def test_verify_rejects_changes(self):
        good = verify_capture(self.refs, self.set.set_sha256)
        q = self.refs[(5, 7)].q_sha256
        self.assertIn("q_scale_id_shape_bytes_equal_host_reference",
                      self.failed_verify([(i, t.replace(q, "0" * 64)) for i, t in good]))
        missing = [(i, t) for i, t in good if not t.startswith("VQ n=7 id=") or " s=3 " not in t]
        self.assertIn("vq_550_split_major_order", self.failed_verify(missing))
        self.assertIn("device_plan_digest_equal",
                      self.failed_verify(verify_capture(self.refs, self.set.set_sha256, "a" * 64)))
        self.assertEqual(self.failed_verify(verify_capture(self.refs, self.set.set_sha256, td_scale=1.03)),
                         ["tdev_head_within_rule_of_week7_bench_fast"])
        self.assertEqual(self.failed_verify(verify_capture(self.refs, self.set.set_sha256, td_scale=1.015)), [])

    def test_session_passes_plan(self):
        self.assertEqual(self.failed_session(session_capture(self.refs)), [])
        self.assertEqual(self.failed_session(session_capture(self.refs, 33, 22), 33, 22), [])

    def test_session_rejects_changes(self):
        rows = w9.plan_rows(w9.plan_splits())
        swapped = list(rows)
        swapped[3], swapped[4] = (3, 0, 0, swapped[4][3]), (4, 0, 0, swapped[3][3])
        self.assertIn("cycles_equal_plan_order", self.failed_session(session_capture(self.refs, rows=swapped)))
        good = session_capture(self.refs)
        failed = [(i, t.replace("res=OK", "res=HEAD") if i == 10 else t) for i, t in good]
        self.assertIn("all_cycles_ok", self.failed_session(failed))
        line = good[1][1]
        wrong = [(i, t.replace(" bytes=", " bytes=1", 1) if i == 1 else t) for i, t in good]
        self.assertNotEqual(wrong[1][1], line)
        self.assertIn("bytes_equal_tensor_sizes", self.failed_session(wrong))
        self.assertIn("cycles_equal_plan_order", self.failed_session(good[:-2] + good[-1:]))


class BuildChecker(unittest.TestCase):
    def test_week8_radio_image_fails(self):
        if WEEK8_BUILD is None:
            raise unittest.SkipTest("--week8-build not given")
        out = TMP / "week8_as_week9.json"
        code = subprocess.run([sys.executable, "-B", str(HERE / "check_week9_build.py"), "--build",
                               str(WEEK8_BUILD / "build"), "--variant", "dev", "--build-id", "x",
                               "--set-sha256", w8.SET_SHA256, "--plan-sha256", w9.PLAN_SHA256,
                               "--output", str(out)], capture_output=True).returncode
        self.assertEqual(code, 1)
        checks = json.loads(out.read_text(encoding="utf-8"))["checks"]
        for name in ("no_bt", "no_nvs", "no_radio_nonce_i2_code_linked", "variant_selected",
                     "plan_sha256_in_image", "week9_modules_compiled"):
            self.assertFalse(checks[name], name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory")
    parser.add_argument("--plan", type=Path, required=True, help="generate_week9_plan.py directory")
    parser.add_argument("--refs", type=Path, required=True, help="generate_week9_refs.py directory")
    parser.add_argument("--week8-build", type=Path, help="a build_week8.ps1 report directory (negative test)")
    args, rest = parser.parse_known_args()
    SAMPLES, PLAN, REFS = args.samples.resolve(), args.plan.resolve(), args.refs.resolve()
    WEEK8_BUILD = args.week8_build.resolve() if args.week8_build else None
    result = unittest.main(argv=[sys.argv[0], *rest], verbosity=2, exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
