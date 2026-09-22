#!/usr/bin/env python3
"""Analyze a Week 2 PPK2 idle-current CSV without loading it all into RAM."""

from __future__ import annotations

import argparse
import csv
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Iterator, Sequence

os.environ.setdefault(
    "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib-week2-idle")
)
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    REPO_ROOT / "results/week2/raw/2026-09-22_idle_vbus5v_60s.csv"
)
DEFAULT_SUMMARY = REPO_ROOT / "results/week2/summary/week2_idle_summary.csv"
DEFAULT_HISTOGRAM = (
    REPO_ROOT / "results/week2/figures/idle_current_histogram.png"
)

TIME_TO_SECONDS = {
    "s": 1.0,
    "sec": 1.0,
    "second": 1.0,
    "seconds": 1.0,
    "ms": 1e-3,
    "millisecond": 1e-3,
    "milliseconds": 1e-3,
    "us": 1e-6,
    "microsecond": 1e-6,
    "microseconds": 1e-6,
    "ns": 1e-9,
    "nanosecond": 1e-9,
    "nanoseconds": 1e-9,
}
CURRENT_TO_MICROAMPS = {
    "a": 1e6,
    "amp": 1e6,
    "amps": 1e6,
    "ampere": 1e6,
    "amperes": 1e6,
    "ma": 1e3,
    "milliamp": 1e3,
    "milliamps": 1e3,
    "milliampere": 1e3,
    "milliamperes": 1e3,
    "ua": 1.0,
    "microamp": 1.0,
    "microamps": 1.0,
    "microampere": 1.0,
    "microamperes": 1.0,
    "na": 1e-3,
    "nanoamp": 1e-3,
    "nanoamps": 1e-3,
    "nanoampere": 1e-3,
    "nanoamperes": 1e-3,
}


def normalize_unit(unit: str) -> str:
    """Normalize ASCII/Unicode micro signs and unit punctuation."""

    return re.sub(r"[^a-z]", "", unit.replace("µ", "u").replace("μ", "u").lower())


def split_header(header: str) -> tuple[str, str | None]:
    """Return a normalized signal name and an optional unit from a header."""

    stripped = header.strip()
    match = re.match(r"^(.*?)\s*[\[(]\s*([^)\]]+)\s*[\])]\s*$", stripped)
    if match:
        name, unit = match.groups()
        return re.sub(r"[^a-z0-9]", "", name.lower()), unit.strip()

    normalized = stripped.replace("µ", "u").replace("μ", "u")
    suffix_match = re.match(
        r"^(.*?)[_\s-]+(milliseconds?|millisecond|ms|microseconds?|us|"
        r"nanoseconds?|ns|seconds?|sec|s|milliamperes?|milliamps?|ma|"
        r"microamperes?|microamps?|ua|nanoamperes?|nanoamps?|na|"
        r"amperes?|amps?|a)$",
        normalized,
        flags=re.IGNORECASE,
    )
    if suffix_match:
        name, unit = suffix_match.groups()
        return re.sub(r"[^a-z0-9]", "", name.lower()), unit

    return re.sub(r"[^a-z0-9]", "", normalized.lower()), None


def detect_signal_column(
    headers: Sequence[str], signal: str
) -> tuple[int, str, float]:
    """Detect the time/current column and return index, unit and output scale."""

    if signal == "time":
        names = {"time", "timestamp", "elapsedtime", "sampletime"}
        unit_scales = TIME_TO_SECONDS
    elif signal == "current":
        names = {"current", "currentdraw", "i", "amperage"}
        unit_scales = CURRENT_TO_MICROAMPS
    else:
        raise ValueError(f"Unsupported signal type: {signal}")

    candidates: list[tuple[int, str, float]] = []
    for index, header in enumerate(headers):
        name, raw_unit = split_header(header)
        if name not in names:
            continue
        if raw_unit is None:
            raise ValueError(
                f"Detected {signal} column {header!r}, but its unit is missing."
            )
        unit = normalize_unit(raw_unit)
        if unit not in unit_scales:
            raise ValueError(
                f"Unsupported {signal} unit {raw_unit!r} in column {header!r}."
            )
        candidates.append((index, raw_unit, unit_scales[unit]))

    if len(candidates) != 1:
        raise ValueError(
            f"Expected exactly one {signal} column, found {len(candidates)}: "
            f"{list(headers)!r}"
        )
    return candidates[0]


def detect_logic_columns(headers: Sequence[str]) -> dict[str, int]:
    """Find exact D0-D3 logic-channel headers when present."""

    detected: dict[str, int] = {}
    for index, header in enumerate(headers):
        normalized = re.sub(r"[^a-z0-9]", "", header.lower())
        if normalized in {"d0", "d1", "d2", "d3"}:
            detected[normalized.upper()] = index
    return dict(sorted(detected.items()))


