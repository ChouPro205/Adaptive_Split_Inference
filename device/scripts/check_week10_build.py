#!/usr/bin/env python3
"""Offline checks of a week 10 build (TC1): ble/ble-usb (radio on, W10-D4) and prot/prot-usb (radio off,
NVS nonce + I2 protect linked, W10-D1). For ble/ble-usb: Flash end before NVS (the nonce store of weeks
6-9 stays untouched), variant configuration, BLE configuration of weeks 7-8 (one connection, ASI-SV1,
ATT MTU 247, 4 TX credits, CSPRNG request IDs), numerics flags, the build ID, the W8-D3 set SHA-256 and
the W10-D4 plan SHA-256 inside the image, the week 10 modules linked instead of the week 7-9 ones, the
week 8 ble_link (off-air after the session) and no NVS nonce or I2 protect code linked (rho0 only,
W10-D4); the ble image also has no USB, console, printk or log.

Reads only build outputs (zephyr.elf/.bin/.map, .config, zephyr.dts, compile_commands.json); no device
access. Exit 0 = PASS, 1 = FAIL. Writes a JSON report to a new path. Helpers are imported from
check_week6_build.py and check_week7_build.py (unchanged).
"""
import argparse
import json
import pathlib
import sys

from check_week6_build import (APP_START, BIN_LIMIT, NVS_SIZE, NVS_START, elf_load_end,
                               ram_static_bytes, read_config, sha256, storage_partition)
from check_week7_build import L2CAP_HDR, compile_flags, symbols

KCONFIG_KEYS = (
    "CONFIG_WEEK10_BLE_USB", "CONFIG_WEEK10_BLE", "CONFIG_WEEK10_PROT_USB", "CONFIG_WEEK10_PROT", "CONFIG_WEEK10_CYCLE_GAP_MS", "CONFIG_WEEK10_BOOT_IDLE_S",
    "CONFIG_WEEK10_CONNECTED_IDLE_S", "CONFIG_WEEK10_SETTLE_S", "CONFIG_WEEK10_SELFTEST_MS",
    "CONFIG_WEEK10_CTRL_MIN_US", "CONFIG_WEEK10_RESPONSE_TIMEOUT_MS", "CONFIG_WEEK10_CONN_INTERVAL_1250US",
    "CONFIG_FLASH_LOAD_OFFSET", "CONFIG_FLASH_LOAD_SIZE", "CONFIG_SIZE_OPTIMIZATIONS", "CONFIG_BT",
    "CONFIG_BT_MAX_CONN", "CONFIG_BT_DEVICE_NAME", "CONFIG_BT_L2CAP_TX_MTU", "CONFIG_BT_BUF_ACL_TX_COUNT",
    "CONFIG_BT_ATT_TX_COUNT", "CONFIG_USB_DEVICE_STACK_NEXT", "CONFIG_SERIAL", "CONFIG_CONSOLE",
    "CONFIG_PRINTK", "CONFIG_LOG", "CONFIG_MAIN_STACK_SIZE", "CONFIG_MAIN_THREAD_PRIORITY")
