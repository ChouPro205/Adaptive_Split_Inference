# Derives per-epoch timing (from output file mtimes), full checkpoint SHA-256 and GPU memory peak
# (from nvidia-smi samples) for the random-data smoke. Reads only the smoke work dir and receipt files.
import sys, json, hashlib
from pathlib import Path
work = Path(sys.argv[1]); prov = Path(sys.argv[2])
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
runs = {}
for name in ['C0-seed20261030-a', 'C4-seed20261030-a', 'C4-seed20261030-b']:
    d = work/name; s = json.loads((d/'summary.json').read_text(encoding='utf-8'))
    t0 = (d/'attempt-identity.json').stat().st_mtime_ns
    marks = [t0] + [p.stat().st_mtime_ns for p in sorted(d.glob('epoch-*.json'))]
    epochs = [json.loads(p.read_text(encoding='utf-8')) for p in sorted(d.glob('epoch-*.json'))]
    ck = d/s['checkpoint']
    runs[name] = {'epoch_seconds_train_plus_validation': [round((b - a)/1e9, 3) for a, b in zip(marks, marks[1:])],
                  'train_sample_draws': [e['train_sample_draws'] for e in epochs],
                  'reload_confusion_exact': s['reload_confusion_exact'], 'selected_epoch': s['selected_epoch'],
                  'checkpoint': s['checkpoint'], 'checkpoint_sha256_summary': s['checkpoint_sha256'],
                  'checkpoint_sha256_recomputed': sha(ck), 'history_sha256': s['history_sha256'],
                  'DS2_evaluated': s['DS2_evaluated'],
                  'attempt_identity': json.loads((d/'attempt-identity.json').read_text(encoding='utf-8'))}
rows = [l.split(', ') for l in (prov/'vram_samples.csv').read_text().splitlines() if l.strip()]
used = [int(r[1]) for r in rows]; baseline = min(used[:5])
draws_ok = all(x == 41472 for r in runs.values() for x in r['train_sample_draws'])
reload_ok = all(r['reload_confusion_exact'] is True for r in runs.values())
a, b = runs['C4-seed20261030-a'], runs['C4-seed20261030-b']
c4_ok = a['checkpoint_sha256_recomputed'] == b['checkpoint_sha256_recomputed'] and \
        all(r['checkpoint_sha256_recomputed'] == r['checkpoint_sha256_summary'] for r in (a, b))
out = {'runs': runs,
       'gpu_memory_nvidia_smi': {'method': 'whole-GPU memory.used sampled every 200 ms (per-process usage is N/A under WDDM)',
           'samples': len(used), 'baseline_MiB_first_samples_min': baseline, 'peak_MiB': max(used),
           'peak_minus_baseline_MiB': max(used) - baseline,
           'note': 'Includes CUDA context and allocator cache; not torch.cuda.max_memory_allocated.'},
       'timing_note': 'Epoch time = mtime(epoch-k.json) - mtime(previous epoch json, or attempt-identity.json for epoch 1); covers train + validation; epoch 1 of the first run includes CUDA warm-up.',
       'criteria': {'draws_41472_every_epoch': draws_ok, 'reload_exact_all_runs': reload_ok,
                    'C4_two_runs_full_checkpoint_sha256_identical': c4_ok}}
print(json.dumps(out, indent=1))
