"""Write the external steps 1-3 summary from completed host/build evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path

from generate_week4_inputs import load_handoff, sha256


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--report-dir", type=Path, default=Path("D:/HUST/SV3_week4_R3/firmware-build"))
    args = parser.parse_args()
    repo, output = args.repo_root.resolve(), args.report_dir.resolve()
    load_handoff(repo)
    host = json.loads((output / "week4_host_validation.json").read_text(encoding="utf-8"))
    memory = json.loads((output / "week4_memory.json").read_text(encoding="utf-8"))
    if host["status"] != "PASS" or memory["status"] != "PASS":
        raise ValueError("Cannot mark preparation ready without host and memory PASS")
    for path, expected in host["source_sha256"].items():
        if sha256(repo / path) != expected:
            raise ValueError(f"Host verification became stale: {path}")
    if sha256(Path(memory["elf"])) != memory["elf_sha256"]:
        raise ValueError("Inspected ELF changed")
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=repo, text=True).strip()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    if branch != "dev/device-sv1":
        raise ValueError("Unexpected branch")
    subprocess.run(["git", "diff", "--check"], cwd=repo, check=True)
    if subprocess.check_output(["git", "diff", "--name-only", "--", "ml", "results", "contracts"], cwd=repo, text=True).strip():
        raise ValueError("Protected ML/results/contracts were modified")
    if (repo / "results/week4").exists():
        raise ValueError("Official MCU results/week4 must not be created during preparation")
    status = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo, text=True)
    changed = [line[3:] for line in status.splitlines()]
    if any(not name.startswith("device/") for name in changed):
        raise ValueError("Changes outside device scope")
    original_zip = repo / "device/artifacts/adaptive_split_week3_fp32_v2.zip"
    accepted_week3_zip = "1862c97ad223573c4492d0a3c0de2d46b225f4c4573f1ce71c67aa4d65103f02"
    if sha256(original_zip) != accepted_week3_zip:
        raise ValueError("Accepted Week 3 DFU ZIP changed")
    builds = {}
    for name in ("week4", "week3-regression"):
        record = (output / f"build-{name}.log.command.txt").read_text(encoding="utf-8-sig")
        if "EXIT_CODE: 0" not in record:
            raise ValueError(f"Build did not pass: {name}")
        log = (output / f"build-{name}.log").read_text(encoding="utf-8-sig")
        if re.search(r"warning:|error:", log, flags=re.I):
            raise ValueError(f"Build diagnostics need review: {name}")
        builds[name] = {"command": record.splitlines()[0].removeprefix("COMMAND: "), "exit_code": 0}
    package = repo / "device/artifacts/adaptive_split_week4_r3_fp32.zip"
    package_info = None
    if package.exists():
        with zipfile.ZipFile(package) as archive:
            if archive.testzip() is not None:
                raise ValueError("Corrupted DFU ZIP")
            manifest = json.loads(archive.read("manifest.json"))["manifest"]
            app = manifest["application"]
            binary = archive.read(app["bin_file"])
            if binary != (repo / "device/build-week4/zephyr/zephyr.bin").read_bytes():
                raise ValueError("DFU payload differs from inspected build")
            if len(binary) != memory["regions"]["FLASH"]["used_bytes"]:
                raise ValueError("DFU application length differs from linker usage")
            package_info = {"path": str(package), "sha256": sha256(package), "size_bytes": package.stat().st_size,
                            "application_bytes": len(binary), "application_sha256": hashlib.sha256(binary).hexdigest()}
    sources = {path: sha256(repo / path) for path in changed if (repo / path).is_file()}
    result = {"scope": "SV1_WEEK4_PREPARATION_STEPS_1_TO_3", "status": "PASS_READY_FOR_DFU",
              "branch": branch, "head": commit, "builds": builds, "host_status": "PASS", "memory_status": "PASS",
              "mcu_validation": "PENDING", "mcu_timing": "PENDING", "runtime_memory": "PENDING",
              "flash_or_serial_access_performed": False, "protected_tracked_paths_unchanged": True,
              "accepted_week3_zip_sha256": accepted_week3_zip, "dfu": package_info,
              "changed_files": changed, "source_sha256": sources, "known_blockers": [], "skips": [],
              "resolved_issues": ["ML venv has no pyserial; collector uses existing .NET SerialPort, no installation."]}
    (output / "preparation_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    flash, ram = memory["regions"]["FLASH"], memory["regions"]["RAM"]
    maximum = max(host["max_abs_error_by_split"].values())
    lines = ["# SV1 Week 4 R3 — steps 1–3 complete", "", "Prepared on 2026-10-02 (Asia/Saigon).",
             f"Branch `{branch}`, HEAD `{commit}`; initial working tree was clean. No reset, branch creation, commit, PR or merge.",
             "", "**Ready for Nordic USB DFU. MCU validation, timing and runtime stack/USB memory remain PENDING.**",
             "No flash, COM open, device commands or dongle measurements were performed.", "",
             "## Handoff and memory design", "",
             f"R3 manifest `{host['week4_manifest_sha256']}`; all-split manifest `{host['all_split_manifest_sha256']}`.",
             "Authenticated inventory, pinned ML source hashes, graph, 20 weights, ordered IDs and golden tensors were read without modification.",
             "Complete operations/weights/shapes/buffer lifetime mapping: [split_mapping.md](split_mapping.md).",
             "s=0 identity input; s=2 original Week 3 P2; s=10 all 25 ops to 5 logits, N/S/V/F/Q.",
             "FP32, original sample order, NCL s0..8, NC s9..10, C order and strict `<1e-3` retained.",
             "Two 23040-byte static buffers alternate Conv/Pool/Linear; ReLU in place, Flatten/eval Dropout identity.",
             "Output dies at next head call (s0 borrows input). Every call restarts at the immutable original sample.",
             "Weights 438612 bytes and all 20 inputs 28800 bytes in read-only Flash; timing array 400 static RAM bytes.",
             "", "## Host and tools validation", "",
             f"Actual firmware C: 220/220 PASS, reverse-order 220/220 PASS; overall max error `{maximum:.9g}`.",
             "Week 3 P2 bitwise compatibility 20/20; finite values/shapes/input immutability/API invalid calls checked.",
             f"Protocol tests: {host['valid_command_checks']} valid commands, {host['invalid_command_checks']} invalid commands.",
             "Offline collector chunk/continuation/DONE/error/overflow tests PASS; no SerialPort was instantiated by those tests.",
             "PowerShell/Python syntax and `git diff --check` PASS; no SKIP and no C compiler warnings/errors.",
             "ML venv has no pyserial: resolved by .NET SerialPort collector; no dependencies installed or persistent system/NCS configuration changed.",
             "Host report: [week4_host_validation.json](week4_host_validation.json). No full ML gate rerun.",
             "", "## Build and partition inspection", "",
             "Wrapper: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\device\\scripts\\build_week4_head.ps1 -ReuseHostValidation -PackageDfu` (exit 0).",
             "NCS v3.4.0 / Zephyr 4.4.0 / ARM GCC 14.3.0; board `nrf52840dongle/nrf52840`; --no-sysbuild.",
             "Week 4 selection: CONFIG_APP_WEEK4_HEAD=y / overlay-week4.conf; original Week 3 selection is unchanged.",
             "`-ffp-contract=off` on actual target; Cortex M4 hardware FP32 enabled only for Week 4.",
             "Direct Nordic USB DFU app `[0x1000,0xe0000)`, enforced by FLASH_LOAD_SIZE=0xdf000 in final linker.",
             "The board's MCUboot slots are not active (USE_DT_CODE_PARTITION=n); Nordic bootloader and settings stay outside the app range.", "",
             "| Region | Used (bytes) | Linker limit (bytes) | Remaining (bytes) |", "|---|---:|---:|---:|",
             f"| Flash | {flash['used_bytes']} | {flash['limit_bytes']} | {flash['remaining_bytes']} |",
             f"| Static RAM | {ram['used_bytes']} | {ram['limit_bytes']} | {ram['remaining_bytes']} |", "",
             "Main usable stack 4096 bytes; ELF reserved main stack 4224 bytes including guard/alignment/FPU overhead.",
             "USB usable stacks: UDC 512 and USBD 1024; system workqueue 1024; ISR 2048; idle 320 bytes.",
             "ELF allocation: UDC 640, USBD 1152, workqueue 1152, ISR 2176, idle 512 bytes; heap pool 0.",
             "RAM usage includes all statically allocated stacks, buffers and Zephyr/USB data; remaining RAM is not a runtime high-water measurement.",
             "All 20 const weight arrays located in app Flash. HEX payload 523424 bytes; every data record within app, no UICR/bootloader records.",
             f"HEX end exclusive `{memory['hex_end_exclusive']:#x}`; ELF SHA256 `{memory['elf_sha256']}`.",
             "Week 3 regression build exit 0, Flash 84072 B / existing linker 1044480 B, RAM 64248 B / 262144 B.",
             "Regression output stays in build-week3-regression; accepted build-week3, Week 3 ZIP/results and ML packages preserved.",
             f"Accepted Week 3 ZIP SHA256 remains `{accepted_week3_zip}`.",
             "Detailed ELF symbols/sections/stacks: [week4_memory.json](week4_memory.json).", ""]
    for name, build in builds.items():
        lines.extend([f"{name} build (exit 0):", "", "```text", build["command"], "```", ""])
    lines.extend(["## Files and artifacts", ""])
    lines.extend(f"- `{path}`" for path in changed)
    lines.extend(["", f"ELF: `{memory['elf']}`", f"Map: `{memory['map']}`"])
    if package_info:
        lines.extend([f"DFU ZIP: `{package_info['path']}`", f"DFU ZIP SHA256: `{package_info['sha256']}`",
                      "ZIP CRC/inventory checked; application binary byte-identical to inspected build."])
    lines.extend(["", "## Next stage when dongle is available", "",
                  "1. Enter the existing Nordic USB DFU bootloader; select the Week 4 ZIP and run the separate DFU command documented in device/week4_fp32_guide.md.",
                  "2. Discover the application CDC port and run collect_week4.ps1 -Port COMy -BenchSample 0.",
                  "3. Collector checks 20 x 11 actual tensors, then 20 warm-ups + 100 measured calls for each split on sample 0. All timing output occurs after the batch; s0 uses raw measured cycles.",
                  "4. Inspect real errors, cycles and stack high-water. Only then write acceptance under results/week4 and change MCU statuses from PENDING.",
                  "", "No known build blocker. Collector/USB/timing behavior still requires real-device validation."])
    (output / "steps_1_to_3_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"PREPARATION: PASS_READY_FOR_DFU; MCU=PENDING; report={output / 'steps_1_to_3_report.md'}")


if __name__ == "__main__":
    main()
