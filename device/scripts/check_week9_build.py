#!/usr/bin/env python3
"""Offline checks of a week 9 build (TC1): Flash end before NVS (the nonce store of weeks 6-8 stays
untouched), variant configuration, numerics flags, the build ID, the W8-D3 set SHA-256 and the W9-D4
plan SHA-256 inside the image, the week 9 modules linked instead of the week 7/8 ones, and no radio,
NVS or nonce code in either image (W9-D1); the dev image also has no USB, console, printk or log.

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
from check_week7_build import compile_flags, symbols

KCONFIG_KEYS = (
    "CONFIG_WEEK9_DEV_USB", "CONFIG_WEEK9_DEV", "CONFIG_WEEK9_CYCLE_GAP_MS", "CONFIG_WEEK9_BOOT_IDLE_S",
    "CONFIG_WEEK9_SELFTEST_MS", "CONFIG_WEEK9_CTRL_MIN_US", "CONFIG_FLASH_LOAD_OFFSET",
    "CONFIG_FLASH_LOAD_SIZE", "CONFIG_SIZE_OPTIMIZATIONS", "CONFIG_BT", "CONFIG_NVS", "CONFIG_FLASH",
    "CONFIG_USB_DEVICE_STACK_NEXT", "CONFIG_SERIAL", "CONFIG_CONSOLE", "CONFIG_PRINTK", "CONFIG_LOG",
    "CONFIG_MAIN_STACK_SIZE", "CONFIG_MAIN_THREAD_PRIORITY")
# Linked by weeks 6-8 radio images; none may be in a week 9 image (W9-D1, W9-D5).
RADIO_NONCE_SYMBOLS = ("bt_enable", "link_init", "mpsl_init", "nonce_nvs_init", "nonce_nvs_allocate",
                       "nvs_mount", "nvs_write", "pkt_protect", "g2_cycle_run", "energy_cycle_run")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=pathlib.Path)
    parser.add_argument("--variant", required=True, choices=["dev-usb", "dev"])
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
    partition = storage_partition((zdir / "zephyr.dts").read_text(encoding="utf-8"))
    on = lambda key: config.get(key) == "y"  # noqa: E731
    flags = {name: compile_flags(args.build, name) for name in (
        "week7/head_fast.c", "week5/quantization.c", "week9/dev_cycle.c", "week9/main.c",
        "week7/main.c", "week7/energy_cycle.c", "week8/main.c", "week8/g2_cycle.c")}
    syms = symbols(map_text, ["head_fast_run", "marker_ctrl_on", "dev_cycle_run", "week8_inputs",
                              "week9_plan_split", "sha256", *RADIO_NONCE_SYMBOLS])

    checks = {
        "flash_load_offset_0x1000": int(config.get("CONFIG_FLASH_LOAD_OFFSET", "-1"), 0) == APP_START,
        "flash_load_size_limits_to_nvs": int(config.get("CONFIG_FLASH_LOAD_SIZE", "0"), 0) == BIN_LIMIT,
        "elf_starts_at_app_start": load_start == APP_START,
        "elf_ends_before_nvs": load_end <= NVS_START,
        "bin_fits_before_nvs": bin_size <= BIN_LIMIT,
        "bin_matches_elf_span": bin_size == load_end - load_start,
        "storage_partition_0xdc000_16k": partition == (NVS_START, NVS_SIZE),
        "build_id_in_image": args.build_id.encode() in image,
        "set_sha256_in_image": f"WEEK9_SET_SHA256={args.set_sha256}".encode() in image,
        "plan_sha256_in_image": f"WEEK9_PLAN_SHA256={args.plan_sha256}".encode() in image,
        "variant_selected": on({"dev-usb": "CONFIG_WEEK9_DEV_USB", "dev": "CONFIG_WEEK9_DEV"}[args.variant]),
        "gap_1000_ms_idle_30_s": config.get("CONFIG_WEEK9_CYCLE_GAP_MS") == "1000"
                                 and config.get("CONFIG_WEEK9_BOOT_IDLE_S") == "30",
        "fast_kernel_linked": syms["head_fast_run"],
        "week9_modules_compiled": all(flags[n] for n in ("week9/main.c", "week9/dev_cycle.c")),
        "week7_week8_main_and_cycles_not_compiled": not any(flags[n] for n in (
            "week7/main.c", "week7/energy_cycle.c", "week8/main.c", "week8/g2_cycle.c")),
        "dev_cycle_inputs_plan_linked": syms["dev_cycle_run"] and syms["week8_inputs"]
                                        and syms["week9_plan_split"] and syms["sha256"],
        "d4_marker_linked": syms["marker_ctrl_on"],
        "no_fp_contraction": all("-ffp-contract=off" in flags[n] for n in (
            "week7/head_fast.c", "week5/quantization.c", "week9/dev_cycle.c")),
        "project_size_optimized": on("CONFIG_SIZE_OPTIMIZATIONS"),
        "no_bt": not on("CONFIG_BT"),
        "no_nvs": not on("CONFIG_NVS"),
        "no_radio_nonce_i2_code_linked": not any(syms[n] for n in RADIO_NONCE_SYMBOLS),
    }
    if args.variant == "dev":
        checks.update({
            "no_usb_stack": not on("CONFIG_USB_DEVICE_STACK_NEXT") and not on("CONFIG_USB_DEVICE_STACK"),
            "no_serial_console_printk_log": not any(on(k) for k in (
                "CONFIG_SERIAL", "CONFIG_CONSOLE", "CONFIG_PRINTK", "CONFIG_LOG")),
        })
    else:
        checks["usb_console"] = on("CONFIG_USB_DEVICE_STACK_NEXT") and on("CONFIG_PRINTK")

    report = {
        "schema": "week9-build-check/1",
        "variant": args.variant,
        "kernel": "fast",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "scope": "STATIC_BUILD_ONLY; q/scale bytes and DWT t_dev need the dongle (TC2)",
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
