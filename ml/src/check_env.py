"""Version-aware Week 1 environment verification for CPU or CUDA."""

from __future__ import annotations

import argparse
import importlib.metadata
import platform
import sys

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from week1_common import ValidationError, config_sha256, load_config, require, run_cli


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("auto", "cpu", "gpu"), default="auto")
    parser.add_argument("--config", default="environment.json")
    args = parser.parse_args()
    config_path, config = load_config(args.config)
    python_version = Version(platform.python_version())
    require(python_version in SpecifierSet(config["python"]),
            f"Python {python_version} does not satisfy {config['python']}")
    installed: dict[str, str] = {}
    for distribution, specifier in config["packages"].items():
        try:
            version_text = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError as exc:
            raise ValidationError(f"Required package is not installed: {distribution}") from exc
        require(Version(version_text) in SpecifierSet(specifier),
                f"{distribution} {version_text} does not satisfy {specifier}")
        installed[distribution] = version_text

    import torch

    sanity = torch.tensor([1.0, 2.0, 3.0]) * 2
    require(sanity.tolist() == [2.0, 4.0, 6.0], "PyTorch CPU sanity check failed")
    cuda_available = bool(torch.cuda.is_available())
    if args.mode == "gpu":
        require(cuda_available, "GPU mode requested but torch.cuda.is_available() is false")
    if cuda_available:
        profile = config["gpu_profile"]
        require(torch.version.cuda == profile["cuda_runtime"],
                f"CUDA runtime mismatch: expected {profile['cuda_runtime']}, got {torch.version.cuda}")
        local = Version(installed["torch"]).local
        require(local == profile["torch_local_version"],
                f"PyTorch build mismatch: expected +{profile['torch_local_version']}, got +{local}")
        gpu_name = torch.cuda.get_device_name(0)
        gpu_sanity = (sanity.cuda() + 1).cpu().tolist()
        require(gpu_sanity == [3.0, 5.0, 7.0], "PyTorch CUDA sanity check failed")
    else:
        gpu_name = "not used"
    print("WEEK 1 ENVIRONMENT")
    print(f"Python           : {python_version} ({config['python']})")
    print(f"Executable       : {sys.executable}")
    print(f"OS               : {platform.platform()}")
    for package, version in installed.items():
        print(f"{package:17s}: {version} ({config['packages'][package]})")
    print(f"CUDA available   : {cuda_available}")
    print(f"CUDA runtime     : {torch.version.cuda}")
    print(f"GPU              : {gpu_name}")
    print(f"Requested mode   : {args.mode}")
    print(f"Config SHA-256   : {config_sha256(config_path)}")
    print("STATUS: PASS")


if __name__ == "__main__":
    run_cli(main)
