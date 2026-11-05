"""Negative contract tests only; synthetic fixtures do not establish M1 data completion."""
import unittest

import mitdb_ds1ds2_m1_v3 as p
import m1_validation_policy_v3 as v
import m1_metrics_v3 as metrics


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.config=p.read_json(p.ROOT/'ml/configs/mitdb_ds1ds2_m1_v3.json')
        val=set(p.DS1[:5])
        self.rows=[{'record_id':r,'patient_id':p.patient(r),'split':
            ('val' if r in val else 'train') if r in p.DS1 else
            'test_main' if r in p.DS2 else 'auxiliary_only' if r=='202' else 'excluded'}
            for r in sorted(p.DS1+p.DS2+['202']+p.PACED)]

    def row(self,r):
        return next(x for x in self.rows if x['record_id']==r)

    def test_valid_config(self):
        p.validate_config(self.config)

    def test_ds2_train(self):
        self.row('100')['split']='train'
        with self.assertRaisesRegex(ValueError,'DS1'):
            p.split_records(self.rows)

    def test_ds2_validation(self):
        self.row('100')['split']='val'
        with self.assertRaisesRegex(ValueError,'DS1'):
            p.split_records(self.rows)

    def test_202_train(self):
        self.row('202')['split']='train'
        with self.assertRaisesRegex(ValueError,'DS1'):
            p.split_records(self.rows)

    def test_202_main(self):
        self.row('202')['split']='test_main'
        with self.assertRaisesRegex(ValueError,'DS2/202'):
            p.split_records(self.rows)

    def test_paced_validation(self):
        self.row('107')['split']='val'
        with self.assertRaisesRegex(ValueError,'DS1'):
            p.split_records(self.rows)

    def test_forged_shared_patient(self):
        self.row('202')['patient_id']='P202'
        with self.assertRaisesRegex(ValueError,'Canonical patient'):
            p.split_records(self.rows)

    def test_patient_overlap_even_with_distinct_record_ids(self):
        self.row('100')['patient_id']=self.row('101')['patient_id']
        with self.assertRaisesRegex(ValueError,'Canonical patient'):
            p.split_records(self.rows)

    def test_duplicate_record(self):
        self.rows[-1]=dict(self.rows[0])
        with self.assertRaisesRegex(ValueError,'Duplicate/missing'):
            p.split_records(self.rows)

    def test_wrong_record_config(self):
        self.config['ds1'][0]='100'
        with self.assertRaisesRegex(ValueError,'Canonical record'):
            p.validate_config(self.config)

    def test_patient_group_config_removed(self):
        self.config['shared_patient_groups']=[]
        with self.assertRaisesRegex(ValueError,'Patient identity'):
            p.validate_config(self.config)

    def test_202_calibration(self):
        with self.assertRaisesRegex(ValueError,'Forbidden calibration'):
            p.validate_calibration(['202'],p.split_records(self.rows))

    def test_validation_forbidden_for_calibration_and_fast_finetune(self):
        groups=p.split_records(self.rows)
        with self.assertRaisesRegex(ValueError,'Forbidden calibration'):
            p.validate_calibration([groups['val'][0]],groups)

    def test_ds2_calibration(self):
        with self.assertRaisesRegex(ValueError,'Forbidden calibration'):
            p.validate_calibration(['100'],p.split_records(self.rows))

    def test_val_normalization(self):
        groups=p.split_records(self.rows)
        n={'fit_split':'val','fit_records':groups['val'],'fit_patient_ids':[], 'mean':0,'std':1}
        with self.assertRaisesRegex(ValueError,'Normalization fit records'):
            p.norm_binding(n,groups)

    def test_norm_extra_202(self):
        groups=p.split_records(self.rows)
        n={'fit_split':'train','fit_records':groups['train']+['202'],'mean':0,'std':1}
        with self.assertRaisesRegex(ValueError,'Normalization fit records'):
            p.norm_binding(n,groups)

    def test_zero_std(self):
        groups=p.split_records(self.rows)
        n={'fit_split':'train','fit_records':groups['train'],
           'fit_patient_ids':[p.patient(r) for r in groups['train']],'mean':0,'std':0}
        with self.assertRaisesRegex(ValueError,'Invalid normalization'):
            p.norm_binding(n,groups)

    def test_seed_reproducible_and_ds2_not_used(self):
        counts={r:[100,10,20,5,0] for r in p.DS1}
        first=p.choose_validation(self.config,counts)
        counts['202']=[0,10**9,10**9,0,0]
        self.assertEqual(first,p.choose_validation(self.config,counts))

    def test_no_feasible_split_fails(self):
        counts={r:[100,10,20,5,0] for r in p.DS1}
        # Exercise the explicit no-candidate branch without inventing data evidence.
        from unittest.mock import patch
        with patch.object(p.itertools,'combinations',return_value=iter([])):
            with self.assertRaisesRegex(ValueError,'No feasible'):
                p.choose_validation(self.config,counts)

    def test_rr_rejected(self):
        self.config['rr_features']=True
        with self.assertRaisesRegex(ValueError,'Input/preprocessing'):
            p.validate_config(self.config)

    def test_window_rejected(self):
        self.config['window']['left']=179
        with self.assertRaisesRegex(ValueError,'Input/preprocessing'):
            p.validate_config(self.config)


