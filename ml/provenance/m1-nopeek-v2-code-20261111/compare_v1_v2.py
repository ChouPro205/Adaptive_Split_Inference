# Key-level diff of NoPeek protocol v1 -> v2 and of every plan run config v1 -> v2. Reads JSON only.
# Run from the worktree root: python -B <this file>
import json
from collections import Counter
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def leaves(value, prefix=''):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, f'{prefix}.{key}' if prefix else key)
    else:
        yield prefix, value


a = dict(leaves(load('ml/configs/mitdb_m1_nopeek_protocol_v1.json')))
b = dict(leaves(load('ml/configs/mitdb_m1_nopeek_protocol_v2.json')))
print('PROTOCOL v1 -> v2 (leaf keys)')
for key in sorted(set(a) | set(b)):
    if key not in a:
        print('  ADDED  ', key)
    elif key not in b:
        print('  REMOVED', key)
    elif a[key] != b[key]:
        print('  CHANGED', key)
print(f'  unchanged leaves: {sum(1 for k in a if k in b and a[k] == b[k])} of {len(a)} in v1')

v1, v2 = Path('ml/manifests/mitdb-nopeek-m1-v1'), Path('ml/manifests/mitdb-nopeek-m1-v2')
p1, p2 = load(v1/'plan-manifest.json'), load(v2/'plan-manifest.json')
ids1, ids2 = [r['run_id'] for r in p1['runs']], [r['run_id'] for r in p2['runs']]
print('PLAN v1 -> v2')
print(f'  run ids identical and in the same order: {ids1 == ids2} ({len(ids2)} runs)')
changes = Counter()
for rid in ids2:
    c1, c2 = load(v1/f'{rid}.json'), load(v2/f'{rid}.json')
    for key in sorted(set(c1) | set(c2)):
        if c1.get(key) != c2.get(key):
            changes[(key, json.dumps(c1.get(key)), json.dumps(c2.get(key)))] += 1
for (key, old, new), n in sorted(changes.items()):
    print(f'  config key {key}: {old} -> {new} in {n} configs')
print('  plan-manifest top-level keys that differ:', sorted(k for k in set(p1) | set(p2) if p1.get(k) != p2.get(k)))
print('  sources whose SHA-256 differs:', sorted(k for k in set(p1['sources_sha256']) | set(p2['sources_sha256'])
                                                 if p1['sources_sha256'].get(k) != p2['sources_sha256'].get(k)))
