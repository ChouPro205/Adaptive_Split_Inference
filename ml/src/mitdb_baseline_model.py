"""One Week 2 candidate; no architecture freeze is implied."""

from __future__ import annotations

import torch
from torch import nn


class MitdbBaselineCNN(nn.Module):
    """Eight Conv1d and two Linear layers; input (batch, 1, 360)."""

    CHANNELS = (16, 16, 32, 32, 48, 48, 64, 64)
    WEIGHT_LAYER_COUNT = 10  # Eight convolutions plus two dense layers.

    def __init__(self, dropout: float = 0.2) -> None:
        super().__init__()
        layers: list[nn.Module] = []
        channels = 1
        for index, output_channels in enumerate(self.CHANNELS):
            layers.extend((nn.Conv1d(channels, output_channels, kernel_size=5, padding=2), nn.ReLU()))
            if index % 2 == 1:
                layers.append(nn.MaxPool1d(kernel_size=2))
            channels = output_channels
        self.features = nn.Sequential(*layers)
        self.classifier = nn.Sequential(nn.Flatten(), nn.Dropout(dropout),
                                        nn.Linear(64 * 22, 32), nn.ReLU(), nn.Linear(32, 5))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.ndim != 3 or x.shape[1:] != (1, 360):
            raise ValueError(f"Expected ECG batch (N, 1, 360), got {tuple(x.shape)}")
        return self.classifier(self.features(x))


def architecture_metadata(model: MitdbBaselineCNN, candidate_name: str) -> dict:
    """Report every learned layer and the exact counting convention."""
    if not isinstance(candidate_name, str) or not candidate_name:
        raise ValueError("candidate_name must be a non-empty string")
    learned = []
    for name, module in model.named_modules():
        if isinstance(module, (nn.Conv1d, nn.Linear)):
            learned.append({"index": len(learned) + 1, "name": name,
                            "type": type(module).__name__,
                            "input_features": module.in_channels if isinstance(module, nn.Conv1d) else module.in_features,
                            "output_features": module.out_channels if isinstance(module, nn.Conv1d) else module.out_features,
                            "kernel_size": module.kernel_size[0] if isinstance(module, nn.Conv1d) else None,
                            "parameters": sum(p.numel() for p in module.parameters())})
    parameter_count = sum(p.numel() for p in model.parameters())
    trainable_count = sum(p.numel() for p in model.parameters() if p.requires_grad)
    fp32_bytes = parameter_count * 4
    return {"candidate": candidate_name, "input_shape": [1, 360], "logits": 5,
            "layer_count_convention": "Conv1d and Linear modules with learned weights; ReLU, MaxPool1d, Flatten and Dropout are operations, not counted layers",
            "layers": learned, "layer_count": len(learned),
            "total_parameters": parameter_count, "trainable_parameters": trainable_count,
            "fp32_parameter_bytes": fp32_bytes, "fp32_parameter_mib": fp32_bytes / (1024 ** 2)}
