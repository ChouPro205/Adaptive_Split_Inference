"""Package authenticated Week 6 vectors with deterministic ZIP bytes and external hashes."""
import argparse
from pathlib import Path
from week6_p1 import archive, authenticate_package, write

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--expected-manifest-sha256', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    authenticate_package(a.package, a.expected_manifest_sha256)
    r = archive(a.package, a.output)
    with Path(str(a.output) + '.sha256').open('x', encoding='ascii', newline='\n') as f:
        f.write(r['sha256'] + '  ' + a.output.name + '\n')
    write(Path(str(a.output) + '.json'), {**r, 'manifest_sha256': a.expected_manifest_sha256})
    print(r)
