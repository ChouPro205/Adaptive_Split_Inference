"""Failure-mode tests for independent audit and frozen-test output acceptance.

All backend outputs here are SYNTHETIC_TEST_ONLY, never hardware evidence.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np
from review_week7_sv2 import ROOT, CHECKPOINT, CLASSES, audit, sha, write
from week7_dpu_accuracy import evaluate, metrics, csv_write
from evaluate_week5_v2 import strict_accuracy_gate


class AccuracyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.ref=self.root/'reference'
        self.ref.mkdir()
        self.samples=[{'sample_id':f'test-only-{i}', 'true_label':i%5} for i in range(8544)]
        csv_write(self.ref/'samples.csv', ['sample_id','true_label'], self.samples)
        logits=np.zeros((8544,5),dtype='<f4')
        logits[np.arange(8544),np.arange(8544)%5]=2
        np.save(self.ref/'reference_fp32.npy',logits,allow_pickle=False)
        np.save(self.ref/'reference_wire_fp32tail_s2.npy',logits,allow_pickle=False)
        write(self.ref/'manifest.json', {'schema':'sv3-week7-dpu-reference/1', 'count':8544,
             'checkpoint_sha256':CHECKPOINT,'class_order':CLASSES,'split_points':[2],
             'expected_xmodel_sha256':{'2':'a'*64},
             'expected_calibration':{'split':'val','sample_ids':['validation-only'],
                                      'samples_csv_sha256':'d'*64,'golden_sha256':{'2':'d'*64}},
             'files':{p.name:{'sha256':sha(p),'size_bytes':p.stat().st_size} for p in self.ref.iterdir()}})
        self.data={'schema':'sv3-week7-dpu-output/1','class_order':CLASSES,
                   'scope':'SYNTHETIC_TEST_ONLY', 'reference_manifest_sha256':sha(self.ref/'manifest.json'),
                   'checkpoint_sha256':CHECKPOINT,'backend':'kv260_root_cpu_dpu',
                   'provenance':{'board_id':'SYNTHETIC_TEST_ONLY','runtime_version':'test', 'source_commit':'1'*40,
                     'runner_sha256':'b'*64,'quantization_policy':'test', 'cpu_plugins_sha256':{'test.so':'c'*64},
                     'calibration':{'split':'val','sample_ids':['validation-only'], 'artifacts_sha256':{'test':'d'*64},
                                    'samples_csv_sha256':'d'*64,'golden_sha256':{'2':'d'*64}},
                     'models':{'2':{'xmodel_sha256':'a'*64,'quant_info_sha256':'e'*64,'compile_log_sha256':'f'*64}}},
                   'rows':[{'sample_id':r['sample_id'],'split_point_s':2,'status':'OK','logits':z.tolist()}
                           for r,z in zip(self.samples,logits)]}

    def tearDown(self):
        self.tmp.cleanup()

    def run_data(self,data=None):
        p=self.root/'outputs.json'
        p.write_text(json.dumps(self.data if data is None else data),encoding='utf-8')
        return evaluate(self.ref,p)['results'][0]

    def test_reordered_ids_match_full_metrics_and_errors(self):
        self.data['rows'].reverse()
        r=self.run_data()
        self.assertEqual(r['status'],'PASS_ACCURACY_GATE')
        self.assertEqual(r['correct_dpu'],8544)
        self.assertEqual(r['logit_errors_vs_full_fp32']['max_abs'],0)
        self.assertEqual(r['valid_output_metrics']['confusion_matrix_true_rows_predicted_columns'][0][0],1709)

    def test_missing_and_failed_never_pass_or_shrink_denominator(self):
        self.data['rows'].pop()
        self.data['rows'][0].update(status='INFERENCE_FAILED',logits=None)
        r=self.run_data()
        self.assertEqual(r['status'],'INCOMPLETE_NO_ACCEPTANCE')
        self.assertEqual(len(r['missing_ids']),1)
        self.assertEqual(len(r['failures']),1)
        self.assertTrue(r['strict_count_gate_met'])
        self.assertEqual(r['correct_dpu'],8542)
        self.assertAlmostEqual(r['accuracy_all_8544_percent'],100*8542/8544)

    def test_invalid_logits_are_failures(self):
        self.data['rows'][0]['logits']=[0,1,2,3]
        self.data['rows'][1]['logits']=[True,0,0,0,0]
        self.data['rows'][2]['logits']=[1e100,0,0,0,0]
        r=self.run_data()
        self.assertEqual(len(r['failures']),3)
        self.assertEqual(r['status'],'INCOMPLETE_NO_ACCEPTANCE')

    def test_accuracy_strict_boundary_counts(self):
        self.assertFalse(strict_accuracy_gate(10000,9950,10000))
        self.assertTrue(strict_accuracy_gate(10000,9951,10000))
        # 42 mistakes pass at 8544; 43 do not.
        for lost,expected in ((42,'PASS_ACCURACY_GATE'),(43,'FAIL_ACCURACY_GATE')):
            data=copy.deepcopy(self.data)
            for r in data['rows'][:lost]:
                true=self.samples[int(r['sample_id'].split('-')[-1])]['true_label']
                r['logits']=[2 if c==(true+1)%5 else 0 for c in range(5)]
            self.assertEqual(self.run_data(data)['status'],expected)

    def test_duplicate_unknown_id_and_split_rejected(self):
        for kind in ('duplicate','unknown','split'):
            data=copy.deepcopy(self.data)
            if kind=='duplicate':data['rows'].append(data['rows'][0])
            if kind=='unknown':data['rows'][0]['sample_id']='unknown'
            if kind=='split':data['rows'][0]['split_point_s']=5
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.run_data(data)

    def test_wrong_manifest_model_class_or_calibration_rejected(self):
        for kind in ('manifest','model','class','calibration','provenance'):
            data=copy.deepcopy(self.data)
            if kind=='manifest':data['reference_manifest_sha256']='0'*64
            if kind=='model':data['provenance']['models']['2']['xmodel_sha256']='0'*64
            if kind=='class':data['class_order'].reverse()
            if kind=='calibration':data['provenance']['calibration']['sample_ids']=['test-only-0']
            if kind=='provenance':del data['provenance']['board_id']
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.run_data(data)

    def test_reference_tamper_rejected(self):
        (self.ref/'samples.csv').write_text('changed',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Reference file differs'):self.run_data()

    def test_tie_policy_and_absent_classes(self):
        for r in self.data['rows']:r['logits']=[0]*5
        result=self.run_data()
        self.assertEqual(result['correct_dpu'],1709)
        self.assertEqual(result['valid_output_metrics']['per_class'][1]['precision'],0)
        m=metrics(np.array([],dtype=int),np.array([],dtype=int))
        self.assertIsNone(m['accuracy_percent'])


class AuditTests(unittest.TestCase):
    def test_duplicate_and_numeric_tamper_even_with_rehashed_export(self):
        for kind in ('duplicate','numeric'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                for week in (5,6,7):
                    shutil.copytree(ROOT/f'results/week{week}/edge',root/f'results/week{week}/edge')
                old='ml/provenance/week6-p1-20261016/final'
                (root/old).mkdir(parents=True)
                for p in ('p1_50.json','output_50.json'):shutil.copyfile(ROOT/old/p,root/old/p)
                p=root/'results/week7/edge/cases.json'
                data=json.loads(p.read_text())
                if kind=='duplicate':data['rows'][1]=data['rows'][0]
                else:data['rows'][0]['logits'][0]+=1
                p.write_text(json.dumps(data))
                sums=root/'results/week7/edge/sha256sum_export.txt'
                lines=sums.read_text().splitlines()
                sums.write_text('\n'.join(sha(p)+'  cases.json' if l.endswith('cases.json') else l for l in lines)+'\n')
                with self.assertRaisesRegex(ValueError,'Duplicate or missing|Recomputed comparison differs'):
                    audit(root)


if __name__=='__main__':
    unittest.main(verbosity=2)
