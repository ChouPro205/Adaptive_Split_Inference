"""Week 2 pre-training tests; no generated run artifact is required."""

from __future__ import annotations

import unittest

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from mitdb_baseline_model import MitdbBaselineCNN, architecture_metadata
from mitdb_week2_data import load_week1_splits
from train_mitdb_baseline import evaluate
from week1_common import configured_path, load_config


class Week2BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config, cls.identifiers, cls.arrays = load_week1_splits()

    def test_model_shape_and_footprint(self) -> None:
        model = MitdbBaselineCNN()
        x = torch.from_numpy(self.arrays["train"][0][:4]).unsqueeze(1)
        self.assertEqual(tuple(model(x).shape), (4, 5))
        _, settings = load_config("mitdb_week2_baseline.json")
        info = architecture_metadata(model, settings["candidate_name"])
        self.assertEqual(info["candidate"], settings["candidate_name"])
        self.assertGreaterEqual(info["layer_count"], 8)
        self.assertLessEqual(info["layer_count"], 12)
        self.assertLess(info["trainable_parameters"], 250_000)
        self.assertLess(info["fp32_parameter_bytes"], 1_000_000)
        self.assertEqual(info["fp32_parameter_bytes"], info["total_parameters"] * 4)

    def test_frozen_split_identity_and_classes(self) -> None:
        self.assertEqual(self.config["classes"], {"N": 0, "S": 1, "V": 2, "F": 3, "Q": 4})
        root = configured_path(self.config, "processed_dir")
        for split in ("train", "val", "test"):
            x, y = self.arrays[split]
            self.assertTrue(np.array_equal(x[:4], np.load(root / f"{split}_X.npy")[:4]))
            self.assertTrue(np.array_equal(y, np.load(root / f"{split}_y.npy")))
            self.assertEqual(len(y), self.config["processed_dataset"][split]["samples"])
        self.assertEqual(self.config["normalization"]["fit_split"], "train")

    def test_evaluation_does_not_update_model(self) -> None:
        model = MitdbBaselineCNN(dropout=0.0)
        x, y = self.arrays["train"]
        loader = DataLoader(TensorDataset(torch.from_numpy(x[:8]).unsqueeze(1),
                                          torch.from_numpy(y[:8])), batch_size=4)
        before = {name: value.clone() for name, value in model.state_dict().items()}
        result = evaluate(model, loader, nn.CrossEntropyLoss(), torch.device("cpu"),
                          self.config["classes"])
        self.assertEqual(sum(row["support"] for row in result["per_class"].values()), 8)
        self.assertFalse(model.training)
        for name, value in model.state_dict().items():
            self.assertTrue(torch.equal(value, before[name]))
            self.assertIsNone(dict(model.named_parameters())[name].grad)


if __name__ == "__main__":
    unittest.main()
