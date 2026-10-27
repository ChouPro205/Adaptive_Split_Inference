#!/usr/bin/env python3
"""Offline checks of a week 8 build (TC1): Flash end before NVS, variant configuration, kernel
selection, numerics flags, the build ID and the W8-D3 set SHA-256 inside the image, the week 8
modules linked (g2_cycle.c, week8/ble_link.c) instead of the week 7 ones.

Reads only build outputs (zephyr.elf/.bin/.map, .config, zephyr.dts, compile_commands.json); no
device access. Exit 0 = PASS, 1 = FAIL. Writes a JSON report to a new path. Helpers are imported
from check_week6_build.py and check_week7_build.py (unchanged).
"""
import argparse
import json
import pathlib
import sys

from check_week6_build import (APP_START, BIN_LIMIT, NVS_SIZE, NVS_START, elf_load_end,
                               ram_static_bytes, read_config, sha256, storage_partition)
from check_week7_build import KCONFIG_KEYS, L2CAP_HDR, compile_flags, symbols

SPLIT = 2
NONCE_RESERVE_BLOCK = 1024


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=pathlib.Path)
    parser.add_argument("--variant", required=True, choices=["energy-usb", "energy"])
    parser.add_argument("--kernel", required=True, choices=["fast", "week4"])
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--set-sha256", required=True)
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
    partition = storage_partition((zdir / "zephyr.dts").read_text(encoding="utf-8"))
    on = lambda key: config.get(key) == "y"  # noqa: E731
    flags = {name: compile_flags(args.build, name) for name in (
        "week7/head_fast.c", "week5/quantization.c", "week8/g2_cycle.c", "week8/main.c",
        "week8/ble_link.c", "week6/ble_link.c", "week7/main.c", "week7/energy_cycle.c")}
    syms = symbols(map_text, ["head_fast_run", "week4_run_head", "marker_ctrl_on", "g2_cycle_run",
                              "energy_cycle_run", "link_init", "nonce_nvs_init", "week8_inputs"])
    acl_rx = int(config.get("CONFIG_BT_BUF_ACL_RX_SIZE", "0"))
    att_mtu = min(acl_rx - L2CAP_HDR, int(config.get("CONFIG_BT_L2CAP_TX_MTU", "0")))
    pairs = int(config.get("CONFIG_WEEK8_PAIRS", "0"))

    checks = {
        "flash_load_offset_0x1000": int(config.get("CONFIG_FLASH_LOAD_OFFSET", "-1"), 0) == APP_START,
        "flash_load_size_limits_to_nvs": int(config.get("CONFIG_FLASH_LOAD_SIZE", "0"), 0) == BIN_LIMIT,
        "elf_starts_at_app_start": load_start == APP_START,
        "elf_ends_before_nvs": load_end <= NVS_START,
        "bin_fits_before_nvs": bin_size <= BIN_LIMIT,
        "bin_matches_elf_span": bin_size == load_end - load_start,
        "storage_partition_0xdc000_16k": partition == (NVS_START, NVS_SIZE),
        "build_id_in_image": args.build_id.encode() in image,
        "set_sha256_in_image": f"WEEK8_SET_SHA256={args.set_sha256}".encode() in image,
        "variant_selected": on({"energy-usb": "CONFIG_WEEK7_ENERGY_USB",
                                "energy": "CONFIG_WEEK7_ENERGY"}[args.variant]),
        "not_bench": not on("CONFIG_WEEK7_BENCH"),
        "kernel_selected": on("CONFIG_WEEK7_KERNEL_FAST" if args.kernel == "fast"
                              else "CONFIG_WEEK7_KERNEL_WEEK4"),
        "selected_kernel_linked": syms["head_fast_run" if args.kernel == "fast" else "week4_run_head"],
        "split_2": config.get("CONFIG_WEEK7_SPLIT") == str(SPLIT),
        "pairs_fit_one_nonce_block": 0 < pairs < NONCE_RESERVE_BLOCK,
        "week8_modules_compiled": all(flags[n] for n in ("week8/main.c", "week8/g2_cycle.c",
                                                         "week8/ble_link.c")),
        "week7_main_cycle_and_week6_ble_link_not_compiled": not any(
            flags[n] for n in ("week7/main.c", "week7/energy_cycle.c", "week6/ble_link.c")),
        "g2_cycle_and_inputs_linked": syms["g2_cycle_run"] and syms["week8_inputs"]
                                      and not syms["energy_cycle_run"],
        "d4_marker_linked": syms["marker_ctrl_on"],
        "no_fp_contraction": all("-ffp-contract=off" in flags[n] for n in (
            "week7/head_fast.c", "week5/quantization.c", "week8/g2_cycle.c")),
        "project_size_optimized": on("CONFIG_SIZE_OPTIMIZATIONS"),
        "bt_enabled": on("CONFIG_BT"),
        "single_connection": config.get("CONFIG_BT_MAX_CONN") == "1",
        "device_name": config.get("CONFIG_BT_DEVICE_NAME") == "ASI-SV1",
        "configured_att_mtu_247": att_mtu == 247,
        "tx_credits_4_available": int(config.get("CONFIG_BT_BUF_ACL_TX_COUNT", "0")) >= 4,
        "att_tx_buffers_above_credits": int(config.get("CONFIG_BT_ATT_TX_COUNT", "0")) > 4,
        "nvs_enabled_with_data_crc": on("CONFIG_NVS") and on("CONFIG_NVS_DATA_CRC"),
        "nvs_never_auto_formats": "CONFIG_NVS_INIT_BAD_MEMORY_REGION" not in config,
        "flash_writes_radio_synced": on("CONFIG_SOC_FLASH_NRF_RADIO_SYNC_MPSL"),
        "csprng_for_request_id": on("CONFIG_CSPRNG_ENABLED"),
        "cycle_linked": syms["link_init"] and syms["nonce_nvs_init"],
    }
    if args.variant == "energy":
        checks.update({
            "no_usb_stack": not on("CONFIG_USB_DEVICE_STACK_NEXT") and not on("CONFIG_USB_DEVICE_STACK"),
            "no_serial_console_printk_log": not any(on(k) for k in (
                "CONFIG_SERIAL", "CONFIG_CONSOLE", "CONFIG_PRINTK", "CONFIG_LOG")),
        })
    else:
        checks["usb_console"] = on("CONFIG_USB_DEVICE_STACK_NEXT") and on("CONFIG_PRINTK")

    report = {
        "schema": "week8-build-check/1",
        "variant": args.variant,
        "kernel": args.kernel,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "scope": "STATIC_BUILD_ONLY; runtime stack/RAM/MTU and the q/scale bytes need the dongle (TC2)",
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
        "compile_flags": {n: f for n, f in flags.items() if f},
        "kconfig": {k: config.get(k) for k in (*KCONFIG_KEYS, "CONFIG_WEEK8_PAIRS")},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"image end {hex(load_end)} / limit {hex(NVS_START)}; bin {bin_size} B, headroom "
          f"{BIN_LIMIT - bin_size} B; RAM static {report['ram_static_bytes']} B")
    print(f"RESULT: {report['status']} ({args.variant}/{args.kernel})")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