class PolicyTests(unittest.TestCase):
    def test_F_floor_switch_threshold_50(self):
        for count,floor in [(49,10),(50,20)]:
            rows=[{'size':4,'records':('101','106','108','109'),'counts':[1,1,1,20,0],
                   'F20':True,'F10':True} for _ in range(count)]
            _,draw=v.choose(rows,'F_floor',20261030)
            self.assertEqual(draw['selected_F_floor'],floor)

    def test_F_20_and_10_integer_boundaries(self):
        for floor in [10,20]:
            self.assertTrue(v.feasible([100,100,100,floor,0],[1000]*5,'F'+str(floor)))
            self.assertFalse(v.feasible([100,100,100,floor-1,0],[1000]*5,'F'+str(floor)))
    def test_integer_lower_boundary(self):
        self.assertTrue(v.feasible([100,100,100,0,0],[1000]*5,'B'))
        self.assertFalse(v.feasible([100,99,100,0,0],[1000]*5,'B'))
        self.assertFalse(v.feasible([100,100,99,0,0],[1000]*5,'B'))

    def test_upper_each_class(self):
        for k in range(4):
            row=[100,100,100,1,0]
            row[k]=300
            self.assertTrue(v.feasible(row,[1000]*5,'B'))
            row[k]=301
            self.assertFalse(v.feasible(row,[1000]*5,'B'))

    def test_B_does_not_add_F_lower(self):
        self.assertTrue(v.feasible([100,100,100,0,0],[1000]*5,'B'))
        self.assertFalse(v.feasible([100,100,100,0,0],[1000]*5,'C'))
        self.assertFalse(v.feasible([100,100,100,1,0],[1000]*5,'A'))

    def test_prefer_four_even_if_five_present(self):
        counts={r:[100,10,20,5,0] for r in p.DS1}
        rows,summary=v.enumerate_combinations(counts,p.DS1)
        chosen,draw=v.choose(rows,'F_floor',20261030)
        self.assertEqual(len(chosen),4)
        self.assertEqual(draw['records'],4)
        self.assertGreater(summary['sizes']['5']['policies']['B']['feasible'],0)

    def test_actual_five_fallback_fixture(self):
        counts={r:[1,0,0,0,0] for r in p.DS1}
        for r in p.DS1[:5]:
            counts[r]=[1,1,1,2,0]
        counts[p.DS1[5]]=[95,45,45,100,0]
        rows,summary=v.enumerate_combinations(counts,p.DS1)
        self.assertEqual(summary['sizes']['4']['policies']['B']['feasible'],0)
        chosen,draw=v.choose(rows,'F_floor',20261030)
        self.assertEqual(chosen,p.DS1[:5])
        self.assertEqual(draw['records'],5)

    def test_infeasible_no_relaxation(self):
        counts={r:[1,0,0,0,0] for r in p.DS1}
        counts[p.DS1[0]]=[1,100,100,0,0]
        rows,_=v.enumerate_combinations(counts,p.DS1)
        with self.assertRaisesRegex(ValueError,'No feasible'):
            v.choose(rows,'F_floor',20261030)

    def test_all_rows_enumerated_once(self):
        counts={r:[100,10,20,5,0] for r in p.DS1}
        rows,_=v.enumerate_combinations(counts,p.DS1)
        self.assertEqual(len(rows),7315+26334)
        self.assertEqual(len({r['records'] for r in rows}),len(rows))

    def test_sampling_is_order_and_platform_independent(self):
        self.assertEqual(v.sample_index(1775,20261030),v.sample_index(1775,20261030))
        counts={r:[100,10,20,5,0] for r in reversed(p.DS1)}
        a,_=v.enumerate_combinations(counts,p.DS1)
        b,_=v.enumerate_combinations(counts,list(reversed(p.DS1)))
        self.assertEqual(a,b)


