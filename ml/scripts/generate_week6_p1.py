"""Generate the official 50 real P1 vectors from authenticated Week 5 tensors."""
import argparse
from pathlib import Path
from week6_p1 import GOLDENS, MODEL_PACKAGE, generate

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--goldens', type=Path, default=GOLDENS)
    p.add_argument('--model-package', type=Path, default=MODEL_PACKAGE)
    p.add_argument('--source-commit')
    a = p.parse_args()
    print(generate(a.output, goldens=a.goldens, model_package=a.model_package, source_commit=a.source_commit))
