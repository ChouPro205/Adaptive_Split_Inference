# Anonymous HTTPS download of every asset of the NoPeek v2 checkpoint Release, using the asset URLs of the saved
# `gh release view` (logs/release-view.json), into a NEW directory under ignored ml/data. No token or cookie is sent.
# Each downloaded file is compared with the local asset and with the GitHub digest; the zip is checked against its .sha256
# line, and the separate PACKAGE_SHA256SUMS.txt asset against the copy inside the zip. Prints one line per check and exits
# non-zero if any check differs. Usage, from the worktree root: python -B <this file> <new directory under ml/data>
import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

LOGS = Path('ml/provenance/m1-nopeek-v2-release-publication-20261113/logs')
LOCAL = Path('ml/data/release-nopeek-m1-v2-20261113')
ZIP = 'SV3_M1_NOPEEK_V2_CHECKPOINTS_20261112.zip'
SUMS = 'PACKAGE_SHA256SUMS.txt'
EXPECTED = {ZIP, f'{ZIP}.sha256', SUMS}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def download(url, target):
    digest, size = hashlib.sha256(), 0
    with urllib.request.urlopen(urllib.request.Request(url), timeout=600) as response, target.open('xb') as f:
        status = response.status
        while chunk := response.read(1 << 20):
            digest.update(chunk)
            size += len(chunk)
            f.write(chunk)
    return status, size, digest.hexdigest()


def main():
    out = Path(sys.argv[1]).resolve()
    if not out.is_relative_to(Path('ml/data').resolve()) or out.exists():
        raise SystemExit('Output must be a new directory under ignored ml/data')
    view = json.loads((LOGS/'release-view.json').read_text(encoding='utf-8'))
    assets = sorted(view['assets'], key=lambda a: a['name'])
    if {a['name'] for a in assets} != EXPECTED:
        raise SystemExit(f"Release assets differ: {[a['name'] for a in assets]}")
    out.mkdir(parents=True)
    ok = True
    for a in assets:
        status, size, digest = download(a['url'], out/a['name'])
        local = sha(LOCAL/a['name'])
        good = status == 200 and digest == local and a['digest'] == f'sha256:{digest}' and size == a['size']
        ok &= good
        print(f"{a['name']} http={status} bytes={size} sha256={digest} matches_local={str(digest == local).lower()} "
              f"github_digest_matches={str(a['digest'] == f'sha256:{digest}').lower()}")
    line = (out/f'{ZIP}.sha256').read_text(encoding='ascii').split()
    zip_ok = line == [sha(out/ZIP), ZIP]
    ok &= zip_ok
    print(f"{ZIP}: {'OK' if zip_ok else 'FAILED'} (sha256sum line of the downloaded .sha256)")
    with zipfile.ZipFile(out/ZIP) as z:
        sums_ok = z.read(SUMS) == (out/SUMS).read_bytes()
    ok &= sums_ok
    print(f"{SUMS} asset equals the copy inside the downloaded zip: {'OK' if sums_ok else 'FAILED'}")
    if not ok:
        raise SystemExit('Download check differs')


if __name__ == '__main__':
    main()
