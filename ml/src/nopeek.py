"""Offline NoPeek objective; quantization/P1/transport stay outside this graph."""
from __future__ import annotations

import math
from numbers import Real

import torch
from torch.nn import functional as F

from distance_correlation import distance_correlation


def nopeek_loss(logits, labels, inputs, activations, lambda1):
    """CE + lambda1 * R_n(inputs, activations); report all three scalars.

    At zero lambda the total is the CE tensor itself. dCor is still logged,
    computed without building an unnecessary privacy backward graph.
    """
    if isinstance(lambda1, bool) or not isinstance(lambda1, Real) or not math.isfinite(lambda1) or lambda1 < 0:
        raise ValueError("lambda1 must be finite and nonnegative")
    ce = F.cross_entropy(logits, labels)
    if lambda1 == 0:
        with torch.no_grad():
            dcor = distance_correlation(inputs, activations)
        return ce, {"ce": ce, "dcor": dcor, "total": ce}
    dcor = distance_correlation(inputs, activations)
    total = ce + lambda1 * dcor
    return total, {"ce": ce, "dcor": dcor, "total": total}
