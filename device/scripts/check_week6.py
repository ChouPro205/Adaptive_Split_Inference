#!/usr/bin/env python3
"""Offline checkers of week 6 evidence captured by week6_lab.py (docs/week6_device_edge_plan.md).

Expected values are recomputed here from the authenticated sources (SV3 P1 package,
contracts/i1v2_ref/vectors.json, the reference parsers); flags printed by the firmware
(match=1, result=PASS) are never trusted on their own.

  selftest  criteria 1-2 (+ DWT for criterion 8): ENC goldens, RESP cases, 50 P1 lines, QUANT
  loopback  criteria 3-5 (+ RTT/DWT for criterion 8): one RUN, device counters + peer log
  nonce     criterion 7: sequences never repeat/decrease across every boot of one or more sessions
  negative  criterion 6: one scenario dir (or a parent dir of scenario dirs)
  sentinel  criterion 7 / nonce §8 item 6: sentinel + NONCE_STATE survive a DFU
Exit 0 = PASS, 1 = FAIL, 2 = unusable input. Writes a JSON report to a NEW --output path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import week6_common as wc  # noqa: E402
import i1_ble_binding as ble  # noqa: E402
import i1v2_reference as ref  # noqa: E402

CPU_HZ = 64_000_000


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def lines_after(capture: list, marker: str) -> list:
    """Device lines after the LAST host annotation containing marker."""
    start = 0
    for i, (_, text) in enumerate(capture):
        if text.startswith("#HOST") and marker in text:
            start = i + 1
    return [(t, x) for t, x in capture[start:] if not x.startswith("#HOST")]


def tagged(lines: list, tag: str) -> list:
    return [wc.kv(text) for _, text in lines if text.startswith(tag + " ") or text == tag]


def stats(values: list) -> dict:
    if not values:
        return {}
    ordered = sorted(values)
    return {"n": len(values), "min": ordered[0], "median": statistics.median(ordered),
            "p95": ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))], "max": ordered[-1]}


def finish(args, report: dict) -> int:
    failed = [name for name, ok in report["checks"].items() if not ok]
    report["status"] = "PASS" if not failed else "FAIL"
    report["failed_checks"] = failed
    wc.write_new_json(args.output, report)
    for name, ok in report["checks"].items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"RESULT: {report['status']} -> {args.output}")
    return 0 if not failed else 1


def banner(capture: list) -> dict:
    found = [wc.kv(text) for _, text in capture if text.startswith("READY WEEK6 ")]
    return found[-1] if found else {}


# ---------------------------------------------------------------------------- selftest

def check_selftest(args) -> int:
    capture = wc.read_capture(Path(args.session) / "cdc.log")
    contract_raw = (wc.REF / "vectors.json").read_bytes()
    contract = json.loads(contract_raw)
    package = Path(args.package)
    from generate_week6_vectors import verify_package
    verify_package(package, wc.PACKAGE_MANIFEST_SHA256)
    vectors = sorted(json.loads((package / "vectors.json").read_text(encoding="utf-8"))["vectors"],
                     key=lambda v: int(v["vector_index"]))
    ready = banner(capture)
    checks = {
        "banner_present": bool(ready),
        "banner_package_manifest": ready.get("vectors_manifest") == wc.PACKAGE_MANIFEST_SHA256,
        "banner_i1v2_vectors": ready.get("i1v2_vectors") == sha(contract_raw),
    }

    enc_lines = {e["id"]: e for e in tagged(lines_after(capture, "SEND SELFTEST ENC"), "ENC") if "id" in e}
    expected_enc = {"plain_s10": contract["golden"]["plain_s10"]["packet_hex"],
                    "i2_s10": contract["golden"]["i2_s10"]["packet_hex"]}
    expected_enc.update({b["id"]: b["packet_hex"] for b in contract["boundary"]})
    enc_ok = {}
    for name, packet_hex in expected_enc.items():
        packet = bytes.fromhex(packet_hex)
        line = enc_lines.get(name, {})
        enc_ok[name] = line.get("sha256") == sha(packet) and line.get("len") == str(len(packet))
    checks["encoder_goldens_byte_exact"] = all(enc_ok.values()) and len(enc_ok) == 4

    resp_lines = {r["id"]: r for r in tagged(lines_after(capture, "SEND SELFTEST ENC"), "RESP")}
    resp_ok = {}
    for case in contract["response"]:
        try:
            kind, value = ref.parse_response(bytes.fromhex(case["packet_hex"]), case["expected_request_id"], 6380)
            want = ("OK", "0") if kind == "OK" else ("ERROR", str(value))
        except ref.Drop:
            want = ("DROP", "0")
        line = resp_lines.get(case["id"], {})
        resp_ok[case["id"]] = (line.get("result"), line.get("status")) == want
    checks["response_checks_match_reference"] = all(resp_ok.values()) and len(resp_ok) == 15

    p1 = {int(e["i"]): e for e in tagged(lines_after(capture, "SEND SELFTEST P1"), "P1") if "i" in e}
    rows, with_0x80 = [], 0
    for v in vectors:
        i = int(v["vector_index"])
        files = {k: (package / p).read_bytes() for k, p in v["files"].items()}
        line = p1.get(i, {})
        n80 = files["transformed"].count(0x80)
        with_0x80 += n80 > 0
        _, channels, length = json.loads(v["shape"]) if isinstance(v["shape"], str) else v["shape"]
        row = {
            "i": i, "s": int(v["split_point_s"]),
            "present": bool(line),
            "identity": (line.get("s"), line.get("split"), line.get("C"), line.get("L"), line.get("seq")) ==
                        (str(v["split_point_s"]), str(v["wire_split_id"]), str(channels), str(length),
                         str(v["sequence"])),
            "transformed_equals_python": line.get("tr_sha256") == sha(files["transformed"]),
            "unprotect_byte_exact": line.get("roundtrip") == "1",
            "n80_equals_package": line.get("n80") == str(n80),
            "request_equals_python": line.get("req_sha256") == sha(files["request"]) and
                                     line.get("req_len") == str(len(files["request"])),
            "descriptor_equals_package": line.get("desc_ok") == "1",
        }
        row["pass"] = all(row[k] for k in row if k not in ("i", "s"))
        for key in ("prot_cyc", "unprot_cyc", "enc_cyc", "sha_cyc"):
            row[key] = int(line[key]) if key in line else None
        rows.append(row)
    checks["p1_fifty_lines"] = len(p1) == 50 and all(r["present"] for r in rows)
    checks["criterion_1_transformed_c_equals_python_50_of_50"] = all(
        r["transformed_equals_python"] and r["identity"] and r["descriptor_equals_package"] for r in rows)
    checks["criterion_2_unprotect_byte_exact_50_of_50"] = all(r["unprotect_byte_exact"] for r in rows)
    checks["criterion_2_some_transformed_has_0x80"] = with_0x80 >= 1 and all(r["n80_equals_package"] for r in rows)
    checks["requests_byte_exact_50_of_50"] = all(r["request_equals_python"] for r in rows)
    quant = tagged(lines_after(capture, "SEND SELFTEST QUANT"), "QUANT")
    quant = [q for q in quant if "i" in q]
    checks["quantize_ran_50"] = len(quant) == 50 and all(q.get("status") == "0" for q in quant)

    by_split = {}
    for r in rows:
        by_split.setdefault(r["s"], []).append(r)
    dwt = {}
    for s, group in sorted(by_split.items()):
        entry = {}
        for key in ("prot_cyc", "unprot_cyc", "enc_cyc"):
            values = [g[key] for g in group if g[key] is not None]
            entry[key] = stats(values)
            entry[key.replace("_cyc", "_us_median")] = (statistics.median(values) * 1e6 / CPU_HZ) if values else None
        q = [int(x["cyc"]) for x in quant if int(x.get("s", -1)) == s]
        entry["quant_cyc"] = stats(q)
        dwt[f"s{s}"] = entry
    report = {
        "schema": "week6-check-selftest/1", "session": str(args.session), "build": ready.get("build"),
        "variant": ready.get("variant"), "checks": checks, "encoder": enc_ok, "responses": resp_ok,
        "p1_vectors": rows, "vectors_with_0x80": with_0x80, "dwt_cycles_by_split": dwt,
        "dwt_clock_hz": CPU_HZ,
        "stack": [wc.kv(t) | {"name": t.split()[1]} for _, t in capture if t.startswith("STACK ")][-16:],
    }
    return finish(args, report)


# ---------------------------------------------------------------------------- loopback

def last_run(capture: list) -> dict:
    begin = None
    for i, (_, text) in enumerate(capture):
        if text.startswith("RUN BEGIN "):
            begin = i
    if begin is None:
        return {}
    block = [x for _, x in capture[begin:] if not x.startswith("#HOST")]
    out = {"begin": wc.kv(block[0]), "pkts": [], "end": {}, "counters": {}, "reasm": {}}
    for text in block[1:]:
        if text.startswith("PKT "):
            out["pkts"].append(wc.kv(text))
        elif text.startswith("RUN END "):
            out["end"] = wc.kv(text)
        elif text.startswith("COUNTERS ") and not out["counters"]:
            out["counters"] = {k: int(v) for k, v in wc.kv(text).items()}
        elif text.startswith("REASM") and not out["reasm"]:
            out["reasm"] = {k: int(v) for k, v in wc.kv(text).items()}
        elif text.startswith("RUN BEGIN "):
            break
    return out


def read_peer(session: Path) -> list:
    path = session / "peer.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def check_loopback(args) -> int:
    session = Path(args.session)
    capture = wc.read_capture(session / "cdc.log")
    run = last_run(capture)
    if not run or not run["end"] or not run["counters"]:
        print("FAIL no complete RUN block in cdc.log")
        return 2
    c, pkts, mtu = run["counters"], run["pkts"], args.expect_mtu
    peer = read_peer(session)
    peer_rx = {}
    for e in peer:
        if e.get("ev") == "rx_frame":
            peer_rx.setdefault((e["request_id"], e["length"], e["crc"]), []).append(e)
    sent = [p for p in pkts if "len" in p and "frags" in p]   # NOT_SENT lines carry no transfer
    sizes = {}
    for p in sent:
        sizes.setdefault(int(p["len"]), []).append(p)
    required = [int(s) for s in args.require_sizes.split(",")] if args.require_sizes else []
    rids = [int(p["rid"], 16) for p in pkts if "rid" in p]
    seqs = [int(p["seq"]) for p in sent if p.get("flags") == "2"]
    chunk = mtu - 11
    checks = {
        "run_not_aborted": run["end"].get("aborted") == "0",
        "requested_equals_count": run["end"].get("requested") == str(args.count),
        "planned_equals_count": c.get("planned") == args.count,
        "one_pkt_line_per_planned_packet": len(pkts) == c.get("planned"),
        "all_counters_reported": all(k in c for k in wc.EXCH_COUNTERS),
        "completed_equals_planned": c.get("completed") == c.get("planned"),
        "failed_zero": c.get("failed") == 0,
        "crc_fail_zero": c.get("crc_fail") == 0,
        "byte_mismatch_zero": c.get("byte_mismatch") == 0,
        "every_pkt_ok": all(p.get("res") == "OK" for p in pkts),
        "sent_first_equals_planned": c.get("sent_first") == c.get("planned"),
        "mode_echo_or_normal": run["begin"].get("mode") in ("ECHO", "NORMAL"),
        "att_mtu_as_expected": run["begin"].get("att_mtu") == str(mtu) and
                               all(p.get("mtu") == str(mtu) for p in sent),
        "fragment_count_matches_mtu": all(int(p["frags"]) == -(-int(p["len"]) // chunk) for p in sent),
        "request_ids_unique_nonzero": len(set(rids)) == len(rids) and 0 not in rids,
        "i2_sequences_strictly_increasing": all(b > a for a, b in zip(seqs, seqs[1:])) and all(s > 0 for s in seqs),
        "required_sizes_present": all(s in sizes for s in required),
    }
    if run["begin"].get("mode") == "ECHO":
        matched = [bool(peer_rx.get((int(p["rid"], 16), int(p["len"]), p["crc"]))) for p in sent]
        checks["peer_received_every_frame_over_ble"] = bool(peer) and all(matched)
        checks["peer_crc_all_ok"] = bool(peer) and all(e["crc_ok"] for e in peer if e.get("ev") == "rx_frame")
    per_size = {}
    for size, group in sorted(sizes.items()):
        rtt = [int(p["rtt_us"]) / 1000 for p in group if p.get("res") == "OK"]
        tx_ms = [int(p["tx_ms"]) for p in group]
        per_size[str(size)] = {
            "count": len(group), "flags": sorted({p["flags"] for p in group}),
            "s": sorted({p["s"] for p in group}), "fragments": int(group[0]["frags"]),
            "rtt_ms": stats(rtt), "first_attempt_tx_ms": stats(tx_ms),
            "tx_cycles": stats([int(p["tx_cyc"]) for p in group]),
            "enc_cycles": stats([int(p["enc_cyc"]) for p in group]),
            "prot_cycles": stats([int(p["prot_cyc"]) for p in group if p["flags"] == "2"]),
            "echo_goodput_bytes_per_s": (2 * size * len(rtt) / (sum(rtt) / 1000)) if rtt else None,
        }
    report = {
        "schema": "week6-check-loopback/1", "session": str(session), "run_begin": run["begin"],
        "run_end": run["end"], "counters": c, "reassembly": run["reasm"], "checks": checks,
        "success_rate": (c.get("completed", 0) / c["planned"]) if c.get("planned") else None,
        "per_size": per_size, "i2_packets": len(seqs), "plain_packets": len(sent) - len(seqs),
        "binding_config": [wc.kv(t) for _, t in capture if t.startswith("CONFIG ")][-1:] or None,
        "stack": [wc.kv(t) | {"name": t.split()[1]} for _, t in capture if t.startswith("STACK ")][-16:],
        "peer_counts": next((e for e in reversed(peer) if e.get("ev") == "peer_counts"), None),
    }
    return finish(args, report)


# ---------------------------------------------------------------------------- nonce

def boots(capture: list) -> list:
    """Split a capture into boots; each starts at a READY WEEK6 banner."""
    out, current, pending_kind = [], None, None
    for _, text in capture:
        if text.startswith("#HOST CYCLE"):
            pending_kind = wc.kv(text).get("kind")
            continue
        if text.startswith("#HOST"):
            continue
        if text.startswith("READY WEEK6 "):
            current = {"banner": wc.kv(text), "cause": pending_kind, "boot": {}, "nonce": None,
                       "seq": [], "ntest": [], "nonce_lines": [], "alloc": [], "events": []}
            pending_kind = None
            out.append(current)
            continue
        if current is None:
            continue
        current["events"].append(text)
        if text.startswith("BOOT reset_cause="):
            current["boot"] = wc.kv(text)
        elif text.startswith("NONCE status="):
            k = wc.kv(text)
            if current["nonce"] is None:
                current["nonce"] = k
            current["nonce_lines"].append(k)
        elif text.startswith("SEQ "):
            current["seq"].append(int(text.split()[1]))
        elif text.startswith("NTEST "):
            current["ntest"].append(text)
        elif text.startswith("NONCE ALLOC "):
            current["alloc"].append(wc.kv(text))
    return out


def check_nonce(args) -> int:
    all_boots = []
    for session in args.session:
        all_boots += boots(wc.read_capture(Path(session) / "cdc.log"))
    if not all_boots:
        print("FAIL no boot banner found")
        return 2
    used, decreases, below_persisted, not_ready = [], 0, 0, 0
    highest = 0
    for b in all_boots:
        reserved = int(b["nonce"]["reserved_through"]) if b["nonce"] else -1
        if b["nonce"] is None or b["nonce"].get("status") != "READY":
            not_ready += 1
        if reserved < highest:
            below_persisted += 1        # a boot that could hand out an already used sequence
        for s in b["seq"] + [int(a["first"]) for a in b["alloc"] if a.get("got") not in (None, "0")] + \
                [int(a["last"]) for a in b["alloc"] if a.get("got") not in (None, "0")]:
            if s <= highest:
                decreases += 1
            highest = max(highest, s)
            used.append(s)
    soft = [b for b in all_boots if b["cause"] == "SOFT_RESET"]
    power = [b for b in all_boots if b["cause"] == "POWER_CUT"]
    in_write = [b for b in soft if b["boot"].get("boot_in_write") == "1"]
    checks = {
        "sequences_never_repeat_or_decrease": decreases == 0 and len(used) == len(set(used)),
        "every_boot_reserved_through_covers_used": below_persisted == 0,
        "soft_resets_at_least": len(soft) >= args.min_soft,
        "power_cuts_at_least": len(power) >= args.min_power,
        "sequences_observed": len(used) > 0 or args.hooks,
    }
    hook_report = {}
    if args.hooks:
        text = "\n".join(t for b in all_boots for t in b["ntest"])
        checks["failwrite_latched_fault_without_more_writes"] = \
            "NTEST FAILWRITE" in text and "reason=WRITE_FAILED" in text and \
            any("NTEST FAILWRITE" in t and "result=PASS" in t for b in all_boots for t in b["ntest"])
        checks["readback_latched_fault"] = any("NTEST READBACK" in t and "result=PASS" in t and
                                               "reason=READBACK" in t for b in all_boots for t in b["ntest"])
        expect = {"STATE_CRC": ("FAULT", "STATE_CRC"), "STATE_MISSING": ("FAULT", "STATE_MISSING"),
                  "PROVISION_CORRUPT": ("FAULT", "PROVISION_CORRUPT"),
                  "KEY_MISMATCH": ("FAULT", "STATE_KEY_MISMATCH"), "NONE": ("READY", "NONE")}
        for hook, (status, reason) in expect.items():
            ok = False
            for b in all_boots:
                events = b["events"]
                for idx, t in enumerate(events):
                    if not t.startswith(f"NTEST BOOT hook={hook} "):
                        continue
                    after = next((wc.kv(e) for e in events[idx + 1:] if e.startswith("NONCE status=")), {})
                    ok = wc.kv(t).get("storage_writes_during_boot") == "0" and                         (after.get("status"), after.get("reason")) == (status, reason)
                    hook_report[hook] = {"line": t, "nonce_after": after}
            checks[f"boot_hook_{hook.lower()}_gives_{status.lower()}_without_writing"] = ok
        checks["ready_again_after_real_reboot"] = all_boots[-1]["nonce"] is not None and \
            all_boots[-1]["nonce"].get("status") == "READY"
        checks["sequences_observed"] = any(b["alloc"] for b in all_boots)
    report = {
        "schema": "week6-check-nonce/1", "sessions": [str(s) for s in args.session], "checks": checks,
        "boots": len(all_boots), "soft_resets": len(soft), "power_cuts": len(power),
        "soft_resets_landing_in_nvs_write": len(in_write),
        "boots_not_ready": not_ready, "sequences_used": len(used),
        "highest_sequence": highest, "first_reserved_through": all_boots[0]["nonce"].get("reserved_through")
        if all_boots[0]["nonce"] else None,
        "last_reserved_through": all_boots[-1]["nonce"].get("reserved_through") if all_boots[-1]["nonce"] else None,
        "hooks": hook_report,
        "note": "SOFT_RESET = sys_reboot from a timer inside the stress loop; POWER_CUT = USB unplugged by "
                "the operator. boot_in_write comes from a RAM marker that only survives soft resets.",
    }
    return finish(args, report)


# ---------------------------------------------------------------------------- negative

def check_one_negative(session: Path, name: str) -> dict:
    spec = wc.NEGATIVE_SCENARIOS[name]
    capture = wc.read_capture(session / "cdc.log")
    run = last_run(capture)
    peer = read_peer(session)
    counts = next((e for e in reversed(peer) if e.get("ev") == "peer_counts"), {})
    checks = {"run_complete": bool(run and run["end"] and run["counters"])}
    if checks["run_complete"]:
        c, r = run["counters"], run["reasm"]
        checks["planned_equals_count"] = c.get("planned") == spec["count"] and len(run["pkts"]) == spec["count"]
        for key, value in spec["expect"].items():
            checks[f"{key}=={value}"] = c.get(key) == value
        for key, value in spec.get("reasm_min", {}).items():
            checks[f"reasm.{key}>={value}"] = r.get(key, 0) >= value
        checks["fault_was_applied_by_peer"] = counts.get("faults_applied", 0) >= 1
    return {"scenario": name, "spec": spec, "checks": checks,
            "counters": run.get("counters") if run else None,
            "reassembly": run.get("reasm") if run else None,
            "pass": all(checks.values())}


def check_negative(args) -> int:
    session = Path(args.session)
    if args.scenario:
        result = check_one_negative(session, args.scenario)
        report = {"schema": "week6-check-negative/1", **result}
        return finish(args, report)
    results = [check_one_negative(d, d.name) for d in sorted(session.iterdir())
               if d.is_dir() and d.name in wc.NEGATIVE_SCENARIOS]
    checks = {r["scenario"]: r["pass"] for r in results}
    checks["all_scenarios_present"] = len(results) == len(wc.NEGATIVE_SCENARIOS)
    return finish(args, {"schema": "week6-check-negative-summary/1", "session": str(session),
                         "checks": checks, "scenarios": results})


# ---------------------------------------------------------------------------- DFU sentinel

def sentinel_state(session: Path) -> dict:
    capture = wc.read_capture(Path(session) / "cdc.log")
    out = {"banner": banner(capture), "sentinel": None, "nonce": None}
    for i, (_, text) in enumerate(capture):
        if text.startswith("SENTINEL "):
            out["sentinel"] = wc.kv(text)
            out["nonce"] = next((wc.kv(t) for _, t in capture[i + 1:] if t.startswith("NONCE status=")), None)
    return out


def check_sentinel(args) -> int:
    """Nonce §8 item 6: after DFU of another image, sentinel and NONCE_STATE are intact."""
    before, after = sentinel_state(args.before), sentinel_state(args.after)
    # A later DFU (e.g. mtu23 -> default) is compared with the image that ran just before it.
    previous = sentinel_state(args.image_before) if args.image_before else before
    b, a = before["sentinel"] or {}, after["sentinel"] or {}
    pn, an = previous["nonce"] or {}, after["nonce"] or {}
    checks = {
        "sentinel_written": b.get("op") == "WRITE" and b.get("err") == "0",
        "sentinel_read_after_dfu": a.get("op") == "READ" and a.get("err") == "0",
        "sentinel_value_unchanged": bool(b.get("value")) and a.get("value") == b.get("value"),
        "different_image_flashed": previous["banner"].get("build") != after["banner"].get("build"),
        "nonce_state_ready_after_dfu": an.get("status") == "READY",
        "reserved_through_not_decreased": int(an.get("reserved_through", -1)) >= int(pn.get("reserved_through", 0)),
        "key_check_unchanged": bool(pn.get("key_check")) and an.get("key_check") == pn.get("key_check"),
    }
    report = {"schema": "week6-check-sentinel/1", "before": before, "after": after, "checks": checks}
    if args.image_before:
        report["image_before"] = previous
    return finish(args, report)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="kind", required=True)
    p = sub.add_parser("selftest")
    p.add_argument("--session", required=True)
    p.add_argument("--package", default=str(wc.PACKAGE))
    p = sub.add_parser("loopback")
    p.add_argument("--session", required=True)
    p.add_argument("--expect-mtu", type=int, required=True)
    p.add_argument("--count", type=int, required=True)
    p.add_argument("--require-sizes")
    p = sub.add_parser("nonce")
    p.add_argument("--session", action="append", required=True, help="repeat, in chronological order")
    p.add_argument("--min-soft", type=int, default=0)
    p.add_argument("--min-power", type=int, default=0)
    p.add_argument("--hooks", action="store_true")
    p = sub.add_parser("negative")
    p.add_argument("--session", required=True)
    p.add_argument("--scenario", choices=sorted(wc.NEGATIVE_SCENARIOS))
    p = sub.add_parser("sentinel")
    p.add_argument("--before", required=True, help="session of 'week6_lab.py sentinel --op write'")
    p.add_argument("--after", required=True, help="session of '--op read' after DFU of another image")
    p.add_argument("--image-before", help="session on the image replaced by this DFU (default: --before)")
    for p in sub.choices.values():
        p.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    return {"selftest": check_selftest, "loopback": check_loopback, "nonce": check_nonce,
            "negative": check_negative, "sentinel": check_sentinel}[args.kind](args)


if __name__ == "__main__":
    sys.exit(main())
