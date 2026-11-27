# Deterministic zip of package A (manifest f005b3ea...) for delivery, plus its .sha256 line, in a NEW directory under
# ignored ml/data. Entries are sorted, stored under one top folder, with a fixed timestamp and permissions, so two builds
# give the same bytes. The archive is then extracted to a temporary directory and every file compared with the package.
# Run from the worktree root: python -B <this file> <new output directory under ml/data>
import hashlib
import sys
import tempfile
import zipfile
from pathlib import Path

PACKAGE = Path('ml/data/package-a/m1-v4-package-a-20261105-v1')
TOP = 'm1-v4-package-a-20261105-v1'
NAME = 'SV3_M1_V4_PACKAGE_A_20261105.zip'
STAMP = (2026, 11, 5, 0, 0, 0)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

out = Path(sys.argv[1]).resolve()
if not out.is_relative_to(Path('ml/data').resolve()) or out.exists():
    raise SystemExit('Output must be a new directory under ignored ml/data')
if sha(PACKAGE/'manifest.json') != 'f005b3ea4e2440186bce4218c537b12f3b54fe734631c56a90c2378748aedf2f':
    raise SystemExit('Package manifest differs')
files = sorted(p.relative_to(PACKAGE).as_posix() for p in PACKAGE.rglob('*') if p.is_file())
out.mkdir(parents=True)
archive = out/NAME
with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for rel in files:
        info = zipfile.ZipInfo(f'{TOP}/{rel}', date_time=STAMP)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        info.create_system = 3
        z.writestr(info, (PACKAGE/rel).read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
digest = sha(archive)
(out/f'{NAME}.sha256').write_bytes(f'{digest}  {NAME}\n'.encode('ascii'))
with tempfile.TemporaryDirectory() as d, zipfile.ZipFile(archive) as z:
    names = z.namelist()
    if names != [f'{TOP}/{rel}' for rel in files] or z.testzip() is not None:
        raise SystemExit('Archive entry list or CRC differs')
    z.extractall(d)
    for rel in files:
        if sha(Path(d)/TOP/rel) != sha(PACKAGE/rel):
            raise SystemExit(f'Extracted file differs: {rel}')
print(f'{NAME} files={len(files)} bytes={archive.stat().st_size} sha256={digest} extracted_files_identical=True')
