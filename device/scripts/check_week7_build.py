#!/usr/bin/env python3
"""Offline checks of a week 7 build (TC8): Flash end before NVS, variant configuration, kernel
selection, numerics flags and the build ID inside the image.

Reads only build outputs (zephyr.elf/.bin/.map, .config, zephyr.dts, compile_commands.json); no
device access. Exit 0 = PASS, 1 = FAIL. Writes a JSON report to a new path. ELF/config helpers
are imported from check_week6_build.py (unchanged).
"""
import argparse
import json
import pathlib
import re
import sys

from check_week6_build import (APP_START, BIN_LIMIT, NVS_SIZE, NVS_START, elf_load_end,
                               ram_static_bytes, read_config, sha256, storage_partition)

L2CAP_HDR = 4
FRAGMENT_OVERHEAD = 3 + 8
KCONFIG_KEYS = (
    "CONFIG_WEEK7_BENCH", "CONFIG_WEEK7_ENERGY_USB", "CONFIG_WEEK7_ENERGY",
    "CONFIG_WEEK7_KERNEL_FAST", "CONFIG_WEEK7_KERNEL_WEEK4", "CONFIG_WEEK7_SPLIT",
    "CONFIG_WEEK7_P1_CYCLES", "CONFIG_WEEK7_P0_CYCLES", "CONFIG_WEEK7_CYCLE_GAP_MS",
    "CONFIG_WEEK7_BOOT_IDLE_S", "CONFIG_WEEK7_CONNECTED_IDLE_S", "CONFIG_WEEK7_SETTLE_S",
    "CONFIG_WEEK7_SELFTEST_MS", "CONFIG_WEEK7_CTRL_MIN_US", "CONFIG_WEEK7_RESPONSE_TIMEOUT_MS",
    "CONFIG_WEEK7_CONN_INTERVAL_1250US", "CONFIG_FLASH_LOAD_OFFSET", "CONFIG_FLASH_LOAD_SIZE",
    "CONFIG_SIZE_OPTIMIZATIONS", "CONFIG_BT", "CONFIG_BT_L2CAP_TX_MTU", "CONFIG_BT_BUF_ACL_RX_SIZE",
    "CONFIG_BT_BUF_ACL_TX_COUNT", "CONFIG_BT_ATT_TX_COUNT", "CONFIG_NVS", "CONFIG_NVS_DATA_CRC",
    "CONFIG_SOC_FLASH_NRF_RADIO_SYNC_MPSL", "CONFIG_CSPRNG_ENABLED", "CONFIG_USB_DEVICE_STACK_NEXT",
    "CONFIG_SERIAL", "CONFIG_CONSOLE", "CONFIG_PRINTK", "CONFIG_LOG", "CONFIG_MAIN_STACK_SIZE",
    "CONFIG_MAIN_THREAD_PRIORITY")


def symbols(map_text: str, names) -> dict:
    """Symbols placed by the linker (the map also lists discarded sections before this part)."""
    _, _, linked = map_text.partition("Linker script and memory map")
    return {name: re.search(r"\b" + re.escape(name) + r"\b", linked) is not None for name in names}


