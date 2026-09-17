# Week 1 environment reproducibility

The authoritative version constraints are in `configs/environment.json`.
`src/check_env.py` compares the running Python and package versions to those
constraints and performs CPU and, when available/requested, CUDA tensor checks.
It exits non-zero on missing packages, version mismatches, CUDA runtime
mismatches, or failed tensor operations.

Verified environment:

- Python 3.11.9;
- Windows NT 10.0 build 26200 with PowerShell;
- PyTorch 2.14.0+cu130 and CUDA runtime 13.0;
- NVIDIA GeForce RTX 5060;
- NumPy 2.4.6, pandas 3.0.5, SciPy 1.17.1, Matplotlib 3.11.2,
  WFDB 4.3.1, and scikit-learn 1.9.1.

Linux commands are provided in `ml/README.md`, but a team Linux machine has not
yet produced a committed verification manifest. This limitation is explicit;
the Windows run is the current reproducibility evidence.

CPU installations use `requirements-cpu.txt`. GPU installations use the
tested `requirements-gpu-cu130.txt`. A GPU installation also needs an NVIDIA
driver new enough for the wheel's CUDA 13.0 runtime; the project does not pin a
machine-specific driver package.
