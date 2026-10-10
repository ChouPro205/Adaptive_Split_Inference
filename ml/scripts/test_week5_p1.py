"""10,000 deterministic I2/1 Python round trips with public test keys only."""
import argparse
import hashlib
from pathlib import Path
import random
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from p1 import Profile, descriptor, protect, unprotect
from week5_common import mapping, provenance, write_json, ROOT

SEED = 20261005


def run(cases, output):
    if output.exists():
        raise ValueError('Output exists; choose a new path to preserve evidence')
    if cases < 10000:
        raise ValueError("At least 10,000 cases required")
    rng = random.Random(SEED)
    # Public reproducible test material; not deployment keys or registry IDs.
    keys = [bytes(range(32)), bytes(32), bytes([255]) * 32,
            *[hashlib.sha256(f"PUBLIC-WEEK5-TEST-KEY-{i}".encode()).digest() for i in range(13)]]
    shapes = [(r['channels'], r['quantization_shape'][2]) for r in mapping()]
    shapes += [(1, 1), (256, 1), (256, 128), (1, 32768), (3, 7), (17, 13)]
    checksums = hashlib.sha256()
    started = time.monotonic()
    counts = {}
    for i in range(cases):
        c, length = shapes[i % len(shapes)]
        profile = Profile(0x575435, (i % 11) + 1, c, length, (i % len(keys)) + 1)
        metadata = descriptor(profile)
        nonce = struct.pack('<IQ', 1 + i % 5, i + 1)
        key = keys[i % len(keys)]
        size = c * length
        data = rng.randbytes(size)
        # Exercise -128/127 in each nonscalar case, and all-equal/zero patterns.
        if i % 29 == 0:
            data = bytes([128]) * size
        elif i % 31 == 0:
            data = bytes([127]) * size
        elif i % 37 == 0:
            data = bytes(size)
        elif size >= 2:
            data = b'\x80\x7f' + data[2:]
        protected = protect(data, metadata, nonce, key, profile)
        if protected != protect(data, metadata, nonce, key, profile):
            raise AssertionError(f"Nondeterministic protect case {i}")
        if unprotect(protected, metadata, nonce, key, profile) != data:
            raise AssertionError(f"Round-trip differs case {i}")
        counts[f"1,{c},{length}"] = counts.get(f"1,{c},{length}", 0) + 1
        checksums.update(metadata + nonce + protected)
        if (i + 1) % 1000 == 0:
            print(f"P1 {i + 1}/{cases} PASS", flush=True)
    result = {"status": "PASS", "cases": cases, "tensors_executed": cases, "failed_tensors": 0,
              "determinism_checks": cases, "bit_exact_roundtrips": cases,
              "seed": SEED, "test_keys": len(keys), "shapes_and_counts": counts,
              "output_stream_sha256": checksums.hexdigest(), "elapsed_seconds": time.monotonic() - started,
              "algorithm": "I2/1 existing IETF ChaCha20 counter=0, source-channel affine256, Fisher-Yates rejection",
              "profile_ids": "TEST ONLY; split_id=s+1, not a deployment registry",
              "acceptance": "Python host only; C and 50 official Python/C vectors remain Week 6",
              "provenance": provenance(' '.join(sys.argv))}
    write_json(output, result)
    print(f"PASS {cases} bit-exact round trips; evidence {output}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', type=int, default=10000)
    parser.add_argument('--output', type=Path, default=ROOT / 'ml/provenance/week5/p1_10000.json')
    args = parser.parse_args()
    run(args.cases, args.output)
