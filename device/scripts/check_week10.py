#!/usr/bin/env python3
"""Offline checks of week 10 ble-usb / prot-usb sessions recorded by week10_lab.py (cdc.log), TC2.

  verify   VERIFY ALL: one VQ line per (sample 0..49, s 0..10) whose q/scale SHA-256, C, L and payload bytes
           equal the host C path (week10_ble.HostRefs = the week 9 refs checked on the dongle on 29/10); one
           VREQ line per (sample, s <= 9) whose plain request (request_id n + 1) equals the one built by
           contracts/i1v2_ref from that tensor, length = I1 v2 formula; one VLAB line per sample at s10 whose
           FP32 logits are bit-equal to the host shim and label = argmax; banner: set, plan SHA-256 and the
           device's own plan digest.
  session  SESSION <gap> <first> <count> against the KV260: one CYCLE line per plan cycle in order, (sample,
           s) = plan, result OK, label = argmax of the printed logits, s10 logits/label = host, frame length
           and payload bytes per s; with edge/summary.json of week10_lab.py import-kv260: one request per
           s <= 9 cycle in plan order (q/scale = refs), labels and logits = KV260 offline (W8-D8) at every s,
           dongle logits = KV260 log per request_id, and (with the queue directory) every request went
           through the queue_sim FIFO as a foreground job. DWT phase times per s are reported (laptop power:
           debug only, never energy numbers).
  verify-prot   prot-usb VERIFY ALL + TPROT ALL + TCONV (week10_prot.check_verify / tprot_table): q/scale of
           s0..s9, protect() with the PUBLIC_TEST key = contracts/i2_ref, HEAD-only s1 output = host shim, DWT
           t_prot per s and t_conv (50 runs each).
  session-prot  prot-usb SESSION dry run of the W10-D1 plan: order, ops, no Flash write in any cycle, P1 sequences
           strictly increasing (and above --prior-reserved-through).
Exit 0 = PASS. Writes a JSON report to a new --output path.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import week10_ble as wb  # noqa: E402
import week10_common as w10  # noqa: E402
import week6_common as wc  # noqa: E402

w8 = wb.w8


def lines_with(capture, tag: str) -> list:
    return [wc.kv(text) for _, text in capture if text.startswith(tag)]


def banner_of(capture) -> dict:
    banners = [wc.kv(t) for _, t in capture if t.startswith("READY WEEK10 ")]
    return banners[-1] if banners else {}


def banner_checks(banner: dict, host: wb.HostRefs) -> dict:
    return {
        "banner_variant_ble_usb": banner.get("variant") == "ble-usb",
        "banner_set_sha256": banner.get("set_sha256") == host.sample_set.set_sha256,
        "banner_plan_sha256": banner.get("plan_sha256") == w10.BLE_PLAN_SHA256,
        "device_plan_digest_equal": banner.get("plan_device_sha256") == w10.BLE_PLAN_SHA256
                                    and banner.get("plan_ok") == "1",
        "host_plan_digest_equal": host.plan_digest == w10.BLE_PLAN_SHA256,
        "banner_rounds_cycles": banner.get("rounds") == str(w10.ROUNDS) and banner.get("cycles") == str(w10.BLE_CYCLES),
    }


def check_verify(capture, host: wb.HostRefs) -> tuple:
    vq, vreq, vlab = lines_with(capture, "VQ n="), lines_with(capture, "VREQ n="), lines_with(capture, "VLAB n=")
    end = lines_with(capture, "VERIFY END")
    mismatches = []
    q_ok = []
    for r in vq:
        n, s = int(r["n"]), int(r["s"])
        ok = (n, s) in host.tensors
        if ok:
            c, length, qb, sb = host.tensors[(n, s)]
            ok = (r.get("id") == host.sample_set.samples[n].sample_id and int(r.get("C", -1)) == c
                  and int(r.get("L", -1)) == length and int(r.get("bytes", -1)) == c * length + 2 * c
                  and r.get("q_sha256") == wb.w9.sha256_hex(qb) and r.get("scale_sha256") == wb.w9.sha256_hex(sb))
        q_ok.append(ok)
        if not ok:
            mismatches.append({"n": n, "s": s, "what": "q/scale/id/shape"})
    req_ok = []
    for r in vreq:
        n, s, rid = int(r["n"]), int(r["s"]), int(r["rid"])
        ok = 0 <= n < wb.SAMPLES and s in wb.EDGE_SPLITS and rid == n + 1 and r.get("rho") == "P0"
        if ok:
            frame = host.request(n, s, rid)
            c, length, _, _ = host.tensors[(n, s)]
            ok = int(r["len"]) == len(frame) == wb.frame_length_p0(c, length) and r["sha256"] == wb.w9.sha256_hex(frame)
        req_ok.append(ok)
        if not ok:
            mismatches.append({"n": n, "s": s, "what": "request"})
    lab_ok = []
    for r in vlab:
        n = int(r["n"])
        bits, label = host.s10.get(n, (None, None))
        ok = int(r["s"]) == wb.DEVICE_ONLY and r.get("logits") == bits and int(r.get("label", -1)) == label
        lab_ok.append(ok)
        if not ok:
            mismatches.append({"n": n, "s": 10, "what": "s10 logits/label"})
    order = [(int(r["s"]), int(r["n"])) for r in vq]
    checks = {
        **banner_checks(banner_of(capture), host),
        "vq_every_sample_every_s_in_order": order == [(s, n) for s in range(w10.BLE_SPLITS) for n in range(wb.SAMPLES)],
        "q_scale_id_shape_equal_host": len(q_ok) == wb.SAMPLES * w10.BLE_SPLITS and all(q_ok),
        "requests_every_sample_s0_s9": sorted((int(r["s"]), int(r["n"])) for r in vreq)
                                       == [(s, n) for s in wb.EDGE_SPLITS for n in range(wb.SAMPLES)],
        "requests_equal_python_reference": len(req_ok) == wb.SAMPLES * len(wb.EDGE_SPLITS) and all(req_ok),
        "s10_logits_label_equal_host": len(lab_ok) == wb.SAMPLES and all(lab_ok),
        "verify_end_set_sha256": bool(end) and end[-1].get("set_sha256") == host.sample_set.set_sha256
                                 and end[-1].get("splits") == "ALL",
    }
    labels = {}
    for n in range(wb.SAMPLES):
        labels[host.s10[n][1]] = labels.get(host.s10[n][1], 0) + 1
    details = {"vq": len(vq), "vreq": len(vreq), "vlab": len(vlab), "mismatches": mismatches[:20],
               "s10_label_counts": {str(k): v for k, v in sorted(labels.items())}}
    return checks, details


def stats_ms(values: list) -> dict:
    v = [x / 1000.0 for x in values]
    return {"n": len(v), "mean_ms": statistics.fmean(v) if v else None, "min_ms": min(v) if v else None,
            "max_ms": max(v) if v else None}


def check_session(capture, host: wb.HostRefs, session: Path, first: int, count: int) -> tuple:
    rows = list(host.plans.ble)[first:first + count]
    cycles = lines_with(capture, "CYCLE i=")
    begin, end = lines_with(capture, "SESSION BEGIN"), lines_with(capture, "SESSION END")
    ok_lines = []
    for r in cycles:
        i = int(r["i"])
        plan = host.plans.ble[i] if 0 <= i < w10.BLE_CYCLES else None
        good = plan is not None and int(r["s"]) == plan.split and int(r["n"]) == plan.sample and r.get("res") == "OK" \
            and int(r["rho"]) == 0 and int(r["k"]) == 0 and int(r["bytes"]) == host.bytes_payload(plan.split) \
            and int(r["label"]) == w8.label(w8.logits_from_hex(r["logits"]))
        if good and plan.split == wb.DEVICE_ONLY:
            good = (r["logits"], int(r["label"])) == host.s10[plan.sample] and int(r["len"]) == 0 and int(r["rid"]) == 0
        elif good:
            c, length, _, _ = host.tensors[(plan.sample, plan.split)]
            good = int(r["len"]) == wb.frame_length_p0(c, length) and int(r["rid"]) != 0
        ok_lines.append(good)
    checks = {
        **banner_checks(banner_of(capture), host),
        "session_begin_end": bool(begin) and bool(end) and end[-1].get("ok") == str(count)
                             and end[-1].get("failed") == "0",
        "one_cycle_line_per_plan_cycle_in_order": [int(r["i"]) for r in cycles] == list(range(first, first + count)),
        "every_cycle_ok_plan_s_n_bytes_len_label": len(ok_lines) == count and all(ok_lines),
    }
    edge_file = session / "edge" / "summary.json"
    details = {"cycles": len(cycles), "first": first, "count": count}
    if edge_file.exists():
        edge = json.loads(edge_file.read_text(encoding="utf-8"))
        checks.update({f"kv260_{k}": v for k, v in edge["result"]["checks"].items()})
        details["kv260"] = {k: edge.get(k) for k in ("source_log", "source_log_sha256", "edge_reference", "counters",
                                                     "queue_match")}
        details["kv260_per_s"] = edge["result"]["per_s"]
        details["t_edge_ms_by_s"] = edge["result"]["t_edge_ms_by_s"]
    else:
        checks["kv260_log_imported"] = False
        details["kv260_log"] = "PENDING: week10_lab.py import-kv260"
    timing = {}
    for r in cycles:
        e = timing.setdefault(r["s"], {"head_us": [], "tx_us": [], "wait_us": [], "frags": []})
        for key in ("head_us", "tx_us", "wait_us", "frags"):
            e[key].append(int(r[key]))
    details["dwt_by_s_debug_only"] = {s: {"head": stats_ms(e["head_us"]), "tx": stats_ms(e["tx_us"]),
                                          "wait": stats_ms(e["wait_us"]), "fragments": sorted(set(e["frags"]))}
                                      for s, e in sorted(timing.items(), key=lambda kv: int(kv[0]))}
    return checks, details


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("kind", choices=["verify", "session", "verify-prot", "session-prot"])
    parser.add_argument("--session", type=Path, required=True, help="week10_lab.py output directory")
    parser.add_argument("--samples", type=Path, required=True, help="W8-D3 set directory")
    parser.add_argument("--plan", type=Path, required=True, help="generate_week10_plan.py directory")
    parser.add_argument("--first", type=int, default=0)
    parser.add_argument("--count", type=int, help="cycles (default: the whole plan of the kind)")
    parser.add_argument("--prior-reserved-through", type=int, help="session-prot: NONCE reserved_through before")
    parser.add_argument("--output", type=Path, required=True, help="new JSON report path")
    args = parser.parse_args()
    if args.output.exists():
        sys.exit(f"refusing to overwrite {args.output}")
    host = wb.HostRefs(args.samples, args.plan, args.session / "host_shim")
    capture = wc.read_capture(args.session / "cdc.log")
    if args.kind == "verify":
        checks, details = check_verify(capture, host)
    elif args.kind == "session":
        count = args.count if args.count is not None else w10.BLE_CYCLES
        checks, details = check_session(capture, host, args.session, args.first, count)
    else:
        import week10_prot as wpr
        banner = {}
        for _, t in capture:
            if t.startswith("READY WEEK10 "):
                banner = wc.kv(t)
        def lw(tag):  # noqa: E306
            return lines_with(capture, tag)
        if args.kind == "verify-prot":
            checks, details = wpr.check_verify(lw, banner, host)
            t_checks, t_details = wpr.tprot_table(lw)
            checks.update(t_checks)
            details.update(t_details)
        else:
            count = args.count if args.count is not None else w10.PROT_CYCLES
            checks, details = wpr.check_session(lw, banner, host, args.first, count, args.prior_reserved_through)
    status = "PASS" if all(checks.values()) else "FAIL"
    report = {"schema": f"week10-check-{args.kind}/1", "status": status, "checks": checks, "details": details,
              "scope": "dongle on laptop USB power: correctness evidence and DWT debug times, never energy numbers",
              "tools_sha256": {n: wc.sha256_file(HERE / n) for n in ("check_week10.py", "week10_ble.py", "week10_prot.py",
                                                                      "week10_common.py", "week10_lab.py")
                               if (HERE / n).exists()},
              "shim_sources_sha256": {p.relative_to(wb.ROOT).as_posix(): wc.sha256_file(p) for p in wb.SHIM_SOURCES}}
    wc.write_new_json(args.output, report)
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"RESULT: {status} ({args.kind})")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
