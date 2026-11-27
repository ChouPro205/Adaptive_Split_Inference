# Deterministic zip of the NoPeek v2 run directory (pilot + grid, 891 checkpoints) for the GitHub Release asked by SV1 on
# 2026-11-13 (section 4), as was done for checkpoint C5. Runs verify_runs.check on the local run directory first, then
# writes, in a NEW directory under ignored ml/data:
#   <NAME>.zip        PACKAGE_SHA256SUMS.txt first, then every run file under its repo path ml/data/runs/nopeek-m1-v2-20261112/...,
#                     sorted, fixed timestamp and permissions, so two builds give the same bytes; extract at a checkout root;
#   <NAME>.zip.sha256 its sha256sum line;
#   PACKAGE_SHA256SUMS.txt  the same list as inside the zip (also a Release asset, to check hashes without the download).
# The zip is then extracted to a temporary directory and checked again: entry list, CRC, verify_runs.check on the extracted
# tree (including PACKAGE_SHA256SUMS.txt) and byte equality with every source file.
# Usage, from the worktree root: python -B ml/provenance/m1-nopeek-v2-release-20261113/make_archive.py <new dir under ml/data>
import hashlib
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_runs as v  # noqa: E402

NAME = 'SV3_M1_NOPEEK_V2_CHECKPOINTS_20261112.zip'
STAMP = (2026, 11, 12, 0, 0, 0)


def entry(arcname):
    info = zipfile.ZipInfo(arcname, date_time=STAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3
    return info


def main():
    out = Path(sys.argv[1]).resolve()
    v.need(out.is_relative_to(Path('ml/data').resolve()) and not out.exists(), 'Output must be a new directory under ignored ml/data')
    report, entries = v.check('.')
    sums = v.sums_text(entries).encode('ascii')
    names = [v.SUMS_NAME] + [f'{v.RUNS}/{rel}' for rel, _ in entries]
    out.mkdir(parents=True)
    archive = out/NAME
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr(entry(v.SUMS_NAME), sums, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        for rel, _ in entries:
            z.writestr(entry(f'{v.RUNS}/{rel}'), Path(v.RUNS, rel).read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    digest = v.sha(archive)
    (out/f'{NAME}.sha256').write_bytes(f'{digest}  {NAME}\n'.encode('ascii'))
    (out/v.SUMS_NAME).write_bytes(sums)
    with tempfile.TemporaryDirectory() as d, zipfile.ZipFile(archive) as z:
        v.need(z.namelist() == names and z.testzip() is None, 'Archive entry list or CRC differs')
        z.extractall(d)
        extracted, _ = v.check(d)
        v.need(extracted.get('package_sums_file_checked') is True and extracted['package_sums_sha256'] == report['package_sums_sha256'],
               'Extracted tree check differs')
        for rel, _ in entries:
            v.need(Path(d, v.RUNS, rel).read_bytes() == Path(v.RUNS, rel).read_bytes(), f'Extracted file differs: {rel}')
    print(f"{NAME} entries={len(names)} run_files={report['files']} checkpoints={report['checkpoints']} bytes={archive.stat().st_size} "
          f"sha256={digest} package_sums_sha256={report['package_sums_sha256']} extracted_check=PASS extracted_files_identical=True")


if __name__ == '__main__':
    main()