def iter_chunks(
    reader: Iterator[list[str]], chunk_size: int
) -> Iterator[list[list[str]]]:
    """Yield at most chunk_size CSV rows at a time."""

    chunk: list[list[str]] = []
    for row in reader:
        if not row or all(not field.strip() for field in row):
            continue
        chunk.append(row)
        if len(chunk) == chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def exact_quantiles(values: np.memmap, quantiles: Sequence[float]) -> list[float]:
    """Calculate NumPy-style linear quantiles using in-place memmap partitioning."""

    count = values.size
    positions = [(count - 1) * quantile for quantile in quantiles]
    required_indices = sorted(
        {index for position in positions for index in (math.floor(position), math.ceil(position))}
    )
    values.partition(required_indices)

    results: list[float] = []
    for position in positions:
        lower = math.floor(position)
        upper = math.ceil(position)
        fraction = position - lower
        lower_value = float(values[lower])
        upper_value = float(values[upper])
        results.append(lower_value + fraction * (upper_value - lower_value))
    return results


def analyze_csv(input_path: Path, chunk_size: int) -> dict[str, object]:
    """Stream the CSV and return statistics in seconds, microamps and mC."""

    temp_path: Path | None = None
    try:
        with input_path.open("r", encoding="utf-8-sig", newline="") as source:
            sample = source.read(16_384)
            source.seek(0)
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            reader = csv.reader(source, dialect)
            headers = next(reader)

            time_index, time_unit, time_scale = detect_signal_column(headers, "time")
            current_index, current_unit, current_scale = detect_signal_column(
                headers, "current"
            )
            logic_columns = detect_logic_columns(headers)
            required_index = max([time_index, current_index, *logic_columns.values()])

            print(f"Columns: {headers}")
            print(
                f"Detected time={headers[time_index]!r} ({time_unit}), "
                f"current={headers[current_index]!r} ({current_unit}), "
                f"logic={list(logic_columns)}"
            )

            temp_file = tempfile.NamedTemporaryFile(
                mode="wb", prefix="week2_idle_current_", suffix=".float64", delete=False
            )
            temp_path = Path(temp_file.name)

            count = 0
            mean_ua = 0.0
            m2_ua = 0.0
            minimum_ua = math.inf
            maximum_ua = -math.inf
            first_time_s: float | None = None
            last_time_s: float | None = None
            last_current_ua: float | None = None
            charge_microcoulombs = 0.0
            logic_non_low = {name: 0 for name in logic_columns}
            logic_invalid = {name: 0 for name in logic_columns}

            try:
                for rows in iter_chunks(reader, chunk_size):
                    row_count = len(rows)
                    times_s = np.empty(row_count, dtype=np.float64)
                    currents_ua = np.empty(row_count, dtype=np.float64)

                    for offset, row in enumerate(rows):
                        csv_line = count + offset + 2
                        if len(row) <= required_index:
                            raise ValueError(
                                f"CSV line {csv_line} has {len(row)} fields; "
                                f"at least {required_index + 1} are required."
                            )
                        try:
                            times_s[offset] = float(row[time_index]) * time_scale
                            currents_ua[offset] = (
                                float(row[current_index]) * current_scale
                            )
                        except ValueError as error:
                            raise ValueError(
                                f"Invalid time/current value on CSV line {csv_line}."
                            ) from error

                        for name, index in logic_columns.items():
                            try:
                                logic_value = float(row[index])
                            except ValueError:
                                logic_invalid[name] += 1
                            else:
                                if not math.isfinite(logic_value):
                                    logic_invalid[name] += 1
                                elif logic_value != 0.0:
                                    logic_non_low[name] += 1

                    if not np.all(np.isfinite(times_s)) or not np.all(
                        np.isfinite(currents_ua)
                    ):
                        raise ValueError("Time/current data contains NaN or infinity.")
                    if np.any(np.diff(times_s) <= 0.0):
                        raise ValueError("Timestamps are not strictly increasing.")
                    if last_time_s is not None and times_s[0] <= last_time_s:
                        raise ValueError("Timestamps are not strictly increasing at a chunk boundary.")

                    if first_time_s is None:
                        first_time_s = float(times_s[0])
                    if last_time_s is not None and last_current_ua is not None:
                        charge_microcoulombs += (
                            (last_current_ua + float(currents_ua[0]))
                            * 0.5
                            * (float(times_s[0]) - last_time_s)
                        )
                    charge_microcoulombs += float(np.trapezoid(currents_ua, times_s))

                    chunk_mean = float(np.mean(currents_ua))
                    chunk_m2 = float(np.sum((currents_ua - chunk_mean) ** 2))
                    new_count = count + row_count
                    delta = chunk_mean - mean_ua
                    mean_ua += delta * row_count / new_count
                    m2_ua += chunk_m2 + delta * delta * count * row_count / new_count
                    count = new_count
                    minimum_ua = min(minimum_ua, float(np.min(currents_ua)))
                    maximum_ua = max(maximum_ua, float(np.max(currents_ua)))
                    last_time_s = float(times_s[-1])
                    last_current_ua = float(currents_ua[-1])
                    temp_file.write(currents_ua.tobytes())
            finally:
                temp_file.close()

        if count < 2 or first_time_s is None or last_time_s is None:
            raise ValueError("At least two valid samples are required.")

        duration_s = last_time_s - first_time_s
        if duration_s <= 0.0:
            raise ValueError("Measurement duration must be positive.")

        current_values = np.memmap(temp_path, dtype=np.float64, mode="r+", shape=(count,))
        median_ua, percentile_95_ua, percentile_99_ua = exact_quantiles(
            current_values, (0.50, 0.95, 0.99)
        )
        current_values.flush()

        return {
            "headers": headers,
            "time_column": headers[time_index],
            "time_input_unit": time_unit,
            "current_column": headers[current_index],
            "current_input_unit": current_unit,
            "sample_count": count,
            "duration_s": duration_s,
            "sample_rate_hz": (count - 1) / duration_s,
            "mean_ua": mean_ua,
            "sample_std_ua": math.sqrt(m2_ua / (count - 1)),
            "min_ua": minimum_ua,
            "max_ua": maximum_ua,
            "median_ua": median_ua,
            "percentile_95_ua": percentile_95_ua,
            "percentile_99_ua": percentile_99_ua,
            "charge_mc": charge_microcoulombs / 1000.0,
            "logic_columns": logic_columns,
            "logic_non_low": logic_non_low,
            "logic_invalid": logic_invalid,
            "current_values": current_values,
            "temp_path": temp_path,
        }
    except Exception:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except PermissionError:
                pass
        raise


