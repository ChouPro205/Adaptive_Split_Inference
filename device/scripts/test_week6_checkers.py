#!/usr/bin/env python3
"""Negative tests of check_week6.py: a capture shaped like the firmware output must PASS and
every tampered variant must FAIL. Synthetic captures only (no device); line formats mirror the
printk() calls of device/week6/main.c. Run: python -B device/scripts/test_week6_checkers.py
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import week6_common as wc  # noqa: E402

CHECK = HERE / "check_week6.py"
CONTRACT = json.loads((wc.REF / "vectors.json").read_text(encoding="utf-8"))
CONTRACT_SHA = hashlib.sha256((wc.REF / "vectors.json").read_bytes()).hexdigest()
TMP = Path(tempfile.mkdtemp(prefix="week6_checkers_"))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_capture(directory: Path, lines: list) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / "cdc.log", "w", encoding="utf-8", newline="\n") as f:
        for i, line in enumerate(lines):
            f.write(f"{1000 + 10 * i}\t{line}\n")


def run_check(kind: str, session, *extra) -> int:
    sessions = session if isinstance(session, list) else [session]
    out = sessions[0] / f"report_{len(list(sessions[0].glob('report_*')))}.json"
    args = [sys.executable, "-B", str(CHECK), kind]
    for s in sessions:
        args += ["--session", str(s)]
    return subprocess.run(args + ["--output", str(out)] + list(extra), capture_output=True).returncode


def banner(build="b-default", reserved=0, status="READY", cause="0x00000000", in_write="unknown"):
    return [f"READY WEEK6 build={build} variant=default cfg_att_mtu=247 package={wc.PACKAGE_ID} "
            f"vectors_manifest={wc.PACKAGE_MANIFEST_SHA256} i1v2_vectors={CONTRACT_SHA}",
            f"BOOT reset_cause={cause} soft_reset=0 boot_in_write={in_write}",
            f"NONCE status={status} reason={'NONE' if status != 'FAULT' else 'STATE_CRC'} mounted=1 "
            f"mount_err=0 reserved_through={reserved} next={reserved + 1} limit={reserved} key_id=65537 "
            f"sender_id=131073 key_check=0011223344556677 writes=0 write_cyc_max=0 write_cyc_total=0"]


# ---------------------------------------------------------------------------- selftest

def selftest_lines() -> list:
    lines = banner() + ["#HOST SEND SELFTEST ENC"]
    goldens = {"plain_s10": CONTRACT["golden"]["plain_s10"]["packet_hex"],
               "i2_s10": CONTRACT["golden"]["i2_s10"]["packet_hex"]}
    goldens.update({b["id"]: b["packet_hex"] for b in CONTRACT["boundary"]})
    for name, packet_hex in goldens.items():
        packet = bytes.fromhex(packet_hex)
        lines.append(f"ENC id={name} len={len(packet)} sha256={sha(packet)} match=1 prot_cyc=10 enc_cyc=20")
    import i1v2_reference as ref
    for case in CONTRACT["response"]:
        try:
            kind, value = ref.parse_response(bytes.fromhex(case["packet_hex"]), case["expected_request_id"], 6380)
            result, status = ("OK", 0) if kind == "OK" else ("ERROR", value)
        except ref.Drop:
            result, status = "DROP", 0
        lines.append(f"RESP id={case['id']} result={result} status={status} match=1")
    lines += ["ENC END pass=19 total=19", "#HOST SEND SELFTEST P1"]
    package = json.loads((wc.PACKAGE / "vectors.json").read_text(encoding="utf-8"))
    for v in sorted(package["vectors"], key=lambda x: int(x["vector_index"])):
        files = {k: (wc.PACKAGE / p).read_bytes() for k, p in v["files"].items()}
        _, c, l = json.loads(v["shape"]) if isinstance(v["shape"], str) else v["shape"]
        lines.append(
            f"P1 i={v['vector_index']} s={v['split_point_s']} split={v['wire_split_id']} C={c} L={l} "
            f"seq={v['sequence']} tr_sha256={sha(files['transformed'])} tr_match=1 roundtrip=1 "
            f"n80={files['transformed'].count(0x80)} req_len={len(files['request'])} "
            f"req_sha256={sha(files['request'])} req_match=1 desc_ok=1 prot_cyc={1000 * c} "
            f"unprot_cyc={1100 * c} enc_cyc=500 sha_cyc=300")
    lines += ["P1 END pass=50 total=50 vectors_with_0x80=50", "#HOST SEND SELFTEST QUANT"]
    for v in sorted(package["vectors"], key=lambda x: int(x["vector_index"])):
        _, c, l = json.loads(v["shape"]) if isinstance(v["shape"], str) else v["shape"]
        lines.append(f"QUANT i={v['vector_index']} s={v['split_point_s']} C={c} L={l} status=0 cyc=9999 q_equal=1")
    lines += ["QUANT END total=50", "STACK main used=2100 size=8192", "STACK i1_tx used=600 size=2048"]
    return lines


@unittest.skipUnless((wc.PACKAGE / "vectors.json").exists(), "SV3 P1 package not hydrated")
class SelftestCheckerTests(unittest.TestCase):
    def check(self, lines, name):
        d = TMP / f"selftest_{name}"
        write_capture(d, lines)
        return run_check("selftest", d)

    def test_good_capture_passes(self):
        self.assertEqual(self.check(selftest_lines(), "good"), 0)

    def test_tampering_fails(self):
        good = selftest_lines()
        p1 = [i for i, x in enumerate(good) if x.startswith("P1 i=")]
        enc = [i for i, x in enumerate(good) if x.startswith("ENC id=")]
        resp = [i for i, x in enumerate(good) if x.startswith("RESP id=")]
        cases = {
            "transformed_hash": lambda l: l.__setitem__(p1[7], re.sub(r"tr_sha256=\w", "tr_sha256=z", l[p1[7]])),
            "roundtrip0": lambda l: l.__setitem__(p1[3], l[p1[3]].replace("roundtrip=1", "roundtrip=0")),
            "missing_line": lambda l: l.pop(p1[49]),
            "n80": lambda l: l.__setitem__(p1[0], l[p1[0]].replace(" n80=", " n80=9")),
            "encoder": lambda l: l.__setitem__(enc[2], l[enc[2]].replace("sha256=", "sha256=00")),
            "response": lambda l: l.__setitem__(resp[2], l[resp[2]].replace("result=DROP", "result=OK")),
            "banner": lambda l: l.__setitem__(0, l[0].replace(wc.PACKAGE_MANIFEST_SHA256, "0" * 64)),
            "quant": lambda l: l.__setitem__([i for i, x in enumerate(l) if x.startswith("QUANT i=")][5],
                                             "QUANT i=5 s=1 C=16 L=360 status=-3 cyc=1 q_equal=0"),
        }
        for name, damage in cases.items():
            lines = list(good)
            damage(lines)
            self.assertEqual(self.check(lines, name), 1, name)


# ---------------------------------------------------------------------------- loopback

SPLIT_TABLE = {row["s"]: row for row in CONTRACT["split_table"]}
VECTOR_S = [0] * 5 + [1] * 5 + [2] * 5 + [3] * 5 + [4] * 5 + [5] * 5 + [6] * 4 + [7] * 4 + [8] * 4 + \
    [9] * 4 + [10] * 4


def mix_schedule(count: int) -> list:
    """Mirror of spec_for(PATTERN_MIX) in device/week6/main.c."""
    out = []
    for i in range(count):
        if i % 25 == 24:
            out.append(("T", 6380, True))
            continue
        s = VECTOR_S[i % 50]
        i2 = (i // 50) % 2 == 1
        row = SPLIT_TABLE[s]
        out.append((str(s), row["total_i2"] if i2 else row["total_plain"], i2))
    return out


def loopback_session(name: str, count=1000, mtu=247, damage=None) -> Path:
    d = TMP / f"loop_{name}"
    lines = banner() + ["CONFIG response_timeout_base_ms=8000 per_fragment_budget_ms=30 max_retries=2 "
                        "backoff_base_ms=250 reconnect_wait_ms=10000 reassembly_timeout_ms=2000 tx_credits=4 "
                        "tx_credit_timeout_ms=2000 max_frame=6380",
                        f"#HOST SEND RUN {count} MIX",
                        f"RUN BEGIN run=1 count={count} pattern=MIX mode=ECHO build=b variant=default "
                        f"att_mtu={mtu} interval_1250us=24 phy_tx=2 phy_rx=2"]
    peer, seq, rid = [], 0, 0x1000
    for i, (s, length, i2) in enumerate(mix_schedule(count)):
        rid += 1
        crc = f"{zlib.crc32(struct.pack('<II', rid, length)) & 0xFFFFFFFF:08x}"
        seq_text = 0
        if i2:
            seq += 1
            seq_text = seq
        frags = -(-length // (mtu - 11))
        lines.append(f"PKT i={i} rid={rid:08x} len={length} flags={2 if i2 else 0} s={s} seq={seq_text} "
                     f"crc={crc} res=OK att=1 rtt_us={20000 + length * 10} mtu={mtu} frags={frags} tid={i + 1} "
                     f"tx_cyc={length * 600} tx_ms={length // 100} enomem=0 prot_cyc={9000 if i2 else 0} "
                     f"enc_cyc=4000 status=0")
        peer.append({"t": i, "ev": "rx_frame", "stream": 2, "length": length, "request_id": rid,
                     "crc": crc, "crc_ok": True, "sha256": "x"})
    counters = {k: 0 for k in wc.EXCH_COUNTERS}
    counters.update(planned=count, sent_first=count, completed=count)
    lines += [f"RUN END run=1 requested={count} aborted=0 reason= att_mtu={mtu} interval_1250us=24 phy_tx=2 "
              f"phy_rx=2 disconnections=0",
              "COUNTERS " + " ".join(f"{k}={v}" for k, v in counters.items()),
              "REASM malformed_fragment=0 inconsistent_fragment=0 orphan_fragment=0 duplicate_fragment=0 "
              "superseded_transfer=0 overlap_conflict=0 gap=0 frame_header_mismatch=0 reassembly_timeout=0 "
              f"disconnect=0 rx_busy=0 aborted_transfers=0 frames_delivered={count}",
              "STACK main used=2400 size=8192"]
    if damage:
        damage(lines, peer)
    write_capture(d, lines)
    with open(d / "peer.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for e in peer:
            f.write(json.dumps(e) + "\n")
    return d


class LoopbackCheckerTests(unittest.TestCase):
    ARGS = ("--expect-mtu", "247", "--count", "1000", "--require-sizes", "113,153,6124,6380")

    def test_schedule_covers_required_sizes(self):
        sizes = {length for _, length, _ in mix_schedule(1000)}
        self.assertTrue(set(wc.REQUIRED_SIZES) <= sizes)

    def test_good_run_passes(self):
        self.assertEqual(run_check("loopback", loopback_session("good"), *self.ARGS), 0)

    def test_tampering_fails(self):
        def pkt(lines):
            return [i for i, x in enumerate(lines) if x.startswith("PKT ")]

        def counters(lines, **changes):
            i = next(i for i, x in enumerate(lines) if x.startswith("COUNTERS "))
            kv = wc.kv(lines[i])
            kv.update({k: str(v) for k, v in changes.items()})
            lines[i] = "COUNTERS " + " ".join(f"{k}={v}" for k, v in kv.items())

        cases = {
            "failed_packet": lambda l, p: (l.__setitem__(pkt(l)[10], l[pkt(l)[10]].replace("res=OK", "res=FAILED")),
                                           counters(l, completed=999, failed=1)),
            "crc_fail": lambda l, p: counters(l, crc_fail=1),
            "missing_pkt_line": lambda l, p: l.pop(pkt(l)[500]),
            "peer_missing_frame": lambda l, p: p.pop(42),
            "peer_crc_bad": lambda l, p: p[7].update(crc_ok=False),
            "wrong_mtu": lambda l, p: l.__setitem__(pkt(l)[3], l[pkt(l)[3]].replace("mtu=247", "mtu=23")),
            "no_ceiling": lambda l, p: [l.__setitem__(i, l[i].replace("len=6380", "len=6124"))
                                        for i in pkt(l) if "len=6380" in l[i]],
            "aborted": lambda l, p: l.__setitem__(next(i for i, x in enumerate(l) if x.startswith("RUN END")),
                                                  next(x for x in l if x.startswith("RUN END")).replace(
                                                      "aborted=0", "aborted=1")),
            "seq_repeat": lambda l, p: l.__setitem__(pkt(l)[99], l[pkt(l)[99]].replace(
                f"seq={wc.kv(l[pkt(l)[99]])['seq']}", f"seq={int(wc.kv(l[pkt(l)[99]])['seq']) - 1}")),
        }
        for name, damage in cases.items():
            self.assertEqual(run_check("loopback", loopback_session(name, damage=damage), *self.ARGS), 1, name)


# ---------------------------------------------------------------------------- nonce

def nonce_session(name: str, damage=None, cycles=105) -> Path:
    d = TMP / f"nonce_{name}"
    lines, reserved, seq = [], 0, 0
    lines += banner(reserved=reserved)
    for cycle in range(cycles):
        kind = "POWER_CUT" if cycle % 7 == 6 else "SOFT_RESET"
        lines.append(f"#HOST CYCLE {cycle} kind={kind} stress_ms=500")
        lines.append("NSTRESS BEGIN duration_ms=500 reboot=1 gap_ms=3")
        for _ in range(5):
            reserved += 1024
            seq = reserved - 1023
            lines.append(f"SEQ {seq}")
        lines += banner(reserved=reserved, in_write="1" if cycle % 5 == 0 and kind == "SOFT_RESET" else "0")
    if damage:
        damage(lines)
    write_capture(d, lines)
    return d


def hooks_session(name: str, damage=None) -> Path:
    d = TMP / f"hooks_{name}"
    nonce = lambda status, reason, r=4096: (  # noqa: E731
        f"NONCE status={status} reason={reason} mounted=1 mount_err=0 reserved_through={r} next={r + 1} "
        f"limit={r} key_id=65537 sender_id=131073 key_check=0011223344556677 writes=1 write_cyc_max=0 "
        f"write_cyc_total=0")
    lines = banner(reserved=3072)
    lines += ["NTEST FAILWRITE first=-1 second=-1 status=FAULT reason=WRITE_FAILED writes_before=0 "
              "writes_after=1 result=PASS", nonce("FAULT", "WRITE_FAILED", 3072),
              "#HOST CYCLE hook kind=SOFT_RESET"]
    lines += banner(reserved=3072)
    lines += ["NTEST READBACK first=-1 second=-1 status=FAULT reason=READBACK writes_before=0 writes_after=1 "
              "result=PASS", nonce("FAULT", "READBACK", 3072), "#HOST CYCLE hook kind=SOFT_RESET"]
    lines += banner(reserved=4096)
    for hook, status, reason in (("STATE_CRC", "FAULT", "STATE_CRC"), ("STATE_MISSING", "FAULT", "STATE_MISSING"),
                                 ("PROVISION_CORRUPT", "FAULT", "PROVISION_CORRUPT"),
                                 ("KEY_MISMATCH", "FAULT", "STATE_KEY_MISMATCH"), ("NONE", "READY", "NONE")):
        lines += [f"NTEST BOOT hook={hook} storage_writes_during_boot=0", nonce(status, reason)]
    lines += ["#HOST CYCLE final kind=SOFT_RESET"] + banner(reserved=4096)
    lines += ["NONCE ALLOC requested=3 got=3 first=4097 last=4099", nonce("READY", "NONE", 5120)]
    if damage:
        damage(lines)
    write_capture(d, lines)
    return d


class NonceCheckerTests(unittest.TestCase):
    def test_good_sessions_pass(self):
        self.assertEqual(run_check("nonce", nonce_session("good"), "--min-soft", "80", "--min-power", "10"), 0)
        self.assertEqual(run_check("nonce", hooks_session("good"), "--hooks"), 0)

    def test_two_sessions_must_continue(self):
        first = nonce_session("first", cycles=10)
        later = nonce_session("later", cycles=10)   # restarts at low sequences: reuse across sessions
        self.assertEqual(run_check("nonce", [first, later]), 1)

    def test_tampering_fails(self):
        def repeat(lines):
            seqs = [i for i, x in enumerate(lines) if x.startswith("SEQ ")]
            lines[seqs[200]] = lines[seqs[150]]

        def low_reserved(lines):
            i = [i for i, x in enumerate(lines) if x.startswith("NONCE status=")][40]
            lines[i] = re.sub(r"reserved_through=\d+", "reserved_through=5", lines[i])

        self.assertEqual(run_check("nonce", nonce_session("repeat", repeat)), 1)
        self.assertEqual(run_check("nonce", nonce_session("low", low_reserved)), 1)
        self.assertEqual(run_check("nonce", nonce_session("few"), "--min-soft", "200"), 1)
        for name, damage in {
            "failwrite": lambda l: l.__setitem__(3, l[3].replace("result=PASS", "result=FAIL")),
            "hook_reason": lambda l: [l.__setitem__(i, x.replace("reason=STATE_CRC", "reason=NONE"))
                                      for i, x in enumerate(l) if "reason=STATE_CRC" in x],
            "hook_wrote": lambda l: [l.__setitem__(i, x.replace("storage_writes_during_boot=0",
                                                                "storage_writes_during_boot=1"))
                                     for i, x in enumerate(l) if "hook=KEY_MISMATCH" in x],
        }.items():
            self.assertEqual(run_check("nonce", hooks_session(name, damage), "--hooks"), 1, name)


# ---------------------------------------------------------------------------- negative

def negative_session(name: str, scenario: str, counters_override=None, faults=1) -> Path:
    spec = wc.NEGATIVE_SCENARIOS[scenario]
    d = TMP / f"neg_{name}" / scenario
    counters = {k: 0 for k in wc.EXCH_COUNTERS}
    counters.update(planned=spec["count"], sent_first=spec["count"])
    counters.update(spec["expect"])
    counters.update(counters_override or {})
    reasm = {"gap": 0, "malformed_fragment": 0}
    reasm.update(spec.get("reasm_min", {}))
    lines = banner() + [f"RUN BEGIN run=1 count={spec['count']} pattern=SIZES={spec['sizes']} mode=ECHO "
                        f"build=b variant=default att_mtu=247 interval_1250us=24 phy_tx=2 phy_rx=2"]
    for i in range(spec["count"]):
        lines.append(f"PKT i={i} rid=0000100{i} len={spec['sizes']} flags=0 s=2 seq=0 crc=00000000 res=OK att=1 "
                     f"rtt_us=1 mtu=247 frags=14 tid=1 tx_cyc=1 tx_ms=1 enomem=0 prot_cyc=0 enc_cyc=1 status=0")
    lines += [f"RUN END run=1 requested={spec['count']} aborted=0 reason= att_mtu=247 interval_1250us=24 "
              "phy_tx=2 phy_rx=2 disconnections=0",
              "COUNTERS " + " ".join(f"{k}={v}" for k, v in counters.items()),
              "REASM " + " ".join(f"{k}={v}" for k, v in reasm.items())]
    write_capture(d, lines)
    with open(d / "peer.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({"ev": "peer_counts", "faults_applied": faults}) + "\n")
    return d


class NegativeCheckerTests(unittest.TestCase):
    def test_every_scenario_good_passes_and_wrong_counter_fails(self):
        for scenario, spec in wc.NEGATIVE_SCENARIOS.items():
            good = negative_session("good", scenario)
            self.assertEqual(run_check("negative", good, "--scenario", scenario), 0, scenario)
            key = next(iter(spec["expect"]))
            bad = negative_session("bad", scenario, {key: spec["expect"][key] + 1})
            self.assertEqual(run_check("negative", bad, "--scenario", scenario), 1, scenario)
        self.assertEqual(run_check("negative", negative_session("nofault", "crc", faults=0), "--scenario", "crc"), 1)

    def test_summary_requires_all_scenarios(self):
        self.assertEqual(run_check("negative", TMP / "neg_good"), 0)
        self.assertEqual(run_check("negative", TMP / "neg_bad"), 1)


class SentinelCheckerTests(unittest.TestCase):
    VALUE = "00112233445566778899aabbccddeeff"

    def session(self, name, op, build, value, reserved):
        d = TMP / f"sentinel_{name}"
        lines = banner(build=build, reserved=reserved) + [
            f"SENTINEL op={op} err=0 value={value}"] + banner(reserved=reserved)[2:]
        write_capture(d, lines)
        return d

    def check(self, before, after) -> int:
        out = after / f"report_{len(list(after.glob('report_*')))}.json"
        return subprocess.run([sys.executable, "-B", str(CHECK), "sentinel", "--before", str(before),
                               "--after", str(after), "--output", str(out)], capture_output=True).returncode

    def test_dfu_sentinel(self):
        before = self.session("w", "WRITE", "build-default", self.VALUE, 5120)
        self.assertEqual(self.check(before, self.session("r", "READ", "build-mtu23", self.VALUE, 5120)), 0)
        self.assertEqual(self.check(before, self.session("r2", "READ", "build-mtu23", "f" * 32, 5120)), 1)
        self.assertEqual(self.check(before, self.session("r3", "READ", "build-default", self.VALUE, 5120)), 1)
        self.assertEqual(self.check(before, self.session("r4", "READ", "build-mtu23", self.VALUE, 1024)), 1)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
