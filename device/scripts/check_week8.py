#!/usr/bin/env python3
"""Offline checks of week 8 dongle sessions recorded by week8_lab.py (cdc.log).

  verify  TC2: the energy-usb image prints one VQ line per W8-D3 sample (s=2) and two VREQ lines
          (P0 plain; P1 PUBLIC_TEST key, sequence n+1; request_id n+1). Every q/scale SHA-256 equals
          the host C reference of samples.csv (week8_common.load_set), the sample ID and order equal
          the set, every request equals the one built by contracts/i1v2_ref + i2_ref from that
          tensor, and the image reports the W8-D3 set SHA-256 (banner and VERIFY END).
  cycles  TC3/TC5: PAIRS <first> <pairs> (or ONE <n> <rho>, --one) against an edge peer
          (edge/peer.jsonl + edge/summary.json of week8_lab.py: the laptop edge, or an external peer's
          log brought in with week8_lab.py import-peer). Device side: every CYCLE OK in the W8-D1 order (pair, sample, rho), one
          attempt, no Flash write inside a cycle, P1 sequences inside the block reserved at boot,
          strictly increasing (and above --prior-reserved-through), frame lengths per I1 v2; the
          label printed equals argmax of the printed logits and the reference label (W8-D4) for
          every sample, per rho. Cross-checks: the dongle's logits equal the edge's, bit for bit,
          per request_id; the edge recovered exactly the samples' q/scale (P1 unprotect bit-exact);
          laptop peer only: the edge logits equal reference_s2.npz bit for bit.
          DWT phase times summarized (laptop power: debug only, never energy numbers).
Exit 0 = PASS. Writes a JSON report to a new --output path.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import week6_common as wc  # noqa: E402
import week7_common as w7  # noqa: E402
import week8_common as w8  # noqa: E402


def lines_with(capture, tag: str) -> list:
    return [wc.kv(text) for _, text in capture if text.startswith(tag)]


def check_verify(capture, sample_set: w8.SampleSet) -> dict:
    vq = lines_with(capture, "VQ n=")
    vreq = lines_with(capture, "VREQ n=")
    end = lines_with(capture, "VERIFY END")
    banner = next((wc.kv(t) for _, t in capture if t.startswith("READY WEEK8 ")), {})
    q_ok, req_ok, mismatches = [], [], []
    for r in vq:
        n = int(r["n"])
        sample = sample_set.samples[n] if 0 <= n < w8.SAMPLE_COUNT else None
        ok = (sample is not None and r.get("id") == sample.sample_id and int(r.get("s", -1)) == w8.SPLIT
              and int(r.get("C", -1)) == sample_set.channels and int(r.get("L", -1)) == sample_set.length
              and r.get("q_sha256") == sample.q_sha256 and r.get("scale_sha256") == sample.scale_sha256)
        q_ok.append(ok)
        if not ok:
            mismatches.append({"n": n, "what": "q/scale/id/shape"})
    for r in vreq:
        n, rid = int(r["n"]), int(r["rid"])
        p1 = r["rho"] == "P1"
        ok = 0 <= n < w8.SAMPLE_COUNT and int(r["s"]) == w8.SPLIT
        if ok:
            frame = w8.build_request(sample_set, n, rid, w7.PUBLIC_TEST_KEY if p1 else None,
                                     int(r["seq"]) if p1 else None)
            ok = int(r["len"]) == len(frame) and r["sha256"] == w8.sha256_hex(frame)
        req_ok.append(ok)
        if not ok:
            mismatches.append({"n": n, "rho": r["rho"], "what": "request"})
    expected_requests = sorted((n, rho) for n in range(w8.SAMPLE_COUNT) for rho in ("P0", "P1"))
    checks = {
        "banner_set_sha256": banner.get("set_sha256") == sample_set.set_sha256,
        "banner_split_2_samples_100": banner.get("split") == str(w8.SPLIT)
                                      and banner.get("samples") == str(w8.SAMPLE_COUNT),
        "vq_100_in_set_order": [int(r["n"]) for r in vq] == list(range(w8.SAMPLE_COUNT)),
        "q_scale_id_equal_host_reference": len(q_ok) == w8.SAMPLE_COUNT and all(q_ok),
        "requests_p0_p1_per_sample": sorted((int(r["n"]), r["rho"]) for r in vreq) == expected_requests,
        "requests_equal_python_reference": len(req_ok) == 2 * w8.SAMPLE_COUNT and all(req_ok),
        "frame_lengths": all(int(r["len"]) == w8.frame_length(sample_set, r["rho"]) for r in vreq),
        "verify_end_set_sha256": len(end) == 1 and end[0].get("samples") == str(w8.SAMPLE_COUNT)
                                 and end[0].get("set_sha256") == sample_set.set_sha256,
    }
    return {"checks": checks, "mismatches": mismatches, "samples_dir": str(sample_set.directory),
            "set_sha256": sample_set.set_sha256, "kernel": end[0].get("kernel") if end else None,
            "p1_prot_us": [int(r["prot_us"]) for r in vreq if r["rho"] == "P1" and "prot_us" in r],
            "reference": "host C path of generate_week8_samples.py (week7/head_fast.c + week5 quantization)"}


def edge_records(session: Path) -> list:
    path = session / "edge" / "peer.jsonl"
    if not path.exists():
        return []
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [e for e in events if e.get("ev") == "request"]


def logits_hex(logits) -> str:
    return ",".join(f"{v:08x}" for v in np.array(logits, "<f4").view("<u4").tolist())


def check_cycles(capture, session: Path, sample_set: w8.SampleSet, first: int, pairs: int,
                 prior_reserved: int | None = None, one: tuple | None = None) -> dict:
    rows = lines_with(capture, "CYCLE i=")
    plan = w8.one_plan(*one) if one else w8.plan(first, pairs)
    want = {rho: sum(1 for p in plan if p[3] == rho) for rho in ("P1", "P0")}
    covered = {rho: len({p[2] for p in plan if p[3] == rho}) for rho in ("P1", "P0")}
    end = lines_with(capture, "ONE END" if one else "PAIRS END")
    # The first NONCE line follows the boot reservation (week 7 check_dryrun semantics).
    boot_nonce = next((wc.kv(t) for _, t in capture if t.startswith("NONCE status=")), {})
    reserved_at_boot = int(boot_nonce.get("reserved_through", "0"))
    block_first = int(boot_nonce.get("session_reserved_sequence", "0"))
    sequences = [int(r["seq"]) for r in rows if r["rho"] == "P1"]
    edge = {r["request_id"]: r for r in edge_records(session) if "request_id" in r}
    summary_path = session / "edge" / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    laptop_peer = str(summary.get("peer", "")).startswith("laptop")
    per_rho = {rho: {"match": 0, "mismatch": 0, "failed": 0, "samples": set()} for rho in ("P1", "P0")}
    label_from_logits, edge_logits, edge_q, edge_reference, mismatches = [], [], [], [], []
    for r in rows:
        n, rho = int(r["n"]), r["rho"]
        sample = sample_set.samples[n]
        bucket = per_rho[rho]
        if r["res"] != "OK":
            bucket["failed"] += 1
            mismatches.append({"i": int(r["i"]), "n": n, "rho": rho, "res": r["res"]})
            continue
        label = int(r["label"])
        label_from_logits.append(w8.label(w8.logits_from_hex(r["logits"])) == label)
        ok = label == sample.label_ref and int(r["ref"]) == sample.label_ref and r["match"] == "1"
        bucket["match" if ok else "mismatch"] += 1
        bucket["samples"].add(n)
        if not ok:
            mismatches.append({"i": int(r["i"]), "n": n, "rho": rho, "label": label, "ref": sample.label_ref})
        e = edge.get(int(r["rid"], 16), {})
        edge_logits.append(e.get("logits") == r["logits"])
        edge_q.append(e.get("sample") == n and e.get("q_sha256") == sample.q_sha256
                      and e.get("scale_sha256") == sample.scale_sha256)
        edge_reference.append(e.get("logits") == logits_hex(sample.logits))
    want_len = {rho: w8.frame_length(sample_set, rho) for rho in ("P1", "P0")}
    checks = {
        "cycle_count": len(rows) == len(plan),
        "all_ok": bool(rows) and all(r["res"] == "OK" for r in rows),
        "plan_order_pair_sample_rho": [(int(r["i"]), int(r["pair"]), int(r["n"]), r["rho"]) for r in rows] == plan,
        "sample_ids": all(r["id"] == sample_set.samples[int(r["n"])].sample_id for r in rows),
        "single_attempt": all(r["invalid"] == "0" for r in rows),
        "no_flash_write_in_cycle": all(r["nonce_writes"] == "0" for r in rows),
        "frame_lengths": all(int(r["len"]) == want_len[r["rho"]] for r in rows),
        "label_is_argmax_of_logits": bool(label_from_logits) and all(label_from_logits),
        "labels_equal_reference_p1": per_rho["P1"]["match"] == want["P1"]
                                     and len(per_rho["P1"]["samples"]) == covered["P1"],
        "labels_equal_reference_p0": per_rho["P0"]["match"] == want["P0"]
                                     and len(per_rho["P0"]["samples"]) == covered["P0"],
        "end_totals": len(end) == 1 and end[0].get("ok") == str(len(plan))
                      and end[0].get("label_match") == str(len(plan)),
        "dongle_logits_equal_edge_logits": bool(edge_logits) and all(edge_logits),
        "edge_q_scale_equal_samples": bool(edge_q) and all(edge_q),
        "edge_summary_pass": summary.get("status") == "PASS",
    }
    if laptop_peer:
        checks["laptop_tail_logits_equal_reference"] = bool(edge_reference) and all(edge_reference)
    if want["P1"]:
        checks["p1_sequence_in_boot_block"] = block_first > 0 and bool(sequences) and all(
            block_first <= q <= reserved_at_boot for q in sequences)
        checks["p1_sequence_strictly_increasing"] = all(b > a for a, b in zip(sequences, sequences[1:]))
    if prior_reserved is not None and want["P1"]:
        checks["p1_sequence_above_prior_reservation"] = bool(sequences) and all(q > prior_reserved for q in sequences)
    phases = {}
    for key in ("ctrl_us", "head_us", "quant_us", "prot_us", "enc_us", "tx_us", "wait_us"):
        for rho in ("P1", "P0"):
            values = [int(r[key]) for r in rows if r["rho"] == rho]
            if values:
                phases[f"{rho}_{key}"] = {"mean": statistics.fmean(values), "min": min(values), "max": max(values)}
    true_match = sum(1 for r in rows if r["res"] == "OK"
                     and int(r["label"]) == sample_set.samples[int(r["n"])].true_label)
    return {"checks": checks, "peer": summary.get("peer"), "first_pair": first, "pairs": pairs,
            "one": list(one) if one else None,
            "labels": {rho: {k: (len(v) if k == "samples" else v) for k, v in b.items()}
                       for rho, b in per_rho.items()},
            "label_equals_true_class_cycles": true_match,
            "label_equals_true_class_note": "model accuracy on the W8-D3 set (not a G2 criterion)",
            "mismatches": mismatches,
            "reserved_through_at_boot": reserved_at_boot, "session_reserved_sequence": block_first,
            "prior_reserved_through": prior_reserved,
            "first_p1_sequence": sequences[0] if sequences else None,
            "last_p1_sequence": sequences[-1] if sequences else None,
            "att_mtu": sorted({r["mtu"] for r in rows}),
            "dwt_phases_us": phases,
            "scope": "energy-usb on laptop power: correctness evidence; timings debug only, not energy"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("kind", choices=["verify", "cycles"])
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first", type=int, default=0, help="cycles: first pair")
    parser.add_argument("--pairs", type=int, default=100, help="cycles: number of pairs")
    parser.add_argument("--prior-reserved-through", type=int,
                        help="cycles: NONCE reserved_through read before this boot/image")
    parser.add_argument("--one", nargs=2, metavar=("N", "RHO"),
                        help="cycles: the session ran ONE <n> P1|P0 instead of PAIRS")
    args = parser.parse_args()
    if args.output.exists():
        sys.exit(f"refusing to overwrite {args.output}")
    capture = wc.read_capture(args.session / "cdc.log")
    sample_set = w8.load_set(args.samples)
    if args.kind == "verify":
        result = check_verify(capture, sample_set)
    else:
        one = (int(args.one[0]), args.one[1]) if args.one else None
        result = check_cycles(capture, args.session, sample_set, args.first, args.pairs,
                              args.prior_reserved_through, one)
    banner = next((t for _, t in capture if t.startswith("READY WEEK8")), "")
    report = {"schema": f"week8-check-{args.kind}/1", "session": str(args.session),
              "status": "PASS" if all(result["checks"].values()) else "FAIL",
              "device_banner": wc.kv(banner), **result,
              "tool_sha256": {n: wc.sha256_file(HERE / n)
                              for n in ("check_week8.py", "week8_common.py", "week7_common.py",
                                        "week8_edge.py", "week8_tail_worker.py")}}
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, ok in result["checks"].items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"RESULT: {report['status']} ({args.kind})")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
