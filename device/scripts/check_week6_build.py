#!/usr/bin/env python3
"""Offline checks of a week 6 build: Flash end before NVS, partition map and ATT MTU.

Reads only build outputs (zephyr.elf, zephyr.bin, .config, zephyr.dts); no device access.
Exit 0 = PASS, 1 = FAIL. Writes a JSON report to a new path.
"""
import argparse
import hashlib
import json
import pathlib
import re
import struct
import sys

APP_START = 0x1000          # after Nordic MBR (board default FLASH_LOAD_OFFSET)
NVS_START = 0xDC000         # storage_partition, contracts/i2_nonce_provisioning_v1.md §2
NVS_SIZE = 0x4000
BIN_LIMIT = NVS_START - APP_START  # 897024 B
FLASH_SIZE = 0x100000
L2CAP_HDR = 4
FRAGMENT_OVERHEAD = 3 + 8   # ATT write/notify header + binding fragment header
EXPECTED_MTU = {"default": 247, "mtu23": 23}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def elf_load_end(path):
    """Highest LMA end of PT_LOAD segments carrying file bytes, plus the segment list."""
    data = path.read_bytes()
    if data[:4] != b"\x7fELF" or data[4] != 1 or data[5] != 1:
        raise ValueError("expected little-endian ELF32")
    phoff, = struct.unpack_from("<I", data, 28)
    phentsize, phnum = struct.unpack_from("<HH", data, 42)
    segments = []
    for i in range(phnum):
        p_type, _, _, p_paddr, p_filesz, p_memsz, _, _ = struct.unpack_from(
            "<8I", data, phoff + i * phentsize)
        if p_type == 1 and p_filesz:
            segments.append({"lma": p_paddr, "filesz": p_filesz, "memsz": p_memsz})
    flash = [s for s in segments if s["lma"] < FLASH_SIZE]
    return max(s["lma"] + s["filesz"] for s in flash), min(s["lma"] for s in flash), segments


def ram_static_bytes(path):
    """Sum of allocated ELF sections placed in nRF52840 RAM (0x20000000, 256 KiB)."""
    data = path.read_bytes()
    shoff, = struct.unpack_from("<I", data, 32)
    shentsize, shnum = struct.unpack_from("<HH", data, 46)
    total = 0
    for i in range(shnum):
        _, sh_type, flags, addr, _, size = struct.unpack_from("<6I", data, shoff + i * shentsize)
        if flags & 0x2 and 0x20000000 <= addr < 0x20040000 and sh_type != 0:
            total += size
    return total


def read_config(path):
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^(CONFIG_\w+)=(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2).strip('"')
    return values


