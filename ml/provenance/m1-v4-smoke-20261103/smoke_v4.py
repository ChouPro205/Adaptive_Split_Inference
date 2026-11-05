# Random-data smoke of Ky Anh's v4 fit_slot (both modes). Never reads MITDB arrays.
import sys, json, hashlib, time
from pathlib import Path
tree = Path(sys.argv[1]); work = Path(sys.argv[2])
sys.path.insert(0, str(tree/'ml/scripts'))
import numpy as np
import train_mitdb_baseline_v4 as T
from m1_metrics_v4 import freeze_validation_policy
rng = np.random.default_rng(12345)
fake = work/'fake_arrays'; fake.mkdir(parents=True, exist_ok=True)
def make(split, counts):
    y = np.repeat(np.arange(5, dtype='<i8'), counts); rng.shuffle(y)
    x = rng.standard_normal((len(y), 360)).astype('<f4')
    np.save(fake/f'{split}_X.npy', x, allow_pickle=False); np.save(fake/f'{split}_y.npy', y, allow_pickle=False)
    return y
make('train', [37519, 772, 2784, 389, 8]); yv = make('val', [8322, 172, 1004, 25, 0])
policy = freeze_validation_policy(yv)
plan = tree/'ml/manifests/mitdb-baseline-grid-v4'
out = {}
for slot, run in [('C0-seed20261030', 'a'), ('C4-seed20261030', 'a'), ('C4-seed20261030', 'b')]:
    c = json.load(open(plan/f'{slot}.json', encoding='utf-8')); c['epochs'] = 3
    o = work/f'{slot}-{run}'; o.mkdir(parents=True, exist_ok=False)
    t = time.time(); T.fit_slot(c, fake, o, policy, 'SMOKE', 'SMOKE'); dt = time.time() - t
    s = json.load(open(o/'summary.json')); h = [json.load(open(p)) for p in sorted(o.glob('epoch-*.json'))]
    ident = json.load(open(o/'attempt-identity.json'))
    out[f'{slot}-{run}'] = {'seconds': round(dt, 1), 'device': ident['device_name'], 'epochs': len(h),
        'draws': [e['train_sample_draws'] for e in h], 'reload_exact': s['reload_confusion_exact'],
        'checkpoint_sha256': s['checkpoint_sha256'][:16], 'selected_epoch': s['selected_epoch']}
print(json.dumps(out, indent=1))
(work/"smoke_result.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print('C4 replay identical:', out['C4-seed20261030-a']['checkpoint_sha256'] == out['C4-seed20261030-b']['checkpoint_sha256'])
