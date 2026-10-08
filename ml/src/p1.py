"""SV3 P1 Python entry point; reuse the finalized I2/1 API without alterations.

Inputs/outputs are tensor bytes. N=1 INT8 NCL and the active profile are
validated by the authoritative implementation. NC split adapters live in
quantization.py; this module neither quantizes nor manages nonce allocation.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "contracts/i2_ref"))
from i2_reference import I2Error, Profile, descriptor, protect, unprotect

__all__ = ["I2Error", "Profile", "descriptor", "protect", "unprotect"]