def write_summary(summary_path: Path, stats: dict[str, object]) -> None:
    """Write a compact metric/value/unit summary table."""

    rows: list[tuple[str, object, str]] = [
        ("sample_count", stats["sample_count"], "samples"),
        ("duration", f'{stats["duration_s"]:.9f}', "s"),
        ("sample_rate", f'{stats["sample_rate_hz"]:.6f}', "Hz"),
        ("mean_current", f'{stats["mean_ua"]:.9f}', "µA"),
        ("sample_std_current", f'{stats["sample_std_ua"]:.9f}', "µA"),
        ("min_current", f'{stats["min_ua"]:.9f}', "µA"),
        ("max_current", f'{stats["max_ua"]:.9f}', "µA"),
        ("median_current", f'{stats["median_ua"]:.9f}', "µA"),
        ("percentile_95_current", f'{stats["percentile_95_ua"]:.9f}', "µA"),
        ("percentile_99_current", f'{stats["percentile_99_ua"]:.9f}', "µA"),
        ("integrated_charge", f'{stats["charge_mc"]:.9f}', "mC"),
    ]

    logic_columns = stats["logic_columns"]
    logic_non_low = stats["logic_non_low"]
    logic_invalid = stats["logic_invalid"]
    assert isinstance(logic_columns, dict)
    assert isinstance(logic_non_low, dict)
    assert isinstance(logic_invalid, dict)
    for name in logic_columns:
        is_low = logic_non_low[name] == 0 and logic_invalid[name] == 0
        rows.extend(
            [
                (f"{name}_all_low", str(is_low).upper(), "boolean"),
                (f"{name}_non_low_samples", logic_non_low[name], "samples"),
                (f"{name}_invalid_samples", logic_invalid[name], "samples"),
            ]
        )

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(("metric", "value", "unit"))
        writer.writerows(rows)


