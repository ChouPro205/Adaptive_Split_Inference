"""Audit actual ELF, Intel HEX and linker limits, without accessing a device."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def number(value: str) -> int:
    return int(value, 0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--report-dir", type=Path, default=Path("D:/HUST/SV3_week4_R4/sv1-integration/new-build"))
    parser.add_argument("--toolchain-root", type=Path, default=Path("D:/ncs/toolchains/dcbdc366a1"))
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = args.report_dir.resolve()
    zephyr = (args.build_dir.resolve() if args.build_dir else repo / "device/build-week4") / "zephyr"
    elf = zephyr / "zephyr.elf"
    tool_bin = args.toolchain_root / "opt/zephyr-sdk/gnu/arm-zephyr-eabi/bin"
    config = dict(re.findall(r'^(CONFIG_\w+)=(.*)$', (zephyr / ".config").read_text(), flags=re.M))
    flash_origin = number(config["CONFIG_FLASH_BASE_ADDRESS"]) + number(config["CONFIG_FLASH_LOAD_OFFSET"])
    flash_limit = number(config["CONFIG_FLASH_LOAD_SIZE"])
    if (flash_origin, flash_limit) != (0x1000, 0xDF000):
        raise ValueError("Unexpected Nordic USB DFU application limits")
    if config.get("CONFIG_USE_DT_CODE_PARTITION") == "y" or config.get("CONFIG_BOOTLOADER_MCUBOOT") == "y":
        raise ValueError("Unexpected MCUboot/DT code partition selection")
    linker = (zephyr / "linker.cmd").read_text()
    if not re.search(r"FLASH \(rx\).*LENGTH = .*0xdf000", linker, flags=re.I):
        raise ValueError("Final linker does not enforce application limit")
    log = (output / "build-week4.log").read_text(encoding="utf-8-sig")
    regions = {}
    for match in re.finditer(r"^\s*(FLASH|RAM):\s+([\d.]+)\s+(B|KB|MB)\s+([\d.]+)\s+(B|KB|MB)", log, flags=re.M):
        name, used, used_unit, limit, limit_unit = match.groups()
        unit = {"B": 1, "KB": 1024, "MB": 1024 * 1024}
        regions[name] = {"used_bytes": int(float(used) * unit[used_unit]), "limit_bytes": int(float(limit) * unit[limit_unit])}
        regions[name]["remaining_bytes"] = regions[name]["limit_bytes"] - regions[name]["used_bytes"]
    if set(regions) != {"FLASH", "RAM"} or regions["FLASH"]["limit_bytes"] != flash_limit:
        raise ValueError("Missing/mismatched authoritative linker memory usage")
    size_output = subprocess.check_output([str(tool_bin / "arm-zephyr-eabi-size.exe"), "-A", str(elf)], text=True)
    nm_output = subprocess.check_output([str(tool_bin / "arm-zephyr-eabi-nm.exe"), "-S", "--size-sort", str(elf)], text=True)
    objdump_output = subprocess.check_output([str(tool_bin / "arm-zephyr-eabi-objdump.exe"), "-h", str(elf)], text=True)
    symbols = {}
    for line in nm_output.splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+(\w)\s+(\S+)", line)
        if match:
            address, size, kind, name = match.groups()
            symbols[name] = {"address": int(address, 16), "bytes": int(size, 16), "type": kind}
    weights = {k: v for k, v in symbols.items() if k.startswith("sv3_")}
    if len(weights) != 20 or sum(s["bytes"] for s in weights.values()) != 438612:
        raise ValueError("ELF does not contain exactly all 20 FP32 weight arrays")
    if any(s["type"].lower() != "r" or not flash_origin <= s["address"] < 0xE0000 for s in weights.values()):
        raise ValueError("Weights must reside in read-only application Flash")
    for name in ("activation_a", "activation_b"):
        if symbols[name]["bytes"] != 23040 or symbols[name]["type"].lower() != "b":
            raise ValueError("Activation buffer allocation mismatch")
    if symbols["week4_inputs"]["bytes"] != 28800 or symbols["week4_inputs"]["type"].lower() != "r":
        raise ValueError("Inputs must reside in Flash")
    stack_symbols = {k: v for k, v in symbols.items() if "stack" in k and v["type"].lower() == "b"}
    # Check every Intel HEX data record, including potential UICR writes.
    base = 0
    ranges = []
    for line in (zephyr / "zephyr.hex").read_text().splitlines():
        record = bytes.fromhex(line.removeprefix(":"))
        if sum(record) % 256 or len(record) != record[0] + 5:
            raise ValueError("Invalid Intel HEX checksum/length")
        count, low, kind = record[0], int.from_bytes(record[1:3], "big"), record[3]
        data = record[4:4 + count]
        if kind == 4:
            base = int.from_bytes(data, "big") << 16
        elif kind == 2:
            base = int.from_bytes(data, "big") << 4
        elif kind == 0 and count:
            start, end = base + low, base + low + count
            if start < flash_origin or end > 0xE0000:
                raise ValueError(f"HEX writes outside application range: {start:#x}..{end:#x}")
            ranges.append((start, end))
    if not ranges:
        raise ValueError("Empty HEX")
    if any(region["remaining_bytes"] < 0 for region in regions.values()):
        raise ValueError("Memory region overflow")
    interesting = {k: v for k, v in symbols.items() if k in ("activation_a", "activation_b", "week4_inputs", "measured_cycles")}
    report = {"status": "PASS", "scope": "STATIC_BUILD_ONLY", "mcu_validation": "PENDING", "mcu_timing": "PENDING",
              "elf": str(elf), "elf_sha256": hashlib.sha256(elf.read_bytes()).hexdigest(),
              "map": str(zephyr / "zephyr.map"), "linker": str(zephyr / "linker.cmd"),
              "regions": regions, "flash_origin": flash_origin, "flash_end_exclusive": 0xE0000,
              "hex_first_address": min(r[0] for r in ranges), "hex_end_exclusive": max(r[1] for r in ranges),
              "hex_payload_bytes": sum(end - start for start, end in ranges),
              "weight_arrays": weights, "buffer_symbols": interesting, "stack_symbols": stack_symbols,
              "configured_stacks": {k: number(v) for k, v in config.items() if k.endswith("STACK_SIZE")},
              "fpu": config.get("CONFIG_FPU"), "heap_pool_bytes": number(config["CONFIG_HEAP_MEM_POOL_SIZE"]),
              "elf_section_sizes": size_output,
              "limitations": ["Linker usage includes allocated stacks and Zephyr/USB data, not measured runtime peaks.",
                              "Main/USB stack high-water, timing, USB behavior and target numerical accuracy remain PENDING.",
                              "Board's MCUboot slots are not active for this direct Nordic USB DFU configuration."]}
    output.mkdir(parents=True, exist_ok=True)
    (output / "week4_memory.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, content in (("elf-size.txt", size_output), ("elf-symbols.txt", nm_output), ("elf-sections.txt", objdump_output)):
        (output / name).write_text(content, encoding="utf-8")
    for name, region in regions.items():
        print(f"{name}: {region['used_bytes']}/{region['limit_bytes']} B; remaining={region['remaining_bytes']} B")
    print(f"FLASH bounds: [{flash_origin:#x}, {0xE0000:#x}); HEX end={report['hex_end_exclusive']:#x}")
    print("MEMORY: PASS; 20 const weight arrays = 438612 B; activation buffers = 46080 B; runtime=PENDING")


if __name__ == "__main__":
    main()
