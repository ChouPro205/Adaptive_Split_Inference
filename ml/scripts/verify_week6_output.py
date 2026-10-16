"""Check real logits, original-channel recovery, all split tails and s10 identity."""
import argparse
from pathlib import Path
from week6_p1 import MODEL_PACKAGE, output_semantics, write

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--expected-manifest-sha256', required=True)
    p.add_argument('--model-package', type=Path, default=MODEL_PACKAGE)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    result = output_semantics(a.package, a.expected_manifest_sha256, a.model_package)
    write(a.output, result)
    print('PASS B: N,S,V,F,Q raw logits, first-index ties, s0..s9 reference tails, s9 NC, s10 exact identity')
