"""Validate real capture and publish the compact Week 4 evidence set."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import shutil
import subprocess
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from check_week4_capture import MIXED_SEQUENCE, check
from generate_week4_inputs import ALL_SPLIT_MANIFEST, PACKAGE, R3, WEEK4_MANIFEST, load_handoff, sha256


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--dfu-receipt", type=Path, required=True)
    parser.add_argument("--memory-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("results/week4"))
    parser.add_argument("--bench-sample", type=int, default=0)
    parser.add_argument("--application-port", required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Evidence directory already contains files; retain it and choose a fresh directory")
    # All numerical/timing checks complete outside the official results first.
    staging_report = args.capture.parent / "analyzed-capture.json"
    validation = check(repo, args.capture.resolve(), staging_report.resolve(), args.bench_sample, mixed_order=True)
    if validation["mcu_validation"] != "PASS" or validation["mcu_timing"] != "PASS":
        raise ValueError("Cannot publish incomplete MCU evidence")
    if len(validation["stack_high_water"]) != len(validation["rows"]):
        raise ValueError("Every command must have an observed runtime stack sample")
    r3_manifest, split_manifest, graph, _, ids = load_handoff(repo)
    receipt = json.loads(args.dfu_receipt.read_text(encoding="utf-8-sig"))
    memory = json.loads(args.memory_report.read_text(encoding="utf-8-sig"))
    if receipt["exit_code"] != 0 or memory["status"] != "PASS":
        raise ValueError("DFU or footprint evidence is not PASS")
    package = Path(receipt["package"])
    elf = Path(memory["elf"])
    if sha256(package) != receipt["package_sha256"] or sha256(elf) != receipt["elf_sha256"] or sha256(elf) != memory["elf_sha256"]:
        raise ValueError("Final firmware artifact differs from the flashed/inspected image")
    firmware_sources = ['device/CMakeLists.txt', 'device/Kconfig', 'device/overlay-week4.conf',
                        'device/src/main_week4.c', 'device/src/week4_head.c', 'device/src/week4_head.h',
                        'device/src/week4_protocol.c', 'device/src/week4_protocol.h']
    for source in firmware_sources:
        if sha256(repo / source) != receipt["source_sha256"][source]:
            raise ValueError(f"Compiled firmware source changed after DFU: {source}")
    with zipfile.ZipFile(package) as archive:
        app = json.loads(archive.read("manifest.json"))["manifest"]["application"]
        application = archive.read(app["bin_file"])
        if hashlib.sha256(application).hexdigest() != receipt["application_sha256"]:
            raise ValueError("Flashed application payload identity mismatch")
    samples = []
    summaries = []
    for measurement in validation["timing"]:
        cycles = np.array(measurement["cycles"], dtype=np.uint32)
        if cycles.size != 100 or measurement["cpu_hz"] != 64000000:
            raise ValueError("Expected 100 measurements at stable 64 MHz for each split")
        times = cycles.astype(np.float64) / measurement["cpu_hz"] * 1000
        summaries.append({"split": measurement["split"], "sample_index": args.bench_sample,
                          "sample_id": ids[args.bench_sample], "n": 100, "warmup": measurement["warmup"],
                          "cpu_hz": measurement["cpu_hz"], "mean_ms": float(cycles.mean() / measurement["cpu_hz"] * 1000),
                          "std_ms": float(cycles.std(ddof=1) / measurement["cpu_hz"] * 1000),
                          "p95_ms": float(np.percentile(cycles, 95, method="linear") / measurement["cpu_hz"] * 1000),
                          "min_ms": float(times.min()), "max_ms": float(times.max())})
        samples.extend({"split": measurement["split"], "sample_index": args.bench_sample,
                        "sample_id": ids[args.bench_sample], "iteration": i, "cycles": int(cycle),
                        "cpu_hz": measurement["cpu_hz"], "time_ms": float(times[i])}
                       for i, cycle in enumerate(cycles))
    if [r["split"] for r in summaries] != list(range(11)) or len(samples) != 1100:
        raise ValueError("Timing matrix incomplete or duplicated")
    decreases = [{"from_split": a["split"], "to_split": b["split"], "delta_ms": b["mean_ms"] - a["mean_ms"]}
                 for a, b in zip(summaries, summaries[1:]) if b["mean_ms"] < a["mean_ms"]]
    if decreases:
        raise ValueError(f"Cumulative timing decreases require investigation before publication: {decreases}")
    output.mkdir(parents=True, exist_ok=True)
    # Preserve exact measured capture bytes when core.autocrlf is enabled.
    # This rule is local to Week 4 and does not affect accepted Week 2/3 logs.
    (output / ".gitattributes").write_text("logs/*.txt -text whitespace=cr-at-eol\n", encoding="ascii")
    capture = output / "logs/week4_capture.txt"
    capture.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.capture, capture)
    # Re-run the checker on the actual final file path, binding its byte hash.
    report_path = output / "week4_mcu_validation.json"
    validation = check(repo, capture, report_path, args.bench_sample, mixed_order=True)
    primary = [r for r in validation["rows"] if r["phase"] == "primary"]
    max_case = max(primary, key=lambda row: row["max_abs_error"])
    validation["primary_max_error_case"] = max_case
    validation["timing_statistics"] = {"std": "sample standard deviation, ddof=1 (n-1)",
                                       "p95": "NumPy percentile(method=linear), h=(n-1)*0.95",
                                       "cycle_to_ms": "cycles / 64000000 * 1000", "summary": summaries,
                                       "cumulative_mean_decreases": decreases}
    validate_time = datetime.now(timezone(timedelta(hours=7))).isoformat()
    validation["provenance"] = {
        "validated_at": validate_time, "timezone": "Asia/Saigon", "dfu_timestamp": receipt["timestamp"],
        "dfu_port": receipt["port"], "application_port": args.application_port,
        "dfu_command": receipt["command"], "dfu_exit_code": 0,
        "dfu_zip_sha256": receipt["package_sha256"], "application_sha256": receipt["application_sha256"],
        "elf_sha256": receipt["elf_sha256"], "week4_manifest_sha256": WEEK4_MANIFEST,
        "all_split_manifest_sha256": ALL_SPLIT_MANIFEST,
        "checkpoint_sha256": r3_manifest["checkpoint_sha256"],
        "graph_sha256": sha256(repo / R3 / "model_graph.json"),
        "parameters_header_sha256": sha256(repo / R3 / "firmware/head_parameters.h"),
        "input_npy_sha256": sha256(repo / PACKAGE / "golden/z_s0.npy"),
        "samples_csv_sha256": sha256(repo / PACKAGE / "samples.csv"),
        "golden_sha256": {str(s): sha256(repo / PACKAGE / f"golden/z_s{s}.npy") for s in range(11)},
        "compiled_source_sha256": {source: receipt["source_sha256"][source] for source in firmware_sources},
        "generated_header_sha256": {name: sha256(repo / "device/generated" / name) for name in ("week4_graph.h", "week4_inputs.h")},
        "python": platform.python_version(), "numpy": np.__version__, "ncs": "3.4.0", "zephyr": "4.4.0",
        "arm_gcc": "14.3.0", "board": "nrf52840dongle/nrf52840", "cpu_hz": 64000000,
        "source_base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "tool_sha256": {name: sha256(repo / "device/scripts" / name)
                        for name in ("collect_week4.ps1", "check_week4_capture.py", "analyze_week4_mcu.py")},
        "note": "Firmware was built before the evidence commit; exact source and binary hashes identify the flashed image."}
    report_path.write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    errors = [{"sample_index": r["sample_index"], "sample_id": r["sample_id"], "split": r["split"],
               "shape": "x".join(map(str, r["shape"])), "layout": "NCL" if r["split"] <= 8 else "NC",
               "max_abs_error": r["max_abs_error"], "status": r["status"]} for r in primary]
    write_csv(output / "week4_errors_20x11.csv", errors)
    write_csv(output / "week4_timing_1100.csv", samples)
    write_csv(output / "week4_timing_summary.csv", summaries)
    peaks = validation["stack_high_water"]
    memory["mcu_validation"] = "PASS"
    memory["mcu_timing"] = "PASS"
    memory["runtime_observation"] = {"main_stack": {"max_peak_bytes": max(r["peak_bytes"] for r in peaks),
                                                   "configured_bytes": 4096, "observations": len(peaks)},
                                     "fault_reset_buffer_errors_in_capture": 0,
                                     "other_thread_stack_high_water": "NOT_MEASURED",
                                     "overall_runtime_ram_peak": "NOT_MEASURED"}
    memory["scope"] = "STATIC_BUILD_AND_OBSERVED_MAIN_STACK"
    memory["limitations"] = ["Overall runtime RAM and USB/ISR/workqueue stack high-water were not measured.",
                             "No reset/fault/protocol/numerical errors observed in this capture; this is not a long-duration stress test."]
    (output / "week4_footprint.json").write_text(json.dumps(memory, indent=2) + "\n", encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
    x = np.arange(11)
    means = np.array([row["mean_ms"] for row in summaries])
    stds = np.array([row["std_ms"] for row in summaries])
    p95 = np.array([row["p95_ms"] for row in summaries])
    ax.errorbar(x, means, yerr=stds, fmt="o-", capsize=3, label="Mean ± sample std")
    ax.plot(x, p95, "s--", alpha=0.8, label="p95")
    ax.set(xticks=x, xlabel="Split s", ylabel="Device head time (ms)",
           title="nRF52840 — R3 FP32 head timing (20 warm-ups + 100 runs/split)")
    ax.grid(alpha=0.25)
    ax.legend()
    ax.annotate(f"s=0 identity: {means[0] * 1000:.3f} µs", (0, means[0]), xytext=(0.2, means[-1] * 0.16),
                arrowprops={"arrowstyle": "->", "color": "gray"})
    (output / "figures").mkdir(exist_ok=True)
    fig.savefig(output / "figures/week4_t_dev.png", dpi=180)
    plt.close(fig)
    import matplotlib as mpl
    lines = ["# SV1 tuần 4 — kiểm chứng MCU và timing R3", "",
             "**PASS trên nRF52840 Dongle PCA10059 thật, ngày 2026-10-02 (Asia/Saigon).**",
             f"220/220 tensor PASS, chuỗi đổi sample/split {len(MIXED_SEQUENCE)}/{len(MIXED_SEQUENCE)} PASS, 1100/1100 lượt timing hợp lệ.",
             f"Sai số lớn nhất `{max_case['max_abs_error']:.9g}` tại sample {max_case['sample_index']} `{max_case['sample_id']}`, s={max_case['split']}; tiêu chí strict `<1e-3`.",
             "Không thay golden, mô hình, precision hoặc tolerance. Tất cả phép tính là FP32, thứ tự C, NCL s0..8 và NC s9..10.",
             "", "## Hiện vật chính thức", "",
             "- `logs/week4_capture.txt`: toàn bộ CDC capture thật (220 RUN + 16 RUN đổi thứ tự + 11 BENCH, tổng 247 tensor).",
             "- `week4_mcu_validation.json`: checker, toàn bộ sai số, 1100 cycles, provenance và hashes.",
             "- `week4_errors_20x11.csv`: 220 ca chính thức.",
             "- `week4_timing_1100.csv`: cycles và thời gian từng lượt.",
             "- `week4_timing_summary.csv`: mean/std/p95/min/max từng split.",
             "- `figures/week4_t_dev.png`: đồ thị t_dev(s), số liệu nguyên bản.",
             "- `week4_footprint.json`: ELF/linker footprint và stack main đo thật.", "",
             "`.gitattributes` trong thư mục này giữ nguyên bytes capture khi Git checkout, tránh đổi hash do CRLF/LF.", "",
             "## Firmware, input và truy nguồn", "",
             f"ZIP DFU SHA256 `{receipt['package_sha256']}`; application binary SHA256 `{receipt['application_sha256']}`.",
             f"ELF SHA256 `{receipt['elf_sha256']}`.",
             f"R3 manifest `{WEEK4_MANIFEST}`; all-split manifest `{ALL_SPLIT_MANIFEST}`.",
             f"Input NPY SHA256 `{validation['provenance']['input_npy_sha256']}`; checkpoint SHA256 `{r3_manifest['checkpoint_sha256']}`.",
             "Các SHA256 source đã build, generated headers, weights/header, graph, sample CSV và 11 golden đều nằm trong JSON provenance.",
             "Firmware được build từ tree trước commit kết quả; source hashes và ELF/application/ZIP hashes xác định đúng image đã nạp.",
             f"USB DFU `{receipt['port']}` (VID_1915/PID_521F), ứng dụng `{args.application_port}` (VID_2FE3/PID_0004), nhận diện lại thay vì giả định cổng cố định.",
             f"NCS 3.4.0, Zephyr 4.4.0, ARM GCC 14.3.0, Python {platform.python_version()}, NumPy {np.__version__}, Matplotlib {mpl.__version__}.",
             "Không sửa SB1/SB2, bootloader, cấu hình phần cứng, artifacts R3/R2, venv hoặc bằng chứng tuần 2/3.", "",
             "## Mapping", "", "| s | Head endpoint | Shape/layout |", "|---|---|---|"]
    for split in split_manifest["splits"]:
        lines.append(f"| {split['split_id']} | {split['head_endpoint']} | {'x'.join(map(str, split['shape_N1']))} {split['layout']} |")
    lines.extend(["", "Head luôn chạy từ input gốc; không tái sử dụng activation của lệnh trước.",
                  "s0 identity khớp bitwise input; s2 được đối chiếu trực tiếp với P2 của capture MCU tuần 3 đã nghiệm thu; s10 là logits 5 lớp N/S/V/F/Q.",
                  f"Chuỗi bổ sung, đúng thứ tự: `{MIXED_SEQUENCE}`.", "", "## Phương pháp timing", "",
                  f"Một sample cố định: {args.bench_sample}, `{ids[args.bench_sample]}`. Mỗi split 20 warm-up rồi 100 lượt đo.",
                  "DWT CYCCNT phần cứng, Cortex-M4 64 MHz; `time_ms = cycles / 64000000 * 1000`.",
                  "SystemCoreClock trong Nordic MDK là 64000000 và cả 11 TIMING frame đều khai báo cùng tần số này.",
                  "Không dùng CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC=32768: đây là RTC/tick Zephyr, không phải DWT CPU clock.",
                  "IRQ khóa trong từng head call; GPIO, USB, log, chờ lệnh và so sánh golden nằm ngoài khoảng đo.",
                  "Sau toàn bộ batch mới in cycles/tensor. Kết quả head được lưu và xuất, không bị compiler bỏ; `-ffp-contract=off`.",
                  "s0 được đo thực tế, không gán 0 hoặc trừ baseline. Counts bao gồm dispatch/shape bookkeeping của head API.",
                  "Std là sample standard deviation ddof=1 (n−1); p95 là NumPy linear interpolation h=(n−1)*0.95.",
                  "Thứ tự số đo và split được giữ nguyên; không thêm delay, sắp xếp hay sửa số liệu để ép tăng.",
                  "Mean tích lũy tăng theo s; không phát hiện điểm giảm. Payload không đơn điệu và không dùng để suy thời gian.", "",
                  "| s | n | mean (ms) | std (ms) | p95 (ms) |", "|---|---:|---:|---:|---:|"])
    for row in summaries:
        lines.append(f"| {row['split']} | 100 | {row['mean_ms']:.9f} | {row['std_ms']:.9f} | {row['p95_ms']:.9f} |")
    flash, ram = memory["regions"]["FLASH"], memory["regions"]["RAM"]
    lines.extend(["", "## Bộ nhớ và giới hạn chứng cứ", "",
                  f"Flash `{flash['used_bytes']}/{flash['limit_bytes']} B`, còn `{flash['remaining_bytes']} B` trong vùng DFU app `[0x1000,0xe0000)`.",
                  f"RAM tĩnh `{ram['used_bytes']}/{ram['limit_bytes']} B`, còn `{ram['remaining_bytes']} B` theo linker.",
                  "Weights const 438612 B + inputs 28800 B trong Flash. Activation A/B tổng 46080 B, timing array 400 B trong RAM.",
                  f"Stack main khả dụng 4096 B (ELF cấp 4224 B gồm guard/alignment), high-water đo được `{max(r['peak_bytes'] for r in peaks)}/4096 B` qua {len(peaks)} lệnh.",
                  "Stack UDC/USBD/workqueue/ISR/idle đã cấp nằm trong RAM tĩnh. High-water các stack này và peak RAM tổng runtime chưa đo.",
                  "Không quan sát reset, fault, dữ liệu không hữu hạn hoặc lỗi buffer/giao thức trong phiên thu; không thay cho stress test dài hạn.",
                  "Build hồi quy tuần 3 đã PASS vì CMake/Kconfig dùng chung; kernel/entry point/bằng chứng tuần 3 không sửa.", "",
                  "## Lệnh tái chạy", "",
                  "Dùng cổng thực tế sau khi nhận diện, không sao chép COM6/COM7 khi cổng đã thay đổi. Ghi mỗi phiên mới vào thư mục work riêng.", "",
                  "```powershell",
                  "powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\device\\scripts\\build_week4_head.ps1",
                  "# Nạp ZIP đã đối chiếu: nhấn RESET/SW2 để vào bootloader trước.",
                  "powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\device\\scripts\\flash_week4_head.ps1 -Port COMx",
                  "powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\device\\scripts\\collect_week4.ps1 -Port COMy -Output D:/HUST/SV3_week4_R3/mcu-week4-work/new-run/week4_capture.txt -Report D:/HUST/SV3_week4_R3/mcu-week4-work/new-run/validation.json -BenchSample 0",
                  "& ml/.venv/Scripts/python.exe -B device/scripts/check_week4_capture.py --repo-root . --capture results/week4/logs/week4_capture.txt --report D:/HUST/SV3_week4_R3/mcu-week4-work/recheck.json --bench-sample 0 --mixed-order",
                  "```", "", "Collector chạy checker sau 220 tensor, rồi sau chuỗi đổi sample/split; chỉ đo BENCH sau cả hai PASS.",
                  "Logs prepare/thử nghiệm/DFU và các checkpoint giữ ngoài repo tại `D:/HUST/SV3_week4_R3/mcu-week4-work`."])
    (output / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"MCU: 220/220 PASS + mixed {len(MIXED_SEQUENCE)}/{len(MIXED_SEQUENCE)}; max={max_case['max_abs_error']:.9g} n={max_case['sample_index']} s={max_case['split']}")
    for row in summaries:
        print(f"s={row['split']} n=100 mean_ms={row['mean_ms']:.9f} std_ms={row['std_ms']:.9f} p95_ms={row['p95_ms']:.9f}")
    print(f"EVIDENCE: {output}; main_stack_peak={max(r['peak_bytes'] for r in peaks)}/4096 B")


if __name__ == "__main__":
    main()
