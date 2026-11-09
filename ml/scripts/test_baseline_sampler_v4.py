"""K-balanced sampler on synthetic labels only; no MITDB arrays, model, optimizer or fit."""
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest

import numpy as np
import torch

import baseline_sampler_v4 as sampler

ROOT=Path(__file__).resolve().parents[2]
MANIFEST=ROOT/'ml/manifests/mitdb-ds1ds2-m1-v3-r2/processed-manifest.json'
# Train counts are read from the bound manifest; labels below are synthetic arrays with those counts.
TRAIN_COUNTS=json.loads(MANIFEST.read_text(encoding='utf-8'))['splits']['train']['counts']
SEED=20261030


def synthetic_labels(counts):
    return np.repeat(np.arange(5,dtype=np.int64),counts)


def draws(counts,seed):
    generator=torch.Generator().manual_seed(seed)
    return list(sampler.build_sampler(synthetic_labels(counts),counts,generator))


def class_draws(counts,indices):
    return np.bincount(synthetic_labels(counts)[indices],minlength=5).tolist()


class ExpectedDrawTests(unittest.TestCase):
    def test_bound_train_counts(self):
        self.assertEqual(TRAIN_COUNTS,[37519,772,2784,389,8])

    def test_exact_expected_draws_K_equal_Q_natural(self):
        expected=sampler.expected_draws(TRAIN_COUNTS)
        self.assertEqual(expected,[10366,10366,10366,10366,8])
        self.assertEqual(sum(expected),sum(TRAIN_COUNTS))

    def test_probabilities_sum_to_one_and_K_ratio(self):
        counts=[1000,7,30,3,5]
        p=sampler.class_probabilities(counts)
        self.assertEqual(sum(p),1)
        self.assertEqual(len(set(p[:4])),1)
        self.assertEqual(p[0],Fraction(1040,4*1045))
        self.assertEqual(sampler.expected_draws(counts)[:4],[Fraction(1040,4)]*4)

    def test_Q_natural_frequency_not_fifth(self):
        p=sampler.class_probabilities(TRAIN_COUNTS)
        self.assertEqual(p[4],Fraction(8,sum(TRAIN_COUNTS)))
        self.assertNotEqual(p[4],Fraction(1,5))
        # Each Q sample keeps the per-draw probability it has under uniform sampling.
        self.assertEqual(sampler.per_class_sample_weight(TRAIN_COUNTS)[4],1/sum(TRAIN_COUNTS))

    def test_Q_absent_gets_no_draws(self):
        self.assertEqual(sampler.expected_draws([10,2,4,4,0]),[5,5,5,5,0])

    def test_rejects_missing_K_class_and_count_mismatch(self):
        with self.assertRaisesRegex(ValueError,'K class'):
            sampler.class_probabilities([10,0,3,3,1])
        with self.assertRaisesRegex(ValueError,'differ'):
            sampler.sample_weights(synthetic_labels([10,2,3,3,1]),[10,2,3,3,2])

    def test_plan_fields_exact_strings(self):
        f=sampler.plan_fields(TRAIN_COUNTS)
        self.assertEqual(f['sampler_policy'],'K_BALANCED_NSVF_Q_NATURAL_V4')
        self.assertEqual(f['sampler_expected_draws_per_epoch'],['10366']*4+['8'])


class DrawTests(unittest.TestCase):
    def test_total_draws_equal_N_train(self):
        indices=draws(TRAIN_COUNTS,SEED)
        self.assertEqual(len(indices),sum(TRAIN_COUNTS))
        self.assertTrue(all(0<=i<sum(TRAIN_COUNTS) for i in indices))

    def test_empirical_class_ratio_within_five_sd(self):
        total=sum(TRAIN_COUNTS)
        observed=class_draws(TRAIN_COUNTS,draws(TRAIN_COUNTS,SEED))
        for count,p in zip(observed,sampler.class_probabilities(TRAIN_COUNTS)):
            sd=math.sqrt(total*float(p)*(1-float(p)))
            self.assertLessEqual(abs(count-total*float(p)),5*sd)

    def test_Q_draws_track_natural_frequency_over_epochs(self):
        epochs=20
        q=sum(class_draws(TRAIN_COUNTS,draws(TRAIN_COUNTS,SEED+e))[4] for e in range(epochs))
        mean=epochs*TRAIN_COUNTS[4];sd=math.sqrt(mean*(1-TRAIN_COUNTS[4]/sum(TRAIN_COUNTS)))
        self.assertLessEqual(abs(q-mean),5*sd)
        self.assertLess(q,epochs*sum(TRAIN_COUNTS)/10)

    def test_same_seed_identical_other_epoch_seed_differs(self):
        self.assertEqual(draws(TRAIN_COUNTS,SEED),draws(TRAIN_COUNTS,SEED))
        self.assertNotEqual(draws(TRAIN_COUNTS,SEED),draws(TRAIN_COUNTS,SEED+1))

    def test_same_seed_identical_across_processes(self):
        code=('import hashlib,sys,numpy as np,torch;sys.path.insert(0,sys.argv[1]);import baseline_sampler_v4 as s;'
              'c=[37519,772,2784,389,8];y=np.repeat(np.arange(5,dtype=np.int64),c);'
              'i=list(s.build_sampler(y,c,torch.Generator().manual_seed(int(sys.argv[2]))));'
              'print(hashlib.sha256(np.asarray(i,dtype="<i8").tobytes()).hexdigest())')
        local=hashlib.sha256(np.asarray(draws(TRAIN_COUNTS,SEED),dtype='<i8').tobytes()).hexdigest()
        for _ in range(2):
            run=subprocess.run([sys.executable,'-B','-c',code,str(Path(__file__).parent),str(SEED)],
                               capture_output=True,text=True,check=True)
            self.assertEqual(run.stdout.strip(),local)


if __name__=='__main__':unittest.main(verbosity=2)
