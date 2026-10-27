#!/usr/bin/env python3
"""Host tests of the week 8 firmware modules and laptop tools (no dongle).

1. The generated week8_inputs.h, compiled with device/week8/host_test/g2_shim.c + week7/head_fast.c +
   week5/quantization.c (gcc on PATH or CC, -O2 -ffp-contract=off -fno-fast-math, the firmware's
   pipeline_head() steps): q/scale SHA-256 of all 100 samples equal samples.csv, IDs and reference
   labels equal the set, the inputs reproduce WEEK8_SET_SHA256.
2. device/week8/g2_plan.h (session order W8-D1, label rule) equals week8_common.plan()/label().
3. week8_common requests: P0/P1 frames parse with contracts/i1v2_ref, P1 unprotects to q with the
   PUBLIC_TEST key, lengths per I1 v2; check_week8.py verify PASSES on a host-made capture and FAILS
   on a changed q hash, a missing sample, a changed request and another set SHA-256.
Host evidence only: not MCU, radio or KV260 evidence.
Run: device\\host\\.venv\\Scripts\\python.exe -B device\\scripts\\test_week8_host.py --samples <W8-D3 dir>
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import check_week8  # noqa: E402
import week7_common as w7  # noqa: E402
import week8_common as w8  # noqa: E402

WEEK7 = ROOT / "device" / "week7"
WEEK8 = ROOT / "device" / "week8"
TMP = Path(tempfile.mkdtemp(prefix="week8_host_"))
SAMPLES: Path | None = None


def build_shim() -> ctypes.CDLL:
    cc = os.environ.get("CC") or shutil.which("gcc")
    if not cc:
        raise unittest.SkipTest("gcc not found (set CC)")
    out = TMP / ("g2_shim.dll" if os.name == "nt" else "g2_shim.so")
    cmd = [cc, "-std=c11", "-O2", "-ffp-contract=off", "-fno-fast-math", "-shared", "-fPIC",
           "-Wall", "-Wextra", "-Werror", "-Wno-unknown-pragmas",
           "-I", str(WEEK8), "-I", str(WEEK7), "-I", str(ROOT / "device" / "src"),
           "-I", str(ROOT / "device" / "generated"), "-I", str(ROOT / "device" / "week5"),
           "-I", str(ROOT / "ml" / "results" / "week4-r3" / "firmware"), "-I", str(SAMPLES),
           "-o", str(out), str(WEEK8 / "host_test" / "g2_shim.c"), str(WEEK7 / "head_fast.c"),
           str(ROOT / "device" / "week5" / "quantization.c")]
    subprocess.run(cmd, check=True)
    lib = ctypes.CDLL(str(out))
    lib.shim_set_sha256.restype = ctypes.c_char_p
    lib.shim_sample_id.restype = ctypes.c_char_p
    lib.shim_sample_id.argtypes = [ctypes.c_uint]
    lib.shim_inputs.restype = ctypes.POINTER(ctypes.c_float)
    lib.shim_head_quant.argtypes = [ctypes.c_uint, ctypes.c_char_p, ctypes.c_uint, ctypes.c_char_p,
                                    ctypes.c_uint, ctypes.POINTER(ctypes.c_uint),
                                    ctypes.POINTER(ctypes.c_uint)]
    lib.shim_pair_sample.argtypes = [ctypes.c_uint, ctypes.c_uint]
    lib.shim_slot_is_p1.argtypes = [ctypes.c_uint, ctypes.c_uint]
    lib.shim_label.argtypes = [ctypes.POINTER(ctypes.c_float)]
    return lib


class Firmware(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.set = w8.load_set(SAMPLES)
        cls.lib = build_shim()

    def test_header_identity(self):
        self.assertEqual(self.lib.shim_sample_count(), w8.SAMPLE_COUNT)
        self.assertEqual(self.lib.shim_split(), w8.SPLIT)
        self.assertEqual(self.lib.shim_set_sha256().decode(), w8.SET_SHA256)
        for s in self.set.samples:
            self.assertEqual(self.lib.shim_sample_id(s.index).decode(), s.sample_id)
            self.assertEqual(self.lib.shim_reference_label(s.index), s.label_ref)

    def test_inputs_reproduce_set_sha256(self):
        raw = ctypes.string_at(self.lib.shim_inputs(), w8.SAMPLE_COUNT * 360 * 4)
        digest = hashlib.sha256("".join(s.sample_id + "\n" for s in self.set.samples).encode("utf-8"))
        digest.update(raw)
        self.assertEqual(digest.hexdigest(), w8.SET_SHA256)

    def test_q_scale_100_equal_samples_csv(self):
        q = ctypes.create_string_buffer(8192)
        scale = ctypes.create_string_buffer(256)
        c, length = ctypes.c_uint(), ctypes.c_uint()
        for s in self.set.samples:
            self.assertEqual(self.lib.shim_head_quant(s.index, q, 8192, scale, 256, ctypes.byref(c),
                                                      ctypes.byref(length)), 0)
            self.assertEqual((c.value, length.value), (self.set.channels, self.set.length))
            self.assertEqual(w8.sha256_hex(q.raw[:c.value * length.value]), s.q_sha256, s.index)
            self.assertEqual(w8.sha256_hex(scale.raw[:2 * c.value]), s.scale_sha256, s.index)

    def test_session_order_equals_plan(self):
        for first, count in ((0, 100), (97, 7), (250, 3)):
            got = [(2 * k + slot, first + k, self.lib.shim_pair_sample(first + k, 100),
                    "P1" if self.lib.shim_slot_is_p1(first + k, slot) else "P0")
                   for k in range(count) for slot in range(2)]
            self.assertEqual(got, w8.plan(first, count))
        session = w8.plan(0, 100)
        self.assertEqual(sorted(c[2] for c in session), sorted(list(range(100)) * 2))
        self.assertEqual([c[3] for c in session[:4]], ["P1", "P0", "P0", "P1"])
        self.assertEqual(sum(c[3] == "P1" for c in session), 100)

    def test_label_rule_equals_c(self):
        nan, inf = float("nan"), float("inf")
        cases = [s.logits for s in self.set.samples] + [
            (1, 1, 1, 1, 1), (0, 2, 2, 1, 0), (-inf, -inf, -1, -inf, -inf), (inf, 0, inf, 0, 0),
            (0, nan, 1, 0, 0), (-0.0, 0.0, -0.0, 0.0, 0.0), (-3, -2, -1, -1.5, -1)]
        for logits in cases:
            arr = (ctypes.c_float * 5)(*logits)
            c_label = self.lib.shim_label(arr)
            self.assertEqual(c_label, w8.label(tuple(arr)), logits)
        self.assertEqual(w8.label((0, nan, 1, 0, 0)), w8.NO_LABEL)
        self.assertEqual([w8.label(s.logits) for s in self.set.samples], [s.label_ref for s in self.set.samples])

    def test_logits_hex_round_trip(self):
        values = (10.5, -0.0, 2.0 ** -100, -3.25, 7.0)   # FP32-exact
        text = ",".join(f"{struct.unpack('<I', struct.pack('<f', v))[0]:08x}" for v in values)
        self.assertEqual(w8.logits_from_hex(text), values)


def host_capture(s: w8.SampleSet, set_sha: str | None = None) -> list:
    """The lines an energy-usb image prints for VERIFY, built from the host references."""
    set_sha = set_sha or s.set_sha256
    lines = [f"READY WEEK8 build=host variant=energy-usb kernel=FAST split=2 samples=100 pairs=100 "
             f"set_sha256={set_sha}"]
    for x in s.samples:
        n = x.index
        lines.append(f"VQ n={n} id={x.sample_id} s=2 C={s.channels} L={s.length} q_sha256={x.q_sha256} "
                     f"scale_sha256={x.scale_sha256}")
        p0 = w8.build_request(s, n, n + 1, None, None)
        lines.append(f"VREQ n={n} s=2 rho=P0 rid={n + 1} len={len(p0)} sha256={w8.sha256_hex(p0)}")
        p1 = w8.build_request(s, n, n + 1, w7.PUBLIC_TEST_KEY, n + 1)
        lines.append(f"VREQ n={n} s=2 rho=P1 rid={n + 1} seq={n + 1} len={len(p1)} sha256={w8.sha256_hex(p1)} "
                     f"prot_us=0")
    lines.append(f"VERIFY END kernel=FAST samples=100 set_sha256={set_sha}")
    return [(i, text) for i, text in enumerate(lines)]


class Tools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.set = w8.load_set(SAMPLES)

    def test_requests_parse_and_unprotect(self):
        profile = w7.registry_profile()
        for n in (0, 41, 99):
            q = self.set.samples[n].q
            p0 = w8.build_request(self.set, n, 7, None, None)
            p1 = w8.build_request(self.set, n, 8, w7.PUBLIC_TEST_KEY, 1234)
            self.assertEqual(len(p0), w8.frame_length(self.set, "P0"))
            self.assertEqual(len(p1), w8.frame_length(self.set, "P1"))
            r0, r1 = ref_parse(p0, profile), ref_parse(p1, profile)
            self.assertEqual((r0.request_id, r0.split.split_point, r0.transformed), (7, 2, False))
            self.assertEqual(r0.payload, q)
            self.assertTrue(r1.transformed)
            self.assertNotEqual(r1.payload, q)
            self.assertEqual(w8.ref.recover_q(r1, {w7.KEY_ID: w7.PUBLIC_TEST_KEY}), q)
            self.assertEqual(list(r0.scales), w7.scales_fp32(self.set.samples[n].scale_le))

    def test_checker_passes_host_capture(self):
        result = check_week8.check_verify(host_capture(self.set), self.set)
        self.assertTrue(all(result["checks"].values()), result["checks"])

    def test_checker_rejects_changes(self):
        good = host_capture(self.set)

        def failed(capture):
            return [k for k, ok in check_week8.check_verify(capture, self.set)["checks"].items() if not ok]

        bad_q = [(i, t.replace(self.set.samples[5].q_sha256, "0" * 64)) for i, t in good]
        self.assertIn("q_scale_id_equal_host_reference", failed(bad_q))
        missing = [(i, t) for i, t in good if not t.startswith("VQ n=7 ")]
        self.assertIn("vq_100_in_set_order", failed(missing))
        req = next(t for _, t in good if t.startswith("VREQ n=3 s=2 rho=P1"))
        sha = req.split("sha256=")[1].split()[0]
        bad_req = [(i, t.replace(sha, "f" * 64)) for i, t in good]
        self.assertIn("requests_equal_python_reference", failed(bad_req))
        other = host_capture(self.set, "a" * 64)
        self.assertEqual(set(failed(other)), {"banner_set_sha256", "verify_end_set_sha256"})


def ref_parse(frame: bytes, profile):
    return w8.ref.parse_request(frame, profile)


class LaptopEdge(unittest.TestCase):
    """week8_edge.LaptopEdge with the real tail worker (ml/.venv), then check_week8.py cycles on a
    session assembled from its answers (what the dongle would print for the same requests)."""

    @classmethod
    def setUpClass(cls):
        import week8_edge
        if not week8_edge.ML_PYTHON.exists():
            raise unittest.SkipTest(f"missing {week8_edge.ML_PYTHON}")
        cls.mod = week8_edge
        cls.set = w8.load_set(SAMPLES)
        cls.tail = week8_edge.TailClient(SAMPLES, TMP / "tail.log")

    @classmethod
    def tearDownClass(cls):
        cls.tail.close()

    def edge(self):
        return self.mod.LaptopEdge(self.set, w7.PUBLIC_TEST_KEY, self.tail)

    def session(self, first: int, pairs: int, base_seq: int = 1000) -> tuple:
        edge = self.edge()
        records, lines = [], [f"NONCE status=READY reason=NONE reserved_through={base_seq + 1023} "
                              f"next={base_seq + 1} session_reserved_sequence={base_seq}"]
        seq, rid = base_seq, 500
        for i, pair, n, rho in w8.plan(first, pairs):
            rid += 1
            if rho == "P1":
                seq += 1
            frame = w8.build_request(self.set, n, rid, w7.PUBLIC_TEST_KEY if rho == "P1" else None,
                                     seq if rho == "P1" else None)
            response, record = edge.handle(frame)
            record["t_rx_ms"] = i
            records.append(record)
            self.assertEqual(len(response), w7.RESPONSE_BYTES)
            label = record["label"]
            lines.append(
                f"CYCLE i={i} pair={pair} rho={rho} n={n} id={self.set.samples[n].sample_id} s=2 rid={rid:08x} "
                f"seq={seq if rho == 'P1' else 0} len={len(frame)} frags=13 mtu=247 ctrl_us=200 head_us=1 "
                f"quant_us=1 prot_us=1 enc_us=1 tx_us=1 wait_us=1 enomem=0 invalid=0 nonce_writes=0 "
                f"status=0 res=OK logits={record['logits']} label={label} ref={self.set.samples[n].label_ref} "
                f"match={int(label == self.set.samples[n].label_ref)}")
        ok = sum(r["result"] == "OK" for r in records)
        lines.append(f"PAIRS END first={first} pairs={pairs} cycles={2 * pairs} ok={ok} failed={2 * pairs - ok} "
                     f"label_match={ok} label_mismatch=0")
        return edge, records, lines

    def write_session(self, edge, records, lines, first, pairs) -> Path:
        out = Path(tempfile.mkdtemp(dir=TMP))
        (out / "edge").mkdir()
        (out / "cdc.log").write_text("".join(f"{i}\t{t}\n" for i, t in enumerate(lines)), encoding="utf-8")
        (out / "edge" / "peer.jsonl").write_text(
            "".join(json.dumps({"ev": "request", **r}) + "\n" for r in records), encoding="utf-8")
        result = self.mod.evaluate(records, edge.counters, self.set, first, pairs)
        (out / "edge" / "summary.json").write_text(json.dumps(
            {"peer": "laptop (test)", **result}), encoding="utf-8")
        return out

    def test_answers_from_q_and_cycles_checker(self):
        first, pairs = 98, 4   # wraps 98, 99, 0, 1
        edge, records, lines = self.session(first, pairs)
        self.assertEqual(edge.counters["response_sent"], 2 * pairs)
        for r in records:
            self.assertEqual(r["logits"], check_week8.logits_hex(self.set.samples[r["sample"]].logits))
        out = self.write_session(edge, records, lines, first, pairs)
        capture = check_week8.wc.read_capture(out / "cdc.log")
        result = check_week8.check_cycles(capture, out, self.set, first, pairs, prior_reserved=999)
        self.assertTrue(all(result["checks"].values()), result["checks"])
        # A different label on one cycle, and a different logit word, must both fail.
        bad = [t.replace("label=0 ref=0 match=1", "label=2 ref=0 match=0", 1) for t in lines]
        out_bad = self.write_session(edge, records, bad, first, pairs)
        failed = [k for k, ok in check_week8.check_cycles(check_week8.wc.read_capture(out_bad / "cdc.log"), out_bad,
                                                          self.set, first, pairs)["checks"].items() if not ok]
        self.assertIn("label_is_argmax_of_logits", failed)
        word = records[0]["logits"].split(",")[0]
        bad = [t.replace(f"logits={word}", "logits=00000000", 1) for t in lines]
        out_bad = self.write_session(edge, records, bad, first, pairs)
        failed = [k for k, ok in check_week8.check_cycles(check_week8.wc.read_capture(out_bad / "cdc.log"), out_bad,
                                                          self.set, first, pairs)["checks"].items() if not ok]
        self.assertIn("dongle_logits_equal_edge_logits", failed)

    def external_session(self, records, lines, first, pairs, one=None, log_records=None,
                         edge_reference=None) -> tuple:
        """A cycles --peer external directory + a peer log in the PEER_LOG_FIELDS form, imported."""
        import week8_lab
        out = Path(tempfile.mkdtemp(dir=TMP))
        (out / "cdc.log").write_text("".join(f"{i}\t{t}\n" for i, t in enumerate(lines)), encoding="utf-8")
        (out / "session.json").write_text(json.dumps({
            "schema": "week8-lab-session/1", "kind": "cycles", "samples": str(SAMPLES), "first_pair": first,
            "pairs": pairs, "one": list(one) if one else None, "peer": "external: KV260 (test)",
            "prior_reserved_through": 999}), encoding="utf-8")
        log = TMP / f"peer_{out.name}.jsonl"
        with open(log, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"ev": "connected", "mtu": 247}) + "\n")
            for r in (log_records if log_records is not None else records):
                line = {k: r[k] for k in ("request_id", "rho", "result", "q_sha256", "scale_sha256", "label",
                                          "t_rx_ms") if k in r}
                if "sequence" in r:
                    line["sequence"] = r["sequence"]
                # Plain numbers, as a KV260 script would most likely write them.
                line["logits"] = [float(v) for v in w8.logits_from_hex(r["logits"])]
                handle.write(json.dumps({"ev": "request", **line}) + "\n")
        code = week8_lab.cmd_import_peer(argparse.Namespace(out=out, peer_log=log, edge_reference=edge_reference))
        return code, json.loads((out / "check_cycles.json").read_text(encoding="utf-8"))

    def test_external_peer_import(self):
        first, pairs = 10, 3
        _, records, lines = self.session(first, pairs)
        code, report = self.external_session(records, lines, first, pairs)
        self.assertEqual(code, 0, report["checks"])
        self.assertNotIn("laptop_tail_logits_equal_reference", report["checks"])
        self.assertEqual(report["peer"], "KV260 (test)")
        # One answer with a changed logit (the dongle printed what it received) must fail.
        bad = [dict(r) for r in records]
        bad[2]["logits"] = "00000000," + bad[2]["logits"].split(",", 1)[1]
        with self.assertRaises(ValueError):   # a peer label that is not argmax of its own logits
            self.external_session(records, lines, first, pairs, log_records=bad)
        del bad[2]["label"]
        code, report = self.external_session(records, lines, first, pairs, log_records=bad)
        self.assertEqual(code, 1)
        self.assertFalse(report["checks"]["dongle_logits_equal_edge_logits"])

    def test_external_edge_reference(self):
        """W8-D8: an INT8 peer (logits on a 0.125 grid, one label flipped vs W8-D4) passes against its
        own offline run, fails against W8-D4, and fails when the offline logits differ by one bit."""
        first, pairs = 20, 2
        _, records, lines = self.session(first, pairs)
        offline = {n: np.array(s.logits, np.float32) for n, s in enumerate(self.set.samples)}
        for n in {r["sample"] for r in records}:
            v = np.round(offline[n] * 8) / 8
            if n == first:
                v[(self.set.samples[n].label_ref + 1) % 5] = v.max() + 1
            offline[n] = v.astype(np.float32)
        for r in records:
            r["logits"] = check_week8.logits_hex(offline[r["sample"]])
            r["label"] = w8.label(tuple(float(x) for x in offline[r["sample"]]))
        fixed = []
        for t in lines:
            m = re.search(r" n=(\d+) ", t)
            if t.startswith("CYCLE") and m:
                n = int(m.group(1))
                label = w8.label(tuple(float(x) for x in offline[n]))
                t = re.sub(r"logits=\S+ label=\d+ ref=(\d+) match=\d",
                           lambda g: f"logits={check_week8.logits_hex(offline[n])} label={label} ref={g.group(1)} "
                                     f"match={int(label == self.set.samples[n].label_ref)}", t)
            fixed.append(t)

        def reference(change_bit=False) -> Path:
            path = Path(tempfile.mkstemp(dir=TMP, suffix=".jsonl")[1])
            with open(path, "w", encoding="utf-8") as handle:
                for n, s in enumerate(self.set.samples):
                    v = offline[n].copy()
                    if change_bit and n == first + 1:
                        v.view("<u4")[0] ^= 1
                    handle.write(json.dumps({"sample_id": s.sample_id, "logits": [float(x) for x in v]}) + "\n")
            return path

        code, report = self.external_session(records, fixed, first, pairs, edge_reference=reference())
        self.assertEqual(code, 0, report["checks"])
        self.assertTrue(report["checks"]["dongle_logits_equal_edge_offline"])
        self.assertEqual(report["labels_equal_w8d4_fp32"], {"P1": 1, "P0": 1})
        code, report = self.external_session(records, fixed, first, pairs)
        self.assertEqual(code, 1)
        self.assertFalse(report["checks"]["labels_equal_reference_p1"])
        code, report = self.external_session(records, fixed, first, pairs, edge_reference=reference(True))
        self.assertEqual(code, 1)
        self.assertFalse(report["checks"]["dongle_logits_equal_edge_offline"])

    def test_external_one(self):
        for n, rho in ((7, "P0"), (7, "P1")):
            edge = self.edge()
            seq = 1001 if rho == "P1" else 0
            frame = w8.build_request(self.set, n, 77, w7.PUBLIC_TEST_KEY if rho == "P1" else None,
                                     seq if rho == "P1" else None)
            _, record = edge.handle(frame)
            sample = self.set.samples[n]
            lines = ["NONCE status=READY reason=NONE reserved_through=2023 next=1001 session_reserved_sequence=1000",
                     f"CYCLE i=0 pair=0 rho={rho} n={n} id={sample.sample_id} s=2 rid=0000004d seq={seq} "
                     f"len={len(frame)} frags=13 mtu=247 ctrl_us=200 head_us=1 quant_us=1 prot_us=1 enc_us=1 "
                     f"tx_us=1 wait_us=1 enomem=0 invalid=0 nonce_writes=0 status=0 res=OK "
                     f"logits={record['logits']} label={record['label']} ref={sample.label_ref} match=1",
                     "ONE END ok=1 label_match=1"]
            code, report = self.external_session([record], lines, 0, 1, one=(n, rho))
            self.assertEqual(code, 0, (rho, report["checks"]))
            self.assertEqual("p1_sequence_in_boot_block" in report["checks"], rho == "P1")

    def test_rejects_without_answer(self):
        edge = self.edge()
        frame = w8.build_request(self.set, 3, 9, w7.PUBLIC_TEST_KEY, 50)
        self.assertIsNotNone(edge.handle(frame)[0])
        replay = w8.build_request(self.set, 4, 10, w7.PUBLIC_TEST_KEY, 50)
        self.assertEqual(edge.handle(replay), (None, edge.handle(replay)[1]))
        self.assertEqual(edge.counters["sequence_not_increasing"], 2)
        broken = bytearray(w8.build_request(self.set, 4, 11, None, None))
        broken[-1] ^= 1
        response, record = edge.handle(bytes(broken))
        self.assertIsNone(response)
        self.assertEqual(record["result"], "CRC_FAIL")
        nokey = self.mod.LaptopEdge(self.set, None, self.tail)
        self.assertEqual(nokey.handle(w8.build_request(self.set, 1, 12, w7.PUBLIC_TEST_KEY, 60))[1]["result"], "NO_KEY")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory (generate_week8_samples.py)")
    args, rest = parser.parse_known_args()
    SAMPLES = args.samples.resolve()
    result = unittest.main(argv=[sys.argv[0], *rest], verbosity=2, exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
