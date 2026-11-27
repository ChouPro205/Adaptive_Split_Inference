#!/usr/bin/env python3
"""Offline checks of a week 11 build (TC4): link/link-usb (radio on, W11-D3). Flash end before NVS (the nonce
store of weeks 6-9 stays untouched), variant configuration, the BLE configuration of weeks 7-10 (one connection,
ASI-SV1, ATT MTU 247, 4 TX credits, CSPRNG request IDs) plus the week 11 controller options (LE Coded, dynamic
TX power, connection RSSI, no automatic parameter request), numerics flags of the S0c encoder, the build ID,
the W8-D3 set SHA-256, the plan SHA-256 of the session and the S0c version inside the image, the week 11 modules
linked instead of the week 6-10 ones (no head, no I1 request, no NVS nonce or I2 protect); the link image also
has no USB, console, printk or log.

Reads only build outputs (zephyr.elf/.bin/.map, .config, zephyr.dts, compile_commands.json); no device access.
Exit 0 = PASS, 1 = FAIL. Writes a JSON report to a new path. Helpers are imported from check_week6_build.py and
check_week7_build.py (unchanged).
"""
import argparse
import json
import pathlib
import sys

from check_week6_build import (APP_START, BIN_LIMIT, NVS_SIZE, NVS_START, elf_load_end,
                               ram_static_bytes, read_config, sha256, storage_partition)
from check_week7_build import L2CAP_HDR, compile_flags, symbols

KCONFIG_KEYS = (
    "CONFIG_WEEK11_LINK_USB", "CONFIG_WEEK11_LINK", "CONFIG_WEEK11_BOOT_IDLE_S", "CONFIG_WEEK11_CONNECTED_IDLE_S",
    "CONFIG_WEEK11_SETTLE_S", "CONFIG_WEEK11_SELFTEST_MS", "CONFIG_WEEK11_CTRL_MIN_US",
    "CONFIG_WEEK11_STATE_TIMEOUT_MS", "CONFIG_WEEK11_STATE_SETTLE_MS", "CONFIG_WEEK11_ECHO_TIMEOUT_MS",
    "CONFIG_WEEK11_RECONNECT_TIMEOUT_MS", "CONFIG_WEEK11_OP_GAP_MS", "CONFIG_FLASH_LOAD_OFFSET",
    "CONFIG_FLASH_LOAD_SIZE", "CONFIG_SIZE_OPTIMIZATIONS", "CONFIG_BT", "CONFIG_BT_MAX_CONN", "CONFIG_BT_DEVICE_NAME",
    "CONFIG_BT_L2CAP_TX_MTU", "CONFIG_BT_BUF_ACL_TX_COUNT", "CONFIG_BT_ATT_TX_COUNT", "CONFIG_BT_CTLR_PHY_CODED",
    "CONFIG_BT_CTLR_TX_PWR_DYNAMIC_CONTROL", "CONFIG_BT_CTLR_CONN_RSSI", "CONFIG_BT_GAP_AUTO_UPDATE_CONN_PARAMS",
    "CONFIG_BT_CTLR_DATA_LENGTH_MAX", "CONFIG_BT_CTLR_SDC_MAX_CONN_EVENT_LEN_DEFAULT", "CONFIG_BT_CTLR_TX_PWR_DBM",
    "CONFIG_USB_DEVICE_STACK_NEXT", "CONFIG_SERIAL", "CONFIG_CONSOLE", "CONFIG_PRINTK", "CONFIG_LOG",
    "CONFIG_MAIN_STACK_SIZE", "CONFIG_MAIN_THREAD_PRIORITY")
# Nothing of the head/I1/I2/NVS paths of weeks 6-10 in the link images.
FORBIDDEN_SYMBOLS = ("nonce_nvs_init", "nonce_nvs_allocate", "nvs_mount", "nvs_write", "pkt_protect", "pkt_encode",
                     "head_fast_run", "week4_head_run", "g2_cycle_run", "energy_cycle_run", "dev_cycle_run",
                     "ble_cycle_run_plan", "prot_cycle_run_plan", "i1v2_parse_response")
