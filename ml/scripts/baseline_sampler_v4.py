"""K-balanced sampler for C4/C5: N/S/V/F equal expected draws, Q at natural train frequency."""
from fractions import Fraction

import numpy as np

CLASSES=['N','S','V','F','Q']
K_INDICES=(0,1,2,3)
Q_INDEX=4
POLICY_ID='K_BALANCED_NSVF_Q_NATURAL_V4'


def need(ok,message):
    if not ok: raise ValueError(message)


def check_counts(counts):
    need(len(counts)==5 and all(type(n) is int and n>=0 for n in counts),'Expected five integer train counts')
    need(all(counts[k]>0 for k in K_INDICES),'Every K class needs train support')
    return sum(counts)


def class_probabilities(counts):
    # Exact per-draw class probabilities: Q keeps n_Q/N_train, the rest splits equally over K.
    total=check_counts(counts)
    q=Fraction(counts[Q_INDEX],total)
    return [(1-q)/len(K_INDICES)]*len(K_INDICES)+[q]


def expected_draws(counts):
    total=check_counts(counts)
    return [total*p for p in class_probabilities(counts)]


def per_class_sample_weight(counts):
    # Probability of drawing one given sample of class c; zero only for an empty Q class.
    return [float(p/n) if n else 0. for p,n in zip(class_probabilities(counts),counts)]


def sample_weights(labels,counts):
    y=np.asarray(labels)
    need(y.ndim==1 and np.issubdtype(y.dtype,np.integer) and bool(((y>=0)&(y<5)).all()),'Expected five-class integer labels')
    need(np.bincount(y,minlength=5).tolist()==list(counts),'Sampler counts differ from train labels')
    return np.asarray(per_class_sample_weight(counts),dtype=np.float64)[y]


def build_sampler(labels,counts,generator):
    # Lazy import keeps preflight free of torch.
    import torch
    from torch.utils.data import WeightedRandomSampler
    weights=torch.from_numpy(sample_weights(labels,counts))
    return WeightedRandomSampler(weights,check_counts(counts),replacement=True,generator=generator)


def plan_fields(counts):
    return {'sampler_policy':POLICY_ID,
            'sampler_expected_draws_per_epoch':[str(v) for v in expected_draws(counts)],
            'sampler_per_class_sample_weight':per_class_sample_weight(counts)}