def storage_partition(dts_text):
    match = re.search(r"storage_partition:\s*partition@([0-9a-fA-F]+)\s*\{[^}]*?reg\s*=\s*<\s*"
                      r"(0x[0-9a-fA-F]+|\d+)\s+(0x[0-9a-fA-F]+|\d+)\s*>", dts_text, re.S)
    if not match:
        return None
    return int(match.group(2), 0), int(match.group(3), 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=pathlib.Path)
    parser.add_argument("--variant", required=True, choices=sorted(EXPECTED_MTU))
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    if args.output.exists():
        sys.exit(f"refusing to overwrite {args.output}")

    zdir = args.build / "zephyr"
    elf, binf = zdir / "zephyr.elf", zdir / "zephyr.bin"
    config = read_config(zdir / ".config")
    load_end, load_start, segments = elf_load_end(elf)
    bin_size = binf.stat().st_size
    partition = storage_partition((zdir / "zephyr.dts").read_text(encoding="utf-8"))
    l2cap_tx = int(config.get("CONFIG_BT_L2CAP_TX_MTU", "0"))
    acl_rx = int(config.get("CONFIG_BT_BUF_ACL_RX_SIZE", "0"))
    att_mtu = min(acl_rx - L2CAP_HDR, l2cap_tx)

    checks = {
        "flash_load_offset_0x1000": int(config.get("CONFIG_FLASH_LOAD_OFFSET", "-1"), 0) == APP_START,
        "flash_load_size_limits_to_nvs": int(config.get("CONFIG_FLASH_LOAD_SIZE", "0"), 0) == BIN_LIMIT,
        "elf_starts_at_app_start": load_start == APP_START,
        "elf_ends_before_nvs": load_end <= NVS_START,
        "bin_fits_before_nvs": bin_size <= BIN_LIMIT,
        "bin_matches_elf_span": bin_size == load_end - load_start,
        "storage_partition_0xdc000_16k": partition == (NVS_START, NVS_SIZE),
        "bt_enabled": config.get("CONFIG_BT") == "y",
        "single_connection": config.get("CONFIG_BT_MAX_CONN") == "1",
        "device_name": config.get("CONFIG_BT_DEVICE_NAME") == "ASI-SV1",
        "tx_credits_4_available": int(config.get("CONFIG_BT_BUF_ACL_TX_COUNT", "0")) >= 4,
        "configured_att_mtu": att_mtu == EXPECTED_MTU[args.variant],
        "att_tx_buffers_above_credits": int(config.get("CONFIG_BT_ATT_TX_COUNT", "0")) > 4,
        "nvs_enabled_with_data_crc": config.get("CONFIG_NVS") == "y" and config.get("CONFIG_NVS_DATA_CRC") == "y",
        "nvs_never_auto_formats": "CONFIG_NVS_INIT_BAD_MEMORY_REGION" not in config,
        "flash_writes_radio_synced": config.get("CONFIG_SOC_FLASH_NRF_RADIO_SYNC_MPSL") == "y",
        "csprng_for_request_id": config.get("CONFIG_CSPRNG_ENABLED") == "y",
        "build_id_in_image": args.build_id.encode() in binf.read_bytes(),
    }
    report = {
        "schema": "week6-build-check/1",
        "variant": args.variant,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "scope": "STATIC_BUILD_ONLY; runtime MTU/RAM/stack need the dongle",
        "checks": checks,
        "elf_sha256": sha256(elf),
        "bin_sha256": sha256(binf),
        "bin_bytes": bin_size,
        "bin_limit_bytes": BIN_LIMIT,
        "headroom_bytes": BIN_LIMIT - bin_size,
        "image_end_hex": hex(load_end),
        "storage_partition": [hex(v) for v in partition] if partition else None,
        "load_segments": segments,
        "configured_att_mtu": att_mtu,
        "build_id": args.build_id,
        "ram_static_bytes": ram_static_bytes(elf),
        "frame_bytes_per_fragment": att_mtu - FRAGMENT_OVERHEAD,
        "kconfig": {k: config.get(k) for k in (
            "CONFIG_FLASH_LOAD_OFFSET", "CONFIG_FLASH_LOAD_SIZE", "CONFIG_BT_L2CAP_TX_MTU",
            "CONFIG_BT_BUF_ACL_RX_SIZE", "CONFIG_BT_BUF_ACL_TX_SIZE", "CONFIG_BT_BUF_ACL_TX_COUNT",
            "CONFIG_BT_CTLR_DATA_LENGTH_MAX", "CONFIG_BT_LL_SOFTDEVICE", "CONFIG_BT_ATT_TX_COUNT",
            "CONFIG_BT_CONN_TX_MAX", "CONFIG_MAIN_STACK_SIZE", "CONFIG_NVS", "CONFIG_NVS_DATA_CRC",
            "CONFIG_SOC_FLASH_NRF_RADIO_SYNC_MPSL", "CONFIG_CSPRNG_ENABLED")},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'} {name}")
    print(f"image end {hex(load_end)} / limit {hex(NVS_START)}; bin {bin_size} B, headroom "
          f"{BIN_LIMIT - bin_size} B; RAM static {report['ram_static_bytes']} B; ATT MTU {att_mtu} ({att_mtu - FRAGMENT_OVERHEAD} B/fragment)")
    print(f"RESULT: {report['status']} ({args.variant})")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
