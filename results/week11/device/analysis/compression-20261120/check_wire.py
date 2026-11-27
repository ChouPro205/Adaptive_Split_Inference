"""Verify Rice wire lengths and a deterministic set of actual encoded packets on DS1 val."""
import argparse
import json
from pathlib import Path

import numpy as np
from torch.nn import functional as F

from codec_probe import HERE, load_json, rice_body_bytes, transport, validation_only


def pack(row):
    values = [int(x) for x in row]
    deltas = [b - a for a, b in zip(values[:-1], values[1:])]
    zigzag = [2 * d if d >= 0 else -2 * d - 1 for d in deltas]
    k = min(range(8), key=lambda p: sum((v >> p) + 1 + p for v in zigzag))
    words = ['0' * (v >> k) + '1' + (format(v % (1 << k), f'0{k}b') if k else '') for v in zigzag]
    bits = ''.join(words)
    padding = (-len(bits)) % 8
    return bytes([values[0] & 255, k]) + int(bits + '0' * padding, 2).to_bytes((len(bits) + padding) // 8, 'big')


def unpack(body, count):
    first, k = body[:2]
    values = [first if first < 128 else first - 256]
    bits = ''.join(format(b, '08b') for b in body[2:])
    index = 0
    for _ in range(count - 1):
        stop = bits.index('1', index)
        value = ((stop - index) << k) + (int(bits[stop+1:stop+1+k], 2) if k else 0)
        delta = value // 2 if value % 2 == 0 else -(value // 2) - 1
        values.append(values[-1] + delta)
        index = stop + 1 + k
    if any(c != '0' for c in bits[index:]) or len(bits) - index >= 8:
        raise ValueError('Invalid padding')
    return values


def run():
    x, _, patients = validation_only()
    probe = load_json(HERE / 'codec_results.json')
    methods = {}
    for bins in (360, 180, 46, 20):
        name = 's0_rice' if bins == 360 else f's0_rice_{bins}'
        row = probe['methods'][name]
        pooled = x if bins == 360 else F.adaptive_avg_pool1d(x, bins)
        _, quantized = transport(pooled)
        sizes = rice_body_bytes(quantized)
        if not np.isclose(sizes.mean(), row['body_B_mean']) or np.percentile(sizes, 95) != row['body_B_p95']:
            raise ValueError(f'Size result mismatch for {name}')
        checked = 0
        for patient in probe['records']:
            indexes = np.flatnonzero(patients == patient)
            for index in indexes[np.linspace(0, len(indexes) - 1, num=12, dtype=int)]:
                original = quantized[index, 0]
                payload = pack(original)
                if len(payload) != sizes[index] or not np.array_equal(unpack(payload, bins), original):
                    raise ValueError(f'Rice roundtrip failed at {name} beat {index}')
                checked += 1
        frame = sizes + row['envelope_B']
        fragments = (frame + 235) // 236
        methods[name] = {'fragments_mean': float(fragments.mean()), 'fragments_max': int(fragments.max()),
                         'frame_B_min': int(frame.min()), 'frame_B_max': int(frame.max()),
                         'app_transferred_B_mean': float(np.mean(frame + 8 * fragments)),
                         'rice_byte_roundtrips': checked}
    return {'samples': len(x), 'att_mtu': 247, 'binding_header_B': 8, 'methods': methods}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    with args.out.open('x', encoding='utf-8') as out:
        json.dump(report, out, indent=2)
    print(json.dumps(report, indent=1))