def write_histogram(
    histogram_path: Path,
    stats: dict[str, object],
    supply_voltage_v: float,
    bins: int,
) -> None:
    """Create the Week 2 idle-current histogram at 300 dpi."""

    values = stats["current_values"]
    assert isinstance(values, np.memmap)

    counts = np.zeros(bins, dtype=np.int64)
    edges = np.linspace(float(stats["min_ua"]), float(stats["max_ua"]), bins + 1)
    histogram_chunk = 1_000_000
    for start in range(0, values.size, histogram_chunk):
        chunk_counts, _ = np.histogram(values[start : start + histogram_chunk], bins=edges)
        counts += chunk_counts

    centers = (edges[:-1] + edges[1:]) * 0.5
    widths = np.diff(edges)
    figure, axis = plt.subplots(figsize=(10, 6))
    axis.bar(
        centers,
        counts,
        width=widths,
        color="#4C78A8",
        edgecolor="#244A64",
        linewidth=0.35,
        alpha=0.9,
        label="Idle current samples",
    )
    axis.axvline(
        float(stats["mean_ua"]),
        color="#D62728",
        linestyle="--",
        linewidth=1.8,
        label=f'Mean: {stats["mean_ua"]:.3f} µA',
    )
    axis.axvline(
        float(stats["median_ua"]),
        color="#2CA02C",
        linestyle="-.",
        linewidth=1.8,
        label=f'Median: {stats["median_ua"]:.3f} µA',
    )
    axis.set_title("Idle Current Distribution – nRF52840 Dongle", fontsize=14)
    axis.set_xlabel("Current (µA)")
    axis.set_ylabel("Sample count")
    axis.grid(axis="y", alpha=0.25)
    axis.legend()
    annotation = (
        f'Duration: {stats["duration_s"]:.0f} s  |  '
        f"Supply: {supply_voltage_v:.1f} V  |  "
        f'Sampling: {stats["sample_rate_hz"] / 1000.0:.0f} kS/s'
    )
    axis.text(
        0.5,
        0.98,
        annotation,
        transform=axis.transAxes,
        ha="center",
        va="top",
        fontsize=10,
        bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "0.8"},
    )
    figure.tight_layout()
    histogram_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(histogram_path, dpi=300, bbox_inches="tight")
    plt.close(figure)


def print_results(stats: dict[str, object]) -> None:
    """Print all requested metrics and logic checks."""

    print(f'Samples: {stats["sample_count"]:,}')
    print(f'Duration: {stats["duration_s"]:.9f} s')
    print(f'Actual sample rate: {stats["sample_rate_hz"]:.6f} Hz')
    print(f'Mean: {stats["mean_ua"]:.9f} µA')
    print(f'Sample standard deviation: {stats["sample_std_ua"]:.9f} µA')
    print(f'Min: {stats["min_ua"]:.9f} µA')
    print(f'Max: {stats["max_ua"]:.9f} µA')
    print(f'Median: {stats["median_ua"]:.9f} µA')
    print(f'Percentile 95: {stats["percentile_95_ua"]:.9f} µA')
    print(f'Percentile 99: {stats["percentile_99_ua"]:.9f} µA')
    print(f'Integrated charge: {stats["charge_mc"]:.9f} mC')

    logic_columns = stats["logic_columns"]
    logic_non_low = stats["logic_non_low"]
    logic_invalid = stats["logic_invalid"]
    assert isinstance(logic_columns, dict)
    assert isinstance(logic_non_low, dict)
    assert isinstance(logic_invalid, dict)
    if not logic_columns:
        print("Logic D0-D3: not present in CSV")
    else:
        for name in logic_columns:
            is_low = logic_non_low[name] == 0 and logic_invalid[name] == 0
            print(
                f"{name}: {'LOW for all samples' if is_low else 'CHECK FAILED'} "
                f"(non-low={logic_non_low[name]}, invalid={logic_invalid[name]})"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--histogram", type=Path, default=DEFAULT_HISTOGRAM)
    parser.add_argument("--chunk-size", type=int, default=250_000)
    parser.add_argument("--histogram-bins", type=int, default=100)
    parser.add_argument("--supply-voltage-v", type=float, default=5.0)
    args = parser.parse_args()
    if args.chunk_size <= 0:
        parser.error("--chunk-size must be positive")
    if args.histogram_bins <= 0:
        parser.error("--histogram-bins must be positive")
    return args


def main() -> int:
    args = parse_args()
    input_path = args.input_csv.resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"Input CSV not found: {input_path}")

    stats = analyze_csv(input_path, args.chunk_size)
    temp_path = stats["temp_path"]
    current_values = stats["current_values"]
    assert isinstance(temp_path, Path)
    assert isinstance(current_values, np.memmap)
    try:
        write_summary(args.summary.resolve(), stats)
        write_histogram(
            args.histogram.resolve(),
            stats,
            args.supply_voltage_v,
            args.histogram_bins,
        )
        print_results(stats)
        print(f"Summary: {args.summary.resolve()}")
        print(f"Histogram: {args.histogram.resolve()}")
    finally:
        mmap = getattr(current_values, "_mmap", None)
        if mmap is not None:
            mmap.close()
        del current_values
        stats.pop("current_values", None)
        os.unlink(temp_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