OLD_SOURCES = ("week6/ble_link.c", "week8/ble_link.c", "week7/main.c", "week7/energy_cycle.c", "week7/head_fast.c",
               "week8/main.c", "week8/g2_cycle.c", "week9/main.c", "week9/dev_cycle.c", "week10/main.c",
               "week10/ble_cycle.c", "week6/nonce_nvs.c", "week6/nonce_store.c", "week6/packets.c")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=pathlib.Path)
    parser.add_argument("--variant", required=True, choices=["link-usb", "link"])
    parser.add_argument("--session", required=True, type=int, choices=[0, 1])
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
    sources = ("week11/main.c", "week11/link_cycle.c", "week11/ble_link.c", "week11/echo_frames.c",
               "week11/s0c.c", "week5/quantization.c", *OLD_SOURCES)
    flags = {name: compile_flags(args.build, name) for name in sources}
    syms = symbols(map_text, ["marker_ctrl_on", "link_run_entry", "week8_inputs", "week11_link_plan",
                              "week11_link_states", "sha256_update", "link_init", "bt_enable", "link_disconnect",
                              "link_drop", "link_request_phy", "link_set_tx_power", "link_set_latency_mode",
                              "s0c_encode", "week5_quantize", "echo_frame_build", "echo_ack_build", "i1v2_crc32",
                              "z_impl_sys_csrand_get", *FORBIDDEN_SYMBOLS])
    att_mtu = int(config.get("CONFIG_BT_L2CAP_TX_MTU", "0"))

    checks = {
        "flash_load_offset_0x1000": int(config.get("CONFIG_FLASH_LOAD_OFFSET", "-1"), 0) == APP_START,
        "flash_load_size_limits_to_nvs": int(config.get("CONFIG_FLASH_LOAD_SIZE", "0"), 0) == BIN_LIMIT,
        "elf_starts_at_app_start": load_start == APP_START,
        "elf_ends_before_nvs": load_end <= NVS_START,
        "bin_fits_before_nvs": bin_size <= BIN_LIMIT,
        "bin_matches_elf_span": bin_size == load_end - load_start,
        "storage_partition_0xdc000_16k": partition == (NVS_START, NVS_SIZE),
        "build_id_in_image": args.build_id.encode() in image,
        "set_sha256_in_image": f"WEEK11_SET_SHA256={args.set_sha256}".encode() in image,
        "plan_sha256_in_image": f"WEEK11_LINK_PLAN_SHA256={args.plan_sha256}".encode() in image,
        "s0c_version_in_image": b"WEEK11_S0C_VERSION=S0C-V1" in image,
        "d4_marker_linked": syms["marker_ctrl_on"],
        "project_size_optimized": on("CONFIG_SIZE_OPTIMIZATIONS"),
        "variant_selected": on({"link-usb": "CONFIG_WEEK11_LINK_USB", "link": "CONFIG_WEEK11_LINK"}[args.variant]),
        "session_timings": config.get("CONFIG_WEEK11_BOOT_IDLE_S") == "30"
                           and config.get("CONFIG_WEEK11_CONNECTED_IDLE_S") == "30"
                           and config.get("CONFIG_WEEK11_SETTLE_S") == "5"
                           and config.get("CONFIG_WEEK11_CTRL_MIN_US") == "200"
                           and config.get("CONFIG_WEEK11_STATE_TIMEOUT_MS") == "8000"
                           and config.get("CONFIG_WEEK11_STATE_SETTLE_MS") == "2000"
                           and config.get("CONFIG_WEEK11_ECHO_TIMEOUT_MS") == "5000"
                           and config.get("CONFIG_WEEK11_RECONNECT_TIMEOUT_MS") == "30000"
                           and config.get("CONFIG_WEEK11_OP_GAP_MS") == "250",
        "week11_modules_compiled": all(flags[n] for n in sources[:6]),
        "week6_to_10_mains_cycles_links_not_compiled": not any(flags[n] for n in OLD_SOURCES),
        "link_ops_inputs_plan_linked": syms["link_run_entry"] and syms["week8_inputs"] and syms["week11_link_plan"]
                                       and syms["week11_link_states"] and syms["sha256_update"],
        "link_state_controls_linked": all(syms[n] for n in ("link_init", "bt_enable", "link_drop", "link_request_phy",
                                                            "link_set_tx_power", "link_set_latency_mode")),
        "s0c_and_echo_frames_linked": all(syms[n] for n in ("s0c_encode", "week5_quantize", "echo_frame_build",
                                                            "echo_ack_build", "i1v2_crc32")),
        "csprng_for_request_id": on("CONFIG_CSPRNG_ENABLED") and syms["z_impl_sys_csrand_get"],
        "no_head_i1_i2_nvs_linked": not any(syms[n] for n in FORBIDDEN_SYMBOLS),
        "no_fp_contraction": all("-ffp-contract=off" in flags[n] and "-fno-fast-math" in flags[n]
                                 for n in ("week11/s0c.c", "week5/quantization.c")),
        "bt_enabled": on("CONFIG_BT"),
        "single_connection": config.get("CONFIG_BT_MAX_CONN") == "1",
        "device_name": config.get("CONFIG_BT_DEVICE_NAME") == "ASI-SV1",
        "configured_att_mtu_247": att_mtu == 247,
        "acl_rx_fits_mtu": int(config.get("CONFIG_BT_BUF_ACL_RX_SIZE", "0")) >= att_mtu + L2CAP_HDR,
        "tx_credits_4_available": int(config.get("CONFIG_BT_BUF_ACL_TX_COUNT", "0")) >= 4,
        "att_tx_buffers_above_credits": int(config.get("CONFIG_BT_ATT_TX_COUNT", "0")) > 4,
        "data_length_251": config.get("CONFIG_BT_CTLR_DATA_LENGTH_MAX") == "251",
        "coded_phy_enabled": on("CONFIG_BT_CTLR_PHY_CODED") and on("CONFIG_BT_CTLR_PHY_2M"),
        "dynamic_tx_power_enabled": on("CONFIG_BT_CTLR_TX_PWR_DYNAMIC_CONTROL") and on("CONFIG_BT_HCI_VS"),
        "default_tx_power_0_dbm": config.get("CONFIG_BT_CTLR_TX_PWR_DBM") == "0",
        "conn_rssi_enabled": on("CONFIG_BT_CTLR_CONN_RSSI"),
        "no_auto_conn_param_request": not on("CONFIG_BT_GAP_AUTO_UPDATE_CONN_PARAMS"),
        "softdevice_controller": on("CONFIG_BT_LL_SOFTDEVICE"),
    }
    if args.variant == "link":
        checks.update({
            "no_usb_stack": not on("CONFIG_USB_DEVICE_STACK_NEXT") and not on("CONFIG_USB_DEVICE_STACK"),
            "no_serial_console_printk_log": not any(on(k) for k in (
                "CONFIG_SERIAL", "CONFIG_CONSOLE", "CONFIG_PRINTK", "CONFIG_LOG")),
            "session_ends_off_air": syms["link_disconnect"],
        })
    else:
        checks["usb_console"] = on("CONFIG_USB_DEVICE_STACK_NEXT") and on("CONFIG_PRINTK")

    report = {
        "schema": "week11-build-check/1",
        "variant": args.variant,
        "session": args.session,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "scope": "STATIC_BUILD_ONLY; S0c bytes, plan digest and the link ops need the dongle (link-usb VERIFY)",
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
    print(f"RESULT: {report['status']} ({args.variant}, session {args.session})")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
