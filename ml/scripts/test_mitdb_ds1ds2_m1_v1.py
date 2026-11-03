"""Negative contract tests only; synthetic fixtures do not establish M1 data completion."""
import unittest

import mitdb_ds1ds2_m1_v1 as p


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.config=p.read_json(p.ROOT/'ml/configs/mitdb_ds1ds2_m1_v1.json')
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
        counts={r:[100,10,20,0,0] for r in p.DS1}
        first=p.choose_validation(self.config,counts)
        counts['202']=[0,10**9,10**9,0,0]
        self.assertEqual(first,p.choose_validation(self.config,counts))

    def test_no_feasible_split_fails(self):
        counts={r:[100,10,20,0,0] for r in p.DS1}
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


if __name__=='__main__':
    unittest.main(verbosity=2)
