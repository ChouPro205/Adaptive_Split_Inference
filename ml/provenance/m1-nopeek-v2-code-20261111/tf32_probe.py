# TF32 probe for protocol v2 training.precision. Random input (seeded), package A deployment checkpoint,
# deterministic settings as the runner; compares CUDA with CPU for logits (eval) and for the CE gradient
# (eval mode, so dropout does not differ between devices). Reads no MITDB file and trains nothing.
# Usage from the worktree root: python -B <this file> default|off   (off = the runner's set_precision)
import os
import sys

os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
sys.path.insert(0, 'ml/scripts')
sys.path.insert(0, 'ml/src')
import torch  # noqa: E402
import package_m1_v4_a as pkg  # noqa: E402
import nopeek_m1_v2 as nop  # noqa: E402

mode = sys.argv[1]
torch.use_deterministic_algorithms(True)
torch.backends.cudnn.benchmark = False
torch.backends.cudnn.deterministic = True
if mode == 'off':
    nop.set_precision({'cudnn_allow_tf32': False, 'matmul_allow_tf32': False})
elif mode != 'default':
    raise SystemExit('mode must be default or off')
_, deployment, _, config = pkg.locked()
x = torch.randn(512, 1, 360, generator=torch.Generator().manual_seed(1))
y = torch.randint(0, 5, (512,), generator=torch.Generator().manual_seed(2))
out = {}
for dev in ('cpu', 'cuda'):
    model = pkg.load_model(deployment, config).to(dev)
    with torch.no_grad():
        logits = model(x.to(dev)).cpu()
    loss = torch.nn.functional.cross_entropy(model(x.to(dev)), y.to(dev))
    loss.backward()
    out[dev] = (logits, torch.cat([p.grad.flatten().cpu() for p in model.parameters()]))
logit_diff = (out['cpu'][0]-out['cuda'][0]).abs().max().item()
grad_diff = ((out['cpu'][1]-out['cuda'][1]).abs().max()/out['cpu'][1].abs().max()).item()
same = bool((out['cpu'][0].argmax(1) == out['cuda'][0].argmax(1)).all())
print(f"mode={mode} torch={torch.__version__} device={torch.cuda.get_device_name(0)} "
      f"cudnn.allow_tf32={torch.backends.cudnn.allow_tf32} cuda.matmul.allow_tf32={torch.backends.cuda.matmul.allow_tf32} "
      f"cudnn.conv.fp32_precision={torch.backends.cudnn.conv.fp32_precision} cuda.matmul.fp32_precision={torch.backends.cuda.matmul.fp32_precision}")
print(f"  max|logit cpu-cuda| = {logit_diff:.3e}; max relative CE-gradient difference = {grad_diff:.3e}; argmax identical = {same}")
