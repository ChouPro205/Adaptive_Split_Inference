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

import prepare_m1_protocol_assets_v4 as assets
import m1_metrics_v4 as metrics

ROOT=assets.ROOT
PROTOCOL=ROOT/'ml/configs/mitdb_m1_baseline_protocol_v4.json'
PROTOCOL_V3=ROOT/'ml/configs/mitdb_m1_baseline_protocol_v3.json'
ARRAYS=ROOT/'ml/data/processed/mitdb-ds1ds2-m1-v3-r2'
OUTPUT=ROOT/'ml/manifests/mitdb-m1-protocol-assets-v4'
V1_2_SHA='2ddeb08b925a8df18e40a5bff57d14def83b607d1be457b8b25e2ad7d5c9123f'


def rejected(test,mutate,message):
    p=assets.read(PROTOCOL);mutate(p)
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/'protocol.json'
        path.write_bytes(assets.json_bytes(p))
        with test.assertRaisesRegex(ValueError,message):
            assets.inputs(path,ARRAYS)


class ProtocolAssetTests(unittest.TestCase):
    def test_candidate_cannot_claim_locked(self):
        rejected(self,lambda p:p['authority'].update(locked=True),'cannot claim lock')

    def test_changed_data_binding_rejected(self):
        rejected(self,lambda p:p['data']['sha256_bindings'].update(manifest='0'*64),'Protocol data hash differs')

    def test_v3_sampler_or_label_rejected(self):
        rejected(self,lambda p:p['baseline'].update(balanced_sampler_policy_id='PER_CLASS_1_OVER_N_FIVE_CLASS'),'sampler policy')
        rejected(self,lambda p:p['baseline']['gates'].update(S_soft_label='S_ONLY_EXCEPTION'),'soft-gate label')

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

    def test_balanced_sampler_K_expected_draws(self):
        value=json.loads(assets.assets(PROTOCOL,ARRAYS)['class-weights-by-trial.json'])['balanced_samplers']
        for trial in ['C0','C1','C2','C3']:self.assertIsNone(value[trial])
        for trial in ['C4','C5']:
            self.assertEqual(value[trial]['expected_draws_per_epoch'],{'N':'10366','S':'10366','V':'10366','F':'10366','Q':'8'})
            self.assertEqual(value[trial]['per_class_sample_weight']['Q'],1/41472)

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
            run=subprocess.run([sys.executable,'-B',str(ROOT/'ml/scripts/prepare_m1_protocol_assets_v4.py'),
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


class ProtocolV4ContentTests(unittest.TestCase):
    def setUp(self):
        self.p=assets.read(PROTOCOL);self.v3=assets.read(PROTOCOL_V3)

    def test_status_unchanged_not_reviewed_not_locked(self):
        self.assertEqual(self.p['status'],self.v3['status'])
        self.assertEqual(self.p['authority']['artifact_review'],'NOT_REVIEWED')
        self.assertIs(self.p['authority']['locked'],False)
        self.assertIs(self.p['authority']['training_permitted'],False)
        self.assertFalse(any(self.p['execution_in_this_round'].values()))

    def test_data_bindings_identical_to_v3(self):
        self.assertEqual(self.p['data'],self.v3['data'])

    def test_source_bindings(self):
        b=self.p['source_bindings']
        self.assertEqual(b['latest_sv1'],self.v3['source_bindings']['latest_sv1'])
        self.assertEqual(b['v2_review'],self.v3['source_bindings']['v2_review'])
        self.assertEqual(b['v1_2_original']['raw_sha256'],V1_2_SHA)
        self.assertEqual(b['v1_2_original']['status'],'FOUND_AND_COMPARED')
        self.assertEqual(b['v1_2_original']['v3_status'],self.v3['source_bindings']['v1_2_original']['status'])
        review=b['sv1_review_v3_20261102']
        self.assertEqual(review['raw_sha256'],'cd9a2c0a3fa848f3f560d286c0a76c8b4e3b6b597f345645e480c2267d0d41e6')
        self.assertIn('not confirmation of any v4 artifact',review['scope'])

    def test_ds2_report_predeclared(self):
        r=self.p['baseline']['ds2_report']
        self.assertEqual(r['seeds'],self.p['baseline']['seeds'])
        self.assertEqual([row['split'] for row in r['rows']],['test_main','test_aux22'])
        self.assertEqual(r['statistics']['sd_ddof'],1)
        self.assertEqual(r['primary_metric'],'macro_f1_NSVF_fixed4')
        self.assertTrue(any(m.startswith('macro_f1_NSVFQ_fixed5') and 'Q beat count' in m for m in r['secondary_metrics']))
        self.assertIn('accuracy',r['secondary_metrics'])
        self.assertEqual(r['literature_comparison']['row'],'test_aux22')
        papers=r['literature_comparison']['papers']
        self.assertEqual(len(papers),6)
        self.assertTrue(all(type(x['uses_RR']) is bool for x in papers))

    def test_deviations_have_reasons(self):
        d=self.p['deviations_from_v1_2']
        self.assertEqual(len(d),3)
        self.assertTrue(all(x['reason'] and x['change'] and x['status'] for x in d))

    def test_code_fault_and_smoke_rules(self):
        b=self.p['baseline']
        self.assertEqual(b['code_fault']['halt_status'],'HALTED_PRE_VALIDATION_CODE_FAULT')
        self.assertIn('not counted as training',b['code_fault']['random_data_smoke'])
        self.assertEqual(b['retry'],self.v3['baseline']['retry'])

    def test_unchanged_rules_equal_v3(self):
        for key in ['metrics','nopeek','quantization','packages','future_research_output',
                    'deferred_teacher_decisions_not_blocking_M1_baseline','execution_in_this_round']:
            self.assertEqual(self.p[key],self.v3[key],key)
        changed={'balanced_sampler','balanced_sampler_policy_id','gates','ds2_report','code_fault'}
        for key in set(self.v3['baseline'])-changed:
            self.assertEqual(self.p['baseline'][key],self.v3['baseline'][key],key)
        for key in ['N','V','S','uses']:
            self.assertEqual(self.p['baseline']['gates'][key],self.v3['baseline']['gates'][key])

    def test_no_absolute_local_paths(self):
        text=PROTOCOL.read_text(encoding='utf-8')
        for marker in [':\\',':/','Users','Downloads']:
            self.assertNotIn(marker,text)


if __name__=='__main__':
    unittest.main(verbosity=2)
