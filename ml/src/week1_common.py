"""Shared Week 1 configuration, hashing, and validation helpers."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Iterable


ML_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ML_ROOT / "configs"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_DATASET_COMPONENT = re.compile(r"^[A-Za-z0-9._-]+$")
NORMALIZED_TEXT_SUFFIXES = {".csv", ".json", ".md", ".txt"}
TEXT_HASH_POLICY = "sha256_utf8_lf_normalized"
BINARY_HASH_POLICY = "sha256_raw_bytes"


class ValidationError(RuntimeError):
    """A reproducibility or data invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def load_json(path: Path) -> dict:
    require(path.is_file(), f"Required JSON file is missing: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Cannot read valid JSON from {path}: {exc}") from exc
    require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def load_config(name_or_path: str | Path) -> tuple[Path, dict]:
    path = Path(name_or_path)
    if not path.is_absolute():
        candidate = CONFIG_DIR / path
        path = candidate if candidate.exists() else ML_ROOT / path
    path = path.resolve()
    return path, load_json(path)


def ml_path(relative_path: str) -> Path:
    path = (ML_ROOT / relative_path).resolve()
    require(ML_ROOT == path or ML_ROOT in path.parents, f"Path escapes ml/: {relative_path}")
    return path


def configured_path(config: dict, key: str) -> Path:
    try:
        relative = config["paths"][key]
    except KeyError as exc:
        raise ValidationError(f"Config is missing paths.{key}") from exc
    require(isinstance(relative, str) and relative, f"Invalid paths.{key}")
    return ml_path(relative)


def configured_relative_path(config: dict, key: str, root_key: str = "raw_dir") -> str:
    """Return a configured path relative to another configured directory."""
    root = configured_path(config, root_key)
    target = configured_path(config, key)
    require(root in target.parents, f"paths.{key} must be inside paths.{root_key}")
    return target.relative_to(root).as_posix()


def safe_dataset_relative_path(value: str, label: str = "dataset path") -> str:
    """Validate an untrusted POSIX-style path from dataset metadata."""
    require(isinstance(value, str), f"Invalid {label}: expected text")
    normalized = value.strip().replace("\\", "/")
    require(normalized, f"Invalid {label}: empty path")
    require(not normalized.startswith(("/", "//")), f"Invalid {label}: absolute path {value!r}")
    require(re.match(r"^[A-Za-z]:", normalized) is None,
            f"Invalid {label}: drive-qualified path {value!r}")
    components = normalized.split("/")
    require(all(component not in ("", ".", "..") for component in components),
            f"Invalid {label}: unsafe path component in {value!r}")
    require(all(SAFE_DATASET_COMPONENT.fullmatch(component) is not None for component in components),
            f"Invalid {label}: unsupported path component in {value!r}")
    return PurePosixPath(*components).as_posix()


def confined_dataset_path(root: Path, relative_path: str, label: str = "dataset path") -> Path:
    """Resolve a validated dataset path and prove it remains below root."""
    safe_relative = safe_dataset_relative_path(relative_path, label)
    resolved_root = root.resolve()
    destination = resolved_root.joinpath(*PurePosixPath(safe_relative).parts).resolve()
    require(resolved_root in destination.parents,
            f"Invalid {label}: destination escapes dataset root: {relative_path!r}")
    return destination


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    require(path.is_file(), f"Cannot hash missing file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_text_sha256(path: Path) -> str:
    """Hash UTF-8 text after canonicalizing CRLF/CR to LF."""
    require(path.is_file(), f"Cannot hash missing text file: {path}")
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"Cannot read UTF-8 text artifact {path}: {exc}") from exc
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def artifact_sha256(path: Path) -> str:
    """Hash repository artifacts reproducibly while preserving binary bytes."""
    if path.suffix.lower() in NORMALIZED_TEXT_SUFFIXES:
        return normalized_text_sha256(path)
    return sha256_file(path)


def download_file(url: str, destination: Path, overwrite: bool = False) -> str:
    """Download atomically; existing non-empty files are retained unless requested."""
    if destination.is_file() and destination.stat().st_size > 0 and not overwrite:
        return "kept"
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    try:
        with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as handle:
            shutil.copyfileobj(response, handle, length=1024 * 1024)
        require(partial.stat().st_size > 0, f"Downloaded empty file from {url}")
        partial.replace(destination)
    except Exception:
        if partial.exists():
            partial.unlink()
        raise
    return "downloaded"


