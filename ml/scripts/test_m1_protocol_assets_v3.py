"""Real-metadata protocol preflight tests; no training or model predictions."""
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import prepare_m1_protocol_assets_v3 as assets
import m1_metrics_v3 as metrics

ROOT=assets.ROOT
PROTOCOL=ROOT/'ml/configs/mitdb_m1_baseline_protocol_v3.json'
ARRAYS=ROOT/'ml/data/processed/mitdb-ds1ds2-m1-v3-r2'
OUTPUT=ROOT/'ml/manifests/mitdb-m1-protocol-assets-v3'


class ProtocolAssetTests(unittest.TestCase):
    def test_candidate_cannot_claim_locked(self):
        p=assets.read(PROTOCOL)
        p['authority']['locked']=True
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'protocol.json'
            path.write_bytes(assets.json_bytes(p))
            with self.assertRaisesRegex(ValueError,'cannot claim lock'):
                assets.inputs(path,ARRAYS)

    def test_changed_data_binding_rejected(self):
        p=assets.read(PROTOCOL)
        p['data']['sha256_bindings']['manifest']='0'*64
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'protocol.json'
            path.write_bytes(assets.json_bytes(p))
            with self.assertRaisesRegex(ValueError,'Protocol data hash differs'):
                assets.inputs(path,ARRAYS)

    def test_fixed_subset_and_reproducibility(self):
        a=assets.assets(PROTOCOL,ARRAYS)
        b=assets.assets(PROTOCOL,ARRAYS)
        self.assertEqual(a,b)
        rows=list(csv.DictReader(io.StringIO(a['dcor-validation-subset.csv'].decode())))
        self.assertEqual(len(rows),512)
        self.assertEqual(len({r['validation_row_index'] for r in rows}),512)
        self.assertEqual({r['record_id'] for r in rows},{'118','119','205','223'})
        self.assertEqual([r['rank_sha256'] for r in rows],sorted(r['rank_sha256'] for r in rows))

    def test_weights_use_train_counts_and_caps(self):
        value=json.loads(assets.assets(PROTOCOL,ARRAYS)['class-weights-by-trial.json'])
        self.assertEqual(value['train_samples'],41472)
        self.assertEqual(value['train_counts'],[37519,772,2784,389,8])
        self.assertEqual(value['weights']['C0']['Q'],10)
        self.assertEqual(value['weights']['C2']['Q'],50)
        self.assertIsNone(value['weights']['C4'])
        self.assertAlmostEqual(value['weights']['C2']['F'],41472/(5*389))

    def test_trial_register_eighteen_unstarted_slots(self):
        content=assets.assets(PROTOCOL,ARRAYS)['baseline-trial-register.csv']
        rows=list(csv.DictReader(io.StringIO(content.decode())))
        self.assertEqual(len(rows),18)
        self.assertEqual(len({(r['trial'],r['seed']) for r in rows}),18)
        self.assertEqual({r['state'] for r in rows},{'PLANNED_NOT_STARTED'})

    def test_rebound_subset_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'assets'
            shutil.copytree(OUTPUT,target)
            path=target/'dcor-validation-subset.csv'
            rows=list(csv.DictReader(io.StringIO(path.read_text(encoding='utf-8'))))
            rows[0]['record_id']='100'
            path.write_bytes(assets.csv_bytes(list(rows[0]),rows))
            manifest=assets.read(target/'assets-manifest.json')
            manifest['artifacts'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
            (target/'assets-manifest.json').write_bytes(assets.json_bytes(manifest))
            run=subprocess.run([sys.executable,'-B',str(ROOT/'ml/scripts/prepare_m1_protocol_assets_v3.py'),
                'verify','--protocol',str(PROTOCOL),'--artifacts',str(ARRAYS),'--output',str(target)],
                capture_output=True,text=True)
            self.assertNotEqual(run.returncode,0)
            self.assertIn('Protocol asset identity/hash binding differs',run.stderr)

    def test_current_N_and_V_gates_reject_always_N(self):
        # Analytic validation-only diagnostic; no model execution or DS2 predictions.
        p=assets.read(PROTOCOL)
        m=assets.read(ROOT/p['data']['manifest'])
        counts=m['splits']['val']['counts']
        y=[k for k,n in enumerate(counts) for _ in range(n)]
        result=metrics.baseline_gates(y,[0]*len(y))
        self.assertLess(counts[0]/len(y),.9)
        self.assertFalse(result['N'])
        self.assertFalse(result['V'])
        self.assertEqual(result['package_A_gate'],'BLOCKED')


if __name__=='__main__':
    unittest.main(verbosity=2)
