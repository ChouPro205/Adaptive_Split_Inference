"""Approved ASI testbed registry: descriptor and 220 real tensors, public test key."""
import argparse
from pathlib import Path
from week5_registry_acceptance_v3 import approved_registry
from verify_week5_real import verify
from week5_common_v2 import ROOT, PACKAGE


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--registry', type=Path, required=True)
    p.add_argument('--approval', type=Path, required=True)
    p.add_argument('--expected-approval-sha256', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    registry, proof = approved_registry(a.registry, a.approval, a.expected_approval_sha256)
    verify(PACKAGE, ROOT/'ml/artifacts/week5/quantization20', a.output, registry, proof)