def config_sha256(path: Path) -> str:
    return normalized_text_sha256(path)


def require_raw_dir(raw_dir: Path) -> None:
    require(raw_dir.is_dir(), f"Raw dataset directory does not exist: {raw_dir}")
    try:
        has_entry = next(raw_dir.iterdir(), None) is not None
    except OSError as exc:
        raise ValidationError(f"Cannot inspect raw dataset directory {raw_dir}: {exc}") from exc
    require(has_entry, f"Raw dataset directory is empty: {raw_dir}")


def load_expected_records(path: Path, expected_count: int) -> list[str]:
    require(path.is_file(), f"Expected-record list is missing: {path}")
    records = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(len(records) == expected_count, f"Expected {expected_count} record IDs in {path}, found {len(records)}")
    require(len(records) == len(set(records)), f"Duplicate record IDs in {path}")
    return records


def parse_physionet_checksums(path: Path, pinned_manifest_sha256: str) -> dict[str, str]:
    require(HEX64.fullmatch(pinned_manifest_sha256) is not None,
            "Config does not contain a pinned PhysioNet SHA256SUMS.txt hash")
    actual_manifest_hash = sha256_file(path)
    require(actual_manifest_hash == pinned_manifest_sha256,
            f"Checksum manifest hash mismatch: expected {pinned_manifest_sha256}, got {actual_manifest_hash}")
    checksums: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\r\n")
            if not line:
                continue
            parts = line.split(maxsplit=1)
            require(len(parts) == 2 and HEX64.fullmatch(parts[0]) is not None,
                    f"Malformed checksum line {line_number} in {path}")
            relative = parts[1].lstrip("*./").replace("\\", "/")
            require(relative and relative not in checksums,
                    f"Duplicate or empty checksum path at line {line_number}: {relative!r}")
            checksums[relative] = parts[0]
    require(checksums, f"Checksum manifest contains no entries: {path}")
    return checksums


def verify_files_against_checksums(
    raw_dir: Path,
    relative_paths: Iterable[str],
    checksums: dict[str, str],
) -> tuple[int, str]:
    paths = sorted(set(path.replace("\\", "/") for path in relative_paths))
    require(paths, "No required files were supplied for checksum verification")
    tree = hashlib.sha256()
    for relative in paths:
        require(relative in checksums, f"Official checksum missing for required file: {relative}")
        local_path = raw_dir / Path(relative)
        require(local_path.is_file(), f"Required dataset file is missing: {local_path}")
        require(local_path.stat().st_size > 0, f"Required dataset file is empty: {local_path}")
        actual = sha256_file(local_path)
        expected = checksums[relative]
        require(actual == expected,
                f"Checksum mismatch for {relative}: expected {expected}, got {actual}")
        tree.update(f"{relative}\0{actual}\n".encode("utf-8"))
    return len(paths), tree.hexdigest()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    require(path.is_file(), f"Required CSV file is missing: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames is not None, f"CSV has no header: {path}")
        rows = list(reader)
    require(rows, f"CSV contains no data rows: {path}")
    return rows


def patient_sets(rows: Iterable[dict[str, str]]) -> dict[str, set[str]]:
    result = {"train": set(), "val": set(), "test": set()}
    for row in rows:
        split = row.get("split", "")
        if split in result:
            patient_id = row.get("patient_id", "")
            require(bool(patient_id), f"Missing patient_id in {split} row")
            result[split].add(patient_id)
    return result


def verify_no_patient_leakage(sets: dict[str, set[str]]) -> None:
    for split in ("train", "val", "test"):
        require(bool(sets.get(split)), f"Split has no patients: {split}")
    for left, right in (("train", "val"), ("train", "test"), ("val", "test")):
        overlap = sets[left] & sets[right]
        require(not overlap, f"Patient leakage between {left} and {right}: {sorted(overlap)[:10]}")


def run_cli(main) -> None:
    try:
        main()
    except ValidationError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
