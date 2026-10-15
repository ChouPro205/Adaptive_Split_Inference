"""Post-approval mapping/descriptor/220 real-tail check; public test key only."""
import argparse
from pathlib import Path
from week5_registry_acceptance_v2 import approved_registry
from verify_week5_real import verify
from week5_common_v2 import ROOT, PACKAGE


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--approval', type=Path, required=True)
    parser.add_argument('--expected-approval-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    registry, proof = approved_registry(args.registry, args.approval, args.expected_approval_sha256)
    verify(PACKAGE, ROOT/'ml/artifacts/week5/quantization20', args.output, registry, proof)
