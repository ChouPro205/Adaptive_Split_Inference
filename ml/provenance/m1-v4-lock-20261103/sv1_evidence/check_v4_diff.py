# SV1 review of M1 v4: protocol key diff v3->v4, slot config diff, plan binding, sampler draws on real train labels.
# Usage: python -I -B check_v4_diff.py <v3 package dir> <v4 package dir> <processed arrays dir>
import sys, json, glob, os
from fractions import Fraction
import numpy as np, torch
v3, v4, arrays = sys.argv[1:4]
a = json.load(open(v3+'/ml/configs/mitdb_m1_baseline_protocol_v3.json', encoding='utf-8'))
b = json.load(open(v4+'/ml/configs/mitdb_m1_baseline_protocol_v4.json', encoding='utf-8'))
changed = []
def walk(x, y, p=''):
    if isinstance(x, dict) and isinstance(y, dict):
        for k in sorted(set(x) | set(y)):
            if k not in x: changed.append('ADD '+p+'/'+k)
            elif k not in y: changed.append('DEL '+p+'/'+k)
            else: walk(x[k], y[k], p+'/'+k)
    elif x != y: changed.append('CHG '+p)
walk(a, b)
print('protocol changes v3->v4:'); [print('  '+c) for c in changed]
g3, g4 = v3+'/ml/manifests/mitdb-baseline-grid-v3', v4+'/ml/manifests/mitdb-baseline-grid-v4'
allowed = {'protocol_sha256','sources_sha256','sampler_policy','sampler_expected_draws_per_epoch','sampler_per_class_sample_weight'}
bad = []
for f in sorted(glob.glob(g4+'/C*.json')):
    n = os.path.basename(f); x = json.load(open(g3+'/'+n)); y = json.load(open(f))
    extra = {k for k in set(x) | set(y) if x.get(k) != y.get(k)} - allowed
    if extra: bad.append((n, sorted(extra)))
print('18 slot configs change only', sorted(allowed), ':', not bad, bad)
p3 = json.load(open(g3+'/plan-manifest.json'))['binding']; p4 = json.load(open(g4+'/plan-manifest.json'))['binding']
print('plan data_files/runtime/source_head unchanged:', all(p3[k] == p4[k] for k in ('data_files','runtime','source_head')))
y = np.load(arrays+'/train_y.npy'); cnt = np.bincount(y, minlength=5); N = int(cnt.sum())
pq = Fraction(int(cnt[4]), N); pk = (1-pq)/4
print('train counts', cnt.tolist(), 'N', N, '| expected draws K', float(N*pk), 'Q', float(N*pq))
c4 = json.load(open(g4+'/C4-seed20261030.json'))
mine = [float(pk/int(n)) for n in cnt[:4]] + [float(pq/int(cnt[4]))]
print('config per-class weights equal independent value:', np.allclose(mine, c4['sampler_per_class_sample_weight'], rtol=1e-15, atol=0))
w = torch.tensor([mine[c] for c in y.tolist()], dtype=torch.double); tot = np.zeros(5)
for ep in range(40):
    idx = list(torch.utils.data.WeightedRandomSampler(w, N, replacement=True, generator=torch.Generator().manual_seed(20261030+ep)))
    tot += np.bincount(y[idx], minlength=5)
print('own sampler, mean draws/epoch over 40 epochs:', (tot/40).round(1).tolist())
