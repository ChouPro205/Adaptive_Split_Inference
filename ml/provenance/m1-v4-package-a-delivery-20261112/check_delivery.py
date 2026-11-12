# Delivery check for package A (M1 v4, built 2026-11-05, manifest f005b3ea...), before it goes to SV2 with SV1 in cc.
# Runs what SV2 will check in its receipt, plus the confirmed calibration rule:
#   1. package identity and the builder's own verify (checkpoint = lock, weights = checkpoint, header, shapes, inventory);
#   2. calibration indices re-derived with the SV2 edge/quantize_tail.py rule from the train count alone;
#   3. calibration/z_s0 equals the normalized train_X rows of those indices bit for bit (the input SV2 asked for);
#   4. z_s0-z_s9 of the 1000 calibration beats and z_s0-z_s10 + reference logits of the 20 check beats recomputed
#      on CPU from the packaged checkpoint, compared bit for bit with the packaged files.
# Reads train/val arrays only (bound by plan v4); never opens DS2. Run from the worktree root: python -B <this file>
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, 'ml/scripts')
import package_m1_v4_a as pkg  # noqa: E402
from week3_common import need, same_bits  # noqa: E402
from week3_sv2_common import configure  # noqa: E402

PACKAGE = Path('ml/data/package-a/m1-v4-package-a-20261105-v1')
MANIFEST_SHA = 'f005b3ea4e2440186bce4218c537b12f3b54fe734631c56a90c2378748aedf2f'
INDICES_SHA = 'c7e2b3e983fb39760fa5e05d4b09a0597221efb18cbdb11e2fe33bd3d5fa81f0'
SV2_RULE_LINE = 'indices = np.unique(np.linspace(0, len(x) - 1, min(count, len(x))).round().astype(np.int64))'
NORMALIZATION_SHA = '1ae60f3f493427286ddfbcd3e269c6dce312a93351a75ebdf69db61941d23b89'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
read = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))
out = {}

# 1. Identity and the builder's verify.
need(sha(PACKAGE/'manifest.json') == MANIFEST_SHA, 'Package manifest differs from the 2026-11-05 candidate')
out['verify'] = pkg.verify(PACKAGE)
manifest = read(PACKAGE/'manifest.json')
need(manifest['arrays']['DS2_opened'] is False, 'Package opened DS2')

# 2. Calibration rule (SV2 confirmed via SV1 on 2026-11-12): count 1000 from DS1 train, linspace -> round -> unique.
need(SV2_RULE_LINE in Path('edge/quantize_tail.py').read_text(encoding='utf-8'), 'SV2 calibration rule line not found in edge/quantize_tail.py')
rule = read(PACKAGE/'calibration/rule.json')
n_train = int(sum(read(PACKAGE/'data/processed-manifest.json')['splits']['train']['counts']))
count = 1000
indices = np.unique(np.linspace(0, n_train - 1, min(count, n_train)).round().astype(np.int64))
need(rule['n_train'] == n_train and rule['count'] == len(indices) == count and rule['split'] == 'train', 'Calibration count or split differs')
need(hashlib.sha256(indices.astype('<i8').tobytes()).hexdigest() == rule['train_row_indices_le_int64_sha256'] == INDICES_SHA,
     'Calibration indices differ from the SV2 rule')
with (PACKAGE/'calibration/samples.csv').open(encoding='utf-8', newline='') as f:
    rows = list(csv.DictReader(f))
need([int(r['sample_index']) for r in rows] == list(range(count)) and [int(r['source_row_index']) for r in rows] == indices.tolist()
     and {r['split'] for r in rows} == {'train'}, 'calibration/samples.csv order or rows differ')
out['calibration'] = {'n_train': n_train, 'count': count, 'indices_sha256': INDICES_SHA, 'rule_line_in_edge_quantize_tail': True,
                      'samples_csv_order': 'sample_index 0-999 = train rows of the rule, ascending'}

# 3. Normalized input, and normalization identity.
need(sha(PACKAGE/'data/normalization.json') == NORMALIZATION_SHA, 'Packaged normalization differs')
configure()
lock, deployment, plan, config = pkg.locked()
data = pkg.arrays(plan)  # Train/val only, each checked against plan v4.
train_x, _, train_rows = data['train']
z0 = np.load(PACKAGE/'calibration/z_s0.npy', allow_pickle=False)
need(z0.dtype == np.float32 and same_bits(z0, train_x[indices].reshape(count, 1, 360)), 'calibration/z_s0 is not the normalized train input')
out['input'] = {'file': 'calibration/z_s0.npy', 'shape': list(z0.shape), 'equals_normalized_train_X_rows': True,
                'normalization_sha256': NORMALIZATION_SHA}

# 4. Recompute golden tensors from the checkpoint, bit for bit.
model = pkg.load_model(deployment, config)
need(sha(PACKAGE/'model/checkpoint.pt') == deployment['sha256'], 'Packaged checkpoint differs from the lock')
zc = pkg.golden(model, train_x, indices.tolist())
for s in range(10):
    need(same_bits(zc[s], np.load(PACKAGE/f'calibration/z_s{s}.npy', allow_pickle=False)), f'Calibration z_s{s} recomputation differs')
compare = pkg.comparison_indices(train_rows)
zg = pkg.golden(model, train_x, compare)
for s in range(11):
    need(same_bits(zg[s], np.load(PACKAGE/f'golden/z_s{s}.npy', allow_pickle=False)), f'Golden z_s{s} recomputation differs')
need(same_bits(zg[10], np.load(PACKAGE/'golden/reference_logits.npy', allow_pickle=False)), 'Reference logits recomputation differ')
out['recompute'] = {'device': 'cpu', 'calibration_z_s0_s9_bitwise': True, 'check_set_z_s0_s10_bitwise': True,
                    'reference_logits_bitwise': True, 'check_set': '20 DS1 train beats, rule ' + pkg.COMPARISON_RULE}
out['status'] = 'PACKAGE_A_DELIVERY_CHECK_PASS_NO_DS2'
print(json.dumps(out, indent=2))