class MetricTests(unittest.TestCase):
    def test_fixed_K_cannot_drop_absent_F(self):
        with self.assertRaisesRegex(ValueError,'Fixed NSVF'):
            metrics.freeze_validation_policy([0,1,2,4])
    def test_S_predicted_Q_penalizes_S(self):
        y=[0,1,2,3,4]
        policy=metrics.freeze_validation_policy(y)
        good=metrics.validation_metrics(y,y,policy)
        bad=metrics.validation_metrics(y,[0,4,2,3,4],policy)
        self.assertEqual(bad['recall'][1],0)
        self.assertEqual(bad['f1'][1],0)
        self.assertLess(bad['validation_macro_f1_K_fixed'],good['validation_macro_f1_K_fixed'])

    def test_Q_predicted_N_creates_false_positive(self):
        y=[0,1,2,3,4]
        m=metrics.validation_metrics(y,[0,1,2,3,0],metrics.freeze_validation_policy(y))
        self.assertEqual(m['precision'][0],.5)
        self.assertAlmostEqual(m['f1'][0],2/3)
        self.assertEqual(m['samples'],5)

    def test_supported_class_never_predicted_is_zero(self):
        y=[0,1,2,3,4]
        m=metrics.validation_metrics(y,[0,0,0,0,0],metrics.freeze_validation_policy(y))
        self.assertEqual(m['f1'][1:4],[0,0,0])
        self.assertEqual(m['validation_K'],['N','S','V','F'])

    def test_K_true_support_not_predictions(self):
        y=[0,1,2,3,4]
        policy=metrics.freeze_validation_policy(y)
        a=metrics.validation_metrics(y,[3,3,3,3,3],policy)
        b=metrics.validation_metrics(y,[4,4,4,4,4],policy)
        self.assertEqual(a['validation_K'],['N','S','V','F'])
        self.assertEqual(a['validation_K'],b['validation_K'])
        self.assertNotIn('Q',a['validation_K'])

    def test_forged_K_rejected(self):
        y=[0,1,2,3,4]
        policy=metrics.freeze_validation_policy(y)
        policy['K_indices']=[0,1,2]
        with self.assertRaisesRegex(ValueError,'Fixed validation K'):
            metrics.validation_metrics(y,y,policy)

    def test_no_drop_Q_no_four_output_argmax(self):
        result=metrics.all_metrics([0,1,2,3,4],[4,4,4,4,4])
        self.assertEqual(result['predicted_counts'],[0,0,0,0,5])
        self.assertEqual(result['samples'],5)

    def test_ds2_names_fixed4_and_fixed5_synthetic_only(self):
        result=metrics.ds2_reporting_metrics([0,1,2,3,4],[0,1,2,3,0])
        self.assertAlmostEqual(result['macro_f1_NSVF_fixed4'],(2/3+3)/4)
        self.assertAlmostEqual(result['macro_f1_NSVFQ_fixed5'],(2/3+3)/5)

    def test_baseline_perfect_pass(self):
        self.assertEqual(metrics.baseline_gates([0,1,2],[0,1,2])['package_A_gate'],'PASS')

    def test_V_blocks_A(self):
        self.assertFalse(metrics.baseline_gates([0,1,2],[0,1,0])['V'])
        self.assertEqual(metrics.baseline_gates([0,1,2],[0,1,0])['package_A_gate'],'BLOCKED')

    def test_S_exception_needs_authority(self):
        result=metrics.baseline_gates([0]*80+[1]*5+[2]*15,[0]*85+[2]*15)
        self.assertEqual(result['package_A_gate'],'S_ONLY_EXCEPTION_REQUIRES_RECORDED_AUTHORITY')

    def test_N_ten_pp_boundary(self):
        y=[0]*60+[1]*20+[2]*20
        self.assertTrue(metrics.baseline_gates(y,[0]*70+[1]*10+[2]*20)['N'])
        self.assertFalse(metrics.baseline_gates(y,[0]*71+[1]*9+[2]*20)['N'])


if __name__=='__main__':
    unittest.main(verbosity=2)