def compile_flags(build: pathlib.Path, source_name: str) -> str:
    path = build / "compile_commands.json"
    if not path.exists():
        return ""
    for entry in json.loads(path.read_text(encoding="utf-8")):
        if entry["file"].replace("\\", "/").endswith(source_name):
            return entry.get("command") or " ".join(entry.get("arguments", []))
    return ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=pathlib.Path)
    parser.add_argument("--variant", required=True, choices=["bench", "energy-usb", "energy"])
    parser.add_argument("--kernel", required=True, choices=["fast", "week4"])
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    if args.output.exists():
        sys.exit(f"refusing to overwrite {args.output}")

    zdir = args.build / "zephyr"
    elf, binf = zdir / "zephyr.elf", zdir / "zephyr.bin"
    config = read_config(zdir / ".config")
    map_text = (zdir / "zephyr.map").read_text(encoding="utf-8", errors="replace")
    load_end, load_start, segments = elf_load_end(elf)
    bin_size = binf.stat().st_size
    partition = storage_partition((zdir / "zephyr.dts").read_text(encoding="utf-8"))
    radio = args.variant != "bench"
    on = lambda key: config.get(key) == "y"  # noqa: E731
    head_fast_flags = compile_flags(args.build, "week7/head_fast.c")
    syms = symbols(map_text, ["head_fast_run", "week4_run_head", "marker_ctrl_on",
                              "energy_cycle_run", "link_init", "nonce_nvs_init"])

    checks = {
        "flash_load_offset_0x1000": int(config.get("CONFIG_FLASH_LOAD_OFFSET", "-1"), 0) == APP_START,
        "flash_load_size_limits_to_nvs": int(config.get("CONFIG_FLASH_LOAD_SIZE", "0"), 0) == BIN_LIMIT,
        "elf_starts_at_app_start": load_start == APP_START,
        "elf_ends_before_nvs": load_end <= NVS_START,
        "bin_fits_before_nvs": bin_size <= BIN_LIMIT,
        "bin_matches_elf_span": bin_size == load_end - load_start,
        "storage_partition_0xdc000_16k": partition == (NVS_START, NVS_SIZE),
        "build_id_in_image": args.build_id.encode() in binf.read_bytes(),
        "variant_selected": on({"bench": "CONFIG_WEEK7_BENCH", "energy-usb": "CONFIG_WEEK7_ENERGY_USB",
                                "energy": "CONFIG_WEEK7_ENERGY"}[args.variant]),
        "kernel_selected": on("CONFIG_WEEK7_KERNEL_FAST" if args.kernel == "fast"
                              else "CONFIG_WEEK7_KERNEL_WEEK4"),
        "selected_kernel_linked": syms["head_fast_run" if args.kernel == "fast" else "week4_run_head"],
        "d4_marker_linked": syms["marker_ctrl_on"],
        "head_fast_no_fp_contraction": "-ffp-contract=off" in head_fast_flags,
        "project_size_optimized": on("CONFIG_SIZE_OPTIMIZATIONS"),
    }
    if radio:
        acl_rx = int(config.get("CONFIG_BT_BUF_ACL_RX_SIZE", "0"))
        att_mtu = min(acl_rx - L2CAP_HDR, int(config.get("CONFIG_BT_L2CAP_TX_MTU", "0")))
        checks.update({
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
            "cycle_linked": syms["energy_cycle_run"] and syms["link_init"] and syms["nonce_nvs_init"],
        })
    else:
        checks.update({"no_radio": not on("CONFIG_BT"), "no_nvs": not on("CONFIG_NVS"),
                       "usb_console": on("CONFIG_USB_DEVICE_STACK_NEXT") and on("CONFIG_PRINTK"),
                       "both_kernels_linked": syms["head_fast_run"] and syms["week4_run_head"]})
    if args.variant == "energy":
        checks.update({
            "no_usb_stack": not on("CONFIG_USB_DEVICE_STACK_NEXT") and not on("CONFIG_USB_DEVICE_STACK"),
            "no_serial_console_printk_log": not any(on(k) for k in (
                "CONFIG_SERIAL", "CONFIG_CONSOLE", "CONFIG_PRINTK", "CONFIG_LOG")),
        })
    elif args.variant == "energy-usb":
        checks["usb_console"] = on("CONFIG_USB_DEVICE_STACK_NEXT") and on("CONFIG_PRINTK")

    report = {
        "schema": "week7-build-check/1",
        "variant": args.variant,
        "kernel": args.kernel,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "scope": "STATIC_BUILD_ONLY; runtime stack/RAM/MTU need the dongle",
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
        "head_fast_compile_flags": head_fast_flags,
        "kconfig": {k: config.get(k) for k in KCONFIG_KEYS},
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
