"""Biased sample distance correlation R_n (not R_n squared), alpha=1.

Székely, Rizzo & Bakirov (2007), definitions 4/5, equations 2.8--2.10:
https://arxiv.org/abs/0803.4101
NoPeek (2020), equation 1 and appendix B: https://arxiv.org/abs/2008.09161
"""
from __future__ import annotations

import torch


def distance_correlation(x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    """Return scalar R_n for paired observations on axis 0.

    Flatten *only* non-batch axes: ECG [B,1,360] -> [B,360],
    activation [B,C,L] -> [B,C*L], or NC -> [B,C]. Scalars, B<2,
    empty features, nonfinite values, unequal batches/devices/dtypes and
    dtypes other than float32/float64 are rejected. B=2 is mathematically
    valid but uninformative (R=1 for two nonconstant observations).

    Uses Euclidean distances, ordinary double centering, all n*n entries
    including the diagonal (biased V-statistic, not U-centering). Returns
    zero with zero gradients when either distance variance is zero.
    At a numerically nonpositive covariance choose the zero subgradient.
    Else differentiable almost everywhere; no activation detachment.
    First-order autograd is supported; higher derivatives are not promised.
    Cost O(B^2 * (Dx+Dy)), storage O(B^2) plus input/backward buffers.
    """
    for name, value in (("x", x), ("y", y)):
        if not isinstance(value, torch.Tensor):
            raise TypeError(f"{name} must be a torch.Tensor")
        if value.layout != torch.strided or value.dtype not in (torch.float32, torch.float64):
            raise TypeError(f"{name} must be dense float32/float64")
        if value.ndim < 1 or value.shape[0] < 2 or value.numel() == 0:
            raise ValueError(f"{name} requires B>=2 and nonempty features")
        if not bool(torch.isfinite(value).all()):
            raise ValueError(f"{name} must be finite")
    if x.shape[0] != y.shape[0] or x.device != y.device or x.dtype != y.dtype:
        raise ValueError("Paired inputs require equal B, device and dtype")

    def centered_distances(value):
        flat = value.reshape(value.shape[0], -1)
        # One positive scalar per input, not per channel/sample: R is scale
        # invariant. Detaching this scalar does not change the exact derivative
        # of R. Rescale before distances to avoid squared-distance overflow.
        scale = flat.detach().abs().amax()
        flat = flat / torch.where(scale > 0, scale, torch.ones_like(scale))
        # Direct cdist has exact zero diagonal and finite first gradients at
        # duplicate points, unlike a naive sqrt(sum((xi-xj)**2)) backward.
        distances = torch.cdist(flat, flat, p=2, compute_mode="donot_use_mm_for_euclid_dist")
        return (distances - distances.mean(0, keepdim=True)
                - distances.mean(1, keepdim=True) + distances.mean())

    a, b = centered_distances(x), centered_distances(y)
    norm_a, norm_b = torch.linalg.vector_norm(a), torch.linalg.vector_norm(b)
    zero = (x * 0).sum() + (y * 0).sum()
    if bool(norm_a == 0) or bool(norm_b == 0):
        return zero
    # sum(AB)/sqrt(sum(A²)*sum(B²)) = Vn²(X,Y)/sqrt(Vn²(X)*Vn²(Y)).
    # Separate normalization avoids multiplying tiny/large variances.
    r_squared = ((a / norm_a) * (b / norm_b)).sum().clamp(0, 1)
    if bool(r_squared <= 0):
        return zero
    return r_squared.sqrt()
