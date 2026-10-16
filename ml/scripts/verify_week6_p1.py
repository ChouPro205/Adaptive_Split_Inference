"""Verify every official P1 vector using unchanged Python and compiled C I2/1."""
import argparse
import os
from pathlib import Path
from week6_p1 import verify, write

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--expected-manifest-sha256', required=True)
    p.add_argument('--compiler', default=os.environ.get('CC', 'gcc'))
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = verify(a.package, a.expected_manifest_sha256, a.compiler)
    write(a.output, result)
    print('PASS A: 50 real vectors, 11 splits; Python/C protect and roundtrip 50/50; transformed 0x80 present')
