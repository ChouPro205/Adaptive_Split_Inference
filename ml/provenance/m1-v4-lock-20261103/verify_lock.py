# Checks the lock with the v4 runner's own require_authorization (the gate `run` applies before any
# data/model/optimizer). Does not load arrays, build a model or train. Run from the worktree root.
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, 'ml/scripts')
from baseline_grid_v4 import require_authorization
lock = Path('ml/provenance/m1-v4-lock-20261103/m1_baseline_v4_lock_and_train_authorization.json')
protocol = Path('ml/configs/mitdb_m1_baseline_protocol_v4.json')
plan = Path('ml/manifests/mitdb-baseline-grid-v4/plan-manifest.json')
a = require_authorization(lock, protocol, plan)
print('require_authorization: ACCEPTED', a['protocol_sha256'], a['plan_manifest_sha256'])
with tempfile.TemporaryDirectory() as d:
    bad = Path(d)/'bad.json'; bad.write_text(json.dumps(dict(a, allow_training=False)), encoding='utf-8')
    try: require_authorization(bad, protocol, plan); print('negative control: ACCEPTED (unexpected)'); sys.exit(1)
    except Exception as e: print('negative control allow_training=false: REJECTED', type(e).__name__)