# rho0 only (W10-D4): no nonce reservation, no Flash write, no I2 protect in the cycle.
NONCE_I2_SYMBOLS = ("nonce_nvs_init", "nonce_nvs_allocate", "nvs_mount", "nvs_write", "pkt_protect",
                    "g2_cycle_run", "energy_cycle_run", "dev_cycle_run")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=pathlib.Path)
    parser.add_argument("--variant", required=True, choices=["ble-usb", "ble", "prot-usb", "prot"])
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--set-sha256", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    if args.output.exists():
        sys.exit(f"refusing to overwrite {args.output}")

    zdir = args.build / "zephyr"
    elf, binf = zdir / "zephyr.elf", zdir / "zephyr.bin"
    config = read_config(zdir / ".config")
    map_text = (zdir / "zephyr.map").read_text(encoding="utf-8", errors="replace")
    load_end, load_start, segments = elf_load_end(elf)
    image = binf.read_bytes()
    bin_size = len(image)
    dts = (zdir / "zephyr.dts").read_text(encoding="utf-8")
    partition = storage_partition(dts)
    on = lambda key: config.get(key) == "y"  # noqa: E731
    flags = {name: compile_flags(args.build, name) for name in (
        "week7/head_fast.c", "week5/quantization.c", "week10/ble_cycle.c", "week10/main.c",
        "week8/ble_link.c", "week6/ble_link.c", "week7/main.c", "week7/energy_cycle.c", "week8/main.c",
        "week8/g2_cycle.c", "week9/main.c", "week9/dev_cycle.c", "week6/nonce_nvs.c", "week6/nonce_store.c",
        "week10/prot/main.c", "week10/prot/prot_cycle.c")}
    syms = symbols(map_text, ["head_fast_run", "marker_ctrl_on", "ble_cycle_run_plan", "week8_inputs",
                              "week10_ble_plan", "sha256_update", "link_init", "bt_enable", "link_disconnect",
                              "pkt_encode", "i1v2_parse_response", "z_impl_sys_csrand_get", "prot_cycle_run_plan",
                              "week10_prot_plan", "mpsl_init", "link_cycles", *NONCE_I2_SYMBOLS])
    att_mtu = int(config.get("CONFIG_BT_L2CAP_TX_MTU", "0"))

    common = {
        "flash_load_offset_0x1000": int(config.get("CONFIG_FLASH_LOAD_OFFSET", "-1"), 0) == APP_START,
        "flash_load_size_limits_to_nvs": int(config.get("CONFIG_FLASH_LOAD_SIZE", "0"), 0) == BIN_LIMIT,
        "elf_starts_at_app_start": load_start == APP_START,
        "elf_ends_before_nvs": load_end <= NVS_START,
        "bin_fits_before_nvs": bin_size <= BIN_LIMIT,
        "bin_matches_elf_span": bin_size == load_end - load_start,
        "storage_partition_0xdc000_16k": partition == (NVS_START, NVS_SIZE),
        "build_id_in_image": args.build_id.encode() in image,
        "set_sha256_in_image": f"WEEK10_SET_SHA256={args.set_sha256}".encode() in image,
        "fast_kernel_linked": syms["head_fast_run"],
        "d4_marker_linked": syms["marker_ctrl_on"],
        "project_size_optimized": on("CONFIG_SIZE_OPTIMIZATIONS"),
    }
    checks = {
        **common,
        "plan_sha256_in_image": f"WEEK10_BLE_PLAN_SHA256={args.plan_sha256}".encode() in image,
        "variant_selected": on({"ble-usb": "CONFIG_WEEK10_BLE_USB", "ble": "CONFIG_WEEK10_BLE"}.get(args.variant, "")),
        "session_timings_w10_d4": config.get("CONFIG_WEEK10_CYCLE_GAP_MS") == "1000"
                                  and config.get("CONFIG_WEEK10_BOOT_IDLE_S") == "30"
                                  and config.get("CONFIG_WEEK10_CONNECTED_IDLE_S") == "30"
                                  and config.get("CONFIG_WEEK10_RESPONSE_TIMEOUT_MS") == "5000",
        "conn_interval_15_ms_k0": config.get("CONFIG_WEEK10_CONN_INTERVAL_1250US") == "12",
        "week10_modules_compiled": all(flags[n] for n in ("week10/main.c", "week10/ble_cycle.c", "week8/ble_link.c")),
        "week6_to_9_main_cycles_and_week6_ble_link_not_compiled": not any(flags[n] for n in (
            "week6/ble_link.c", "week7/main.c", "week7/energy_cycle.c", "week8/main.c", "week8/g2_cycle.c",
            "week9/main.c", "week9/dev_cycle.c", "week6/nonce_nvs.c", "week6/nonce_store.c")),
        "ble_cycle_inputs_plan_linked": syms["ble_cycle_run_plan"] and syms["week8_inputs"]
                                        and syms["week10_ble_plan"] and syms["sha256_update"],
        "link_and_i1v2_linked": syms["link_init"] and syms["bt_enable"] and syms["pkt_encode"]
                                and syms["i1v2_parse_response"],
        "csprng_for_request_id": on("CONFIG_CSPRNG_ENABLED") and syms["z_impl_sys_csrand_get"],
        "no_nonce_nvs_or_protect_linked": not any(syms[n] for n in NONCE_I2_SYMBOLS),
        "no_fp_contraction": all("-ffp-contract=off" in flags[n] for n in (
            "week7/head_fast.c", "week5/quantization.c", "week10/ble_cycle.c")),
        "bt_enabled": on("CONFIG_BT"),
        "single_connection": config.get("CONFIG_BT_MAX_CONN") == "1",
        "device_name": config.get("CONFIG_BT_DEVICE_NAME") == "ASI-SV1",
        "configured_att_mtu_247": att_mtu == 247,
        "acl_rx_fits_mtu": int(config.get("CONFIG_BT_BUF_ACL_RX_SIZE", "0")) >= att_mtu + L2CAP_HDR,
        "tx_credits_4_available": int(config.get("CONFIG_BT_BUF_ACL_TX_COUNT", "0")) >= 4,
        "att_tx_buffers_above_credits": int(config.get("CONFIG_BT_ATT_TX_COUNT", "0")) > 4,
    }
    if args.variant.startswith("prot"):
        # W10-D1: radio off, the week 6 NVS nonce store and I2 protect linked, the prot plan in the image.
        checks = {
            **common,
            "plan_sha256_in_image": f"WEEK10_PROT_PLAN_SHA256={args.plan_sha256}".encode() in image,
            "variant_selected": on({"prot-usb": "CONFIG_WEEK10_PROT_USB", "prot": "CONFIG_WEEK10_PROT"}[args.variant]),
            "session_timings_w10_d1": config.get("CONFIG_WEEK10_CYCLE_GAP_MS") == "1000"
                                      and config.get("CONFIG_WEEK10_BOOT_IDLE_S") == "30",
            "prot_modules_compiled": all(flags[n] for n in ("week10/prot/main.c", "week10/prot/prot_cycle.c",
                                                             "week6/nonce_nvs.c", "week6/nonce_store.c")),
            "other_mains_cycles_and_ble_links_not_compiled": not any(flags[n] for n in (
                "week10/main.c", "week10/ble_cycle.c", "week8/ble_link.c", "week6/ble_link.c", "week7/main.c",
                "week7/energy_cycle.c", "week8/main.c", "week8/g2_cycle.c", "week9/main.c", "week9/dev_cycle.c")),
            "prot_cycle_inputs_plan_linked": syms["prot_cycle_run_plan"] and syms["week8_inputs"]
                                             and syms["week10_prot_plan"],
            "nonce_nvs_and_protect_linked": syms["nonce_nvs_init"] and syms["nonce_nvs_allocate"]
                                            and syms["pkt_protect"] and syms["nvs_mount"] and syms["link_cycles"],
            "no_fp_contraction": all("-ffp-contract=off" in flags[n] for n in (
                "week7/head_fast.c", "week5/quantization.c", "week10/prot/prot_cycle.c")),
            "no_bt": not on("CONFIG_BT") and not any(syms[n] for n in ("bt_enable", "link_init", "mpsl_init")),
            "nvs_enabled_with_data_crc": on("CONFIG_NVS") and on("CONFIG_NVS_DATA_CRC"),
            "nvs_never_auto_formats": "CONFIG_NVS_INIT_BAD_MEMORY_REGION" not in config,
        }
    if args.variant in ("ble", "prot"):
        checks.update({
            "no_usb_stack": not on("CONFIG_USB_DEVICE_STACK_NEXT") and not on("CONFIG_USB_DEVICE_STACK"),
            "no_serial_console_printk_log": not any(on(k) for k in (
                "CONFIG_SERIAL", "CONFIG_CONSOLE", "CONFIG_PRINTK", "CONFIG_LOG")),
        })
    if args.variant == "ble":
        checks["session_ends_off_air"] = syms["link_disconnect"]
    if args.variant.endswith("-usb"):
        checks["usb_console"] = on("CONFIG_USB_DEVICE_STACK_NEXT") and on("CONFIG_PRINTK")

    report = {
        "schema": "week10-build-check/1",
        "variant": args.variant,
        "kernel": "fast",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "scope": "STATIC_BUILD_ONLY; q/scale/request bytes and the KV260 labels need the dongle (TC2)",
        "checks": checks,
        "elf_sha256": sha256(elf),
        "bin_sha256": sha256(binf),
        "bin_bytes": bin_size,
        "bin_limit_bytes": BIN_LIMIT,
        "headroom_bytes": BIN_LIMIT - bin_size,
        "image_end_hex": hex(load_end),
        "load_segments": segments,
        "ram_static_bytes": ram_static_bytes(elf),
        "build_id": args.build_id,
        "set_sha256": args.set_sha256,
        "plan_sha256": args.plan_sha256,
        "compile_flags": {n: f for n, f in flags.items() if f},
        "kconfig": {k: config.get(k) for k in KCONFIG_KEYS},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"image end {hex(load_end)} / limit {hex(NVS_START)}; bin {bin_size} B, headroom "
          f"{BIN_LIMIT - bin_size} B; RAM static {report['ram_static_bytes']} B")
    print(f"RESULT: {report['status']} ({args.variant})")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
