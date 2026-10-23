#!/usr/bin/env python3
"""
quantize_tail.py - Lượng tử hóa mô hình Tail cho điểm cắt s bằng vai_q_pytorch (Vitis AI)
Thuộc phạm vi SV2 (FPGA / Edge) - Tuần 4
Dự án: Adaptive Split Inference

Luồng nghiệm thu chỉ chạy với checkpoint đã duyệt (kiểm SHA-256) và dữ liệu
calibration lấy từ split train/val đã xác thực; không bao giờ dùng tập test.
Trọng số/dữ liệu ngẫu nhiên chỉ có qua --synthetic-demo và kết quả bị đánh dấu
SYNTHETIC, không dùng làm minh chứng nghiệm thu.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import inspect
import shutil
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from torch import nn

# Thêm đường dẫn root để import mô hình và cấu hình dùng chung
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Định nghĩa hình dạng tensor z_s theo hợp đồng kỹ thuật sv3-sv2-week3-fp32-v1
SHAPES = {
    0: (1, 1, 360),    # NCL - raw input
    1: (1, 16, 360),   # NCL - sau ReLU1
    2: (1, 16, 180),   # NCL - sau Pool2
    3: (1, 32, 180),   # NCL - sau ReLU3
    4: (1, 32, 90),    # NCL - sau Pool4
    5: (1, 48, 90),    # NCL - sau ReLU5
    6: (1, 48, 45),    # NCL - sau Pool6
    7: (1, 64, 45),    # NCL - sau ReLU7
    8: (1, 64, 22),    # NCL - sau Pool8
    9: (1, 32),        # NC  - sau ReLU(Linear1)
}

CUTS = (0, 2, 5, 7, 10, 12, 15, 17, 20, 24, 25)

# Checkpoint của approved registry (contracts/sv3_week5_approved_registry_v2.json).
CHECKPOINT_SHA256 = "9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90"
DEFAULT_CHECKPOINT = REPO_ROOT / "ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/model/checkpoint.pt"
PROCESSED_DIR = REPO_ROOT / "ml/data/processed/mitdb"
# Hash raw của dữ liệu processed đã chuẩn hóa, được track trong repo.
DATASET_MANIFEST = REPO_ROOT / "ml/results/week5/dataset_manifest.json"
CALIBRATION_SPLITS = ("train", "val")  # Tập test frozen chỉ dùng để đánh giá.
DEFAULT_CALIBRATION_SAMPLES = 1000
PROVENANCE_NAME = "quantize_provenance.json"
SYNTHETIC_MARKER = "SYNTHETIC_NOT_FOR_ACCEPTANCE"
HYDRATE_HINT = "Hydrate the frozen assets first (ml/docs/week5_delivery_v2.md, setup_week5_delivery_v2.py)."


class TailQuantizationError(Exception):
    """Thiếu hoặc sai đầu vào; không tạo artifact."""


def fix_vai25_conv1d_padding() -> list:
    """Bridge known 1D padding getter/setter mismatches, in this process only."""
    try:
        from pytorch_nndct.parse.torch_op_def import _TorchConv1d, TorchMaxPool1d
    except ImportError:
        return []
    fixes = []
    for cls in (_TorchConv1d, TorchMaxPool1d):
        padding = cls.padding
        name = "vai25_scalar_padding:" + cls.__name__
        if getattr(padding.fset, "_asi_scalar_padding", False):
            fixes.append(name)
            continue
        try:
            source = inspect.getsource(padding.fset)
        except (OSError, TypeError):
            continue
        if "[value[0], value[0]]" not in source:
            continue

        def set_padding(op, value, original_setter=padding.fset):
            original_setter(op, (value,) if isinstance(value, int) else value)

        set_padding._asi_scalar_padding = True
        cls.padding = property(padding.fget, set_padding, padding.fdel, padding.__doc__)
        print("[COMPAT] %s: accept scalar padding when cloning deploy graph" % cls.__name__)
        fixes.append(name)
    return fixes


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def baseline_model() -> nn.Module:
    try:
        from ml.src.mitdb_baseline_model import MitdbBaselineCNN
    except ImportError:
        # Fallback inline nếu chạy hoàn toàn độc lập trong container
        class MitdbBaselineCNN(nn.Module):
            CHANNELS = (16, 16, 32, 32, 48, 48, 64, 64)
            def __init__(self, dropout: float = 0.2):
                super().__init__()
                layers = []
                c = 1
                for idx, out_c in enumerate(self.CHANNELS):
                    layers.extend([nn.Conv1d(c, out_c, kernel_size=5, padding=2), nn.ReLU()])
                    if idx % 2 == 1:
                        layers.append(nn.MaxPool1d(kernel_size=2))
                    c = out_c
                self.features = nn.Sequential(*layers)
                self.classifier = nn.Sequential(
                    nn.Flatten(), nn.Dropout(dropout),
                    nn.Linear(64 * 22, 32), nn.ReLU(), nn.Linear(32, 5)
                )
    return MitdbBaselineCNN(dropout=0.0).eval()


def load_full_model(checkpoint_path: Optional[Path], synthetic: bool = False) -> nn.Module:
    """Nạp checkpoint đã duyệt; chỉ khởi tạo ngẫu nhiên khi synthetic được chọn tường minh."""
    if synthetic:
        torch.manual_seed(42)
        print("[SYNTHETIC] Trọng số ngẫu nhiên; kết quả không dùng làm minh chứng nghiệm thu.")
        return baseline_model()
    if checkpoint_path is None or not Path(checkpoint_path).is_file():
        raise TailQuantizationError(f"Checkpoint not found: {checkpoint_path}. {HYDRATE_HINT}")
    actual = sha256(checkpoint_path)
    if actual != CHECKPOINT_SHA256:
        raise TailQuantizationError(f"Checkpoint SHA-256 {actual} differs from the approved {CHECKPOINT_SHA256}")
    try:
        ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    except TypeError:  # Older PyTorch in the Vitis AI container; the file hash is already verified.
        ckpt = torch.load(checkpoint_path, map_location="cpu")
    full_model = baseline_model()
    state_dict = ckpt.get("state_dict", ckpt.get("model_state_dict", ckpt)) if isinstance(ckpt, dict) else ckpt
    full_model.load_state_dict(state_dict, strict=True)
    print(f"[INFO] Đã nạp checkpoint: {checkpoint_path}")
    return full_model.eval()


def split_modules(full_model: nn.Module, s: int) -> tuple[nn.Sequential, nn.Sequential]:
    """Tách head/tail theo CUTS, cùng quy ước số phép toán với firmware SV1."""
    leaves = [m for n, m in full_model.named_modules() if n and not list(m.children())]
    if len(leaves) != CUTS[-1]:
        raise TailQuantizationError(f"Expected {CUTS[-1]} leaf operations, found {len(leaves)}")
    # Vitis AI 2.5 rewrites Flatten(end_dim=-1) to end_dim=3, assuming
    # a 4D image tensor. This contract has NCL tensors (3D) before Flatten.
    # Make the equivalent positive axis explicit without changing frozen ML code.
    leaves = [nn.Flatten(start_dim=1, end_dim=2)
              if isinstance(m, nn.Flatten) and m.start_dim == 1 and m.end_dim == -1
              else m for m in leaves]
    return nn.Sequential(*leaves[:CUTS[s]]).eval(), nn.Sequential(*leaves[CUTS[s]:]).eval()


def build_tail_model(s: int, checkpoint_path: Optional[Path] = None, synthetic: bool = False) -> nn.Module:
    """Tạo mô hình Tail cho điểm cắt s từ mô hình baseline MitdbBaselineCNN."""
    return split_modules(load_full_model(checkpoint_path, synthetic), s)[1]


def calibration_inputs(split: str, count: int) -> tuple[np.ndarray, dict]:
    """Chọn đều count mẫu đã chuẩn hóa từ split train/val, sau khi kiểm hash raw."""
    if split not in CALIBRATION_SPLITS:
        raise TailQuantizationError(f"Calibration split must be one of {CALIBRATION_SPLITS}; the test split is evaluation-only")
    if count < 1:
        raise TailQuantizationError("Calibration sample count must be positive")
    path = PROCESSED_DIR / f"{split}_X.npy"
    if not path.is_file() or not DATASET_MANIFEST.is_file():
        raise TailQuantizationError(f"Missing processed calibration data {path}. {HYDRATE_HINT}")
    expected = json.loads(DATASET_MANIFEST.read_text(encoding="utf-8"))["identifiers"]["processed_artifacts"][path.name]
    actual = sha256(path)
    if actual != expected:
        raise TailQuantizationError(f"{path.name} SHA-256 {actual} differs from the frozen {expected}")
    x = np.load(path, allow_pickle=False)
    if x.ndim != 2 or x.shape[1] != 360 or x.dtype != np.float32 or not np.isfinite(x).all():
        raise TailQuantizationError(f"{path.name} is not finite normalized FP32 (N,360)")
    indices = np.unique(np.linspace(0, len(x) - 1, min(count, len(x))).round().astype(np.int64))
    source = {"type": "processed_split", "split": split, "path": path.relative_to(REPO_ROOT).as_posix(),
              "sha256": actual, "samples": int(len(indices)),
              "indices_sha256": hashlib.sha256(indices.astype("<i8").tobytes()).hexdigest()}
    return np.ascontiguousarray(x[indices][:, None, :]), source


def head_activations(full_model: nn.Module, s: int, x: np.ndarray, batch: int = 256) -> np.ndarray:
    head = split_modules(full_model, s)[0]
    outputs = []
    with torch.no_grad():
        for start in range(0, len(x), batch):
            outputs.append(head(torch.from_numpy(x[start:start + batch])).numpy())
    z = np.concatenate(outputs).astype(np.float32)
    if z.shape[1:] != SHAPES[s][1:]:
        raise TailQuantizationError(f"Head output {z.shape[1:]} differs from split {s} shape {SHAPES[s][1:]}")
    return z


def get_calibration_data(s: int, full_model: nn.Module, calib_split: str, calib_samples: int,
                         calib_data_path: Optional[Path] = None, calib_data_split: Optional[str] = None,
                         synthetic: bool = False) -> tuple[list, dict]:
    """Trả về các tensor z_s một mẫu (batch 1) và mô tả nguồn calibration."""
    shape = SHAPES[s]
    if synthetic:
        torch.manual_seed(42)
        print(f"[SYNTHETIC] Sinh {calib_samples} mẫu chuẩn tắc cho s={s} shape={shape}")
        return [torch.randn(*shape) for _ in range(calib_samples)], {"type": "synthetic_normal", "samples": calib_samples}
    if calib_data_path is not None:
        if calib_data_split not in CALIBRATION_SPLITS:
            raise TailQuantizationError("--calib_data requires --calib-data-split train|val declaring its source split")
        if not calib_data_path.is_file():
            raise TailQuantizationError(f"Calibration file not found: {calib_data_path}")
        data = np.load(calib_data_path, allow_pickle=False)
        if data.ndim != len(shape) or data.shape[1:] != shape[1:] or not np.isfinite(data).all():
            raise TailQuantizationError(f"Calibration data must be finite {('N',) + shape[1:]}, got {data.shape}")
        data = data[:calib_samples].astype(np.float32)
        source = {"type": "provided_activations", "declared_split": calib_data_split,
                  "path": str(calib_data_path), "sha256": sha256(calib_data_path), "samples": int(len(data))}
    else:
        x, source = calibration_inputs(calib_split, calib_samples)
        data = head_activations(full_model, s, x)
    print(f"[INFO] Calibration s={s}: {source}")
    return [torch.from_numpy(data[i:i + 1].copy()) for i in range(len(data))], source


def write_provenance(output_dir: Path, record: dict) -> None:
    (output_dir / PROVENANCE_NAME).write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_quantization(s: int, quant_mode: str, output_dir: Path, checkpoint_path: Optional[Path],
                     calib_data_path: Optional[Path] = None, dry_run: bool = False,
                     calib_split: str = "train", calib_samples: int = DEFAULT_CALIBRATION_SAMPLES,
                     calib_data_split: Optional[str] = None, synthetic: bool = False) -> int:
    """Thực hiện lượng tử hóa tail_s bằng vai_q_pytorch (hoặc dry-run)."""
    shape = SHAPES[s]
    marker = output_dir / SYNTHETIC_MARKER
    if marker.exists() and not synthetic:
        raise TailQuantizationError(f"{output_dir} holds synthetic results; use a fresh output directory")
    full_model = load_full_model(checkpoint_path, synthetic)
    tail_model = split_modules(full_model, s)[1]
    calib_samples_list, calibration = get_calibration_data(s, full_model, calib_split, calib_samples,
                                                           calib_data_path, calib_data_split, synthetic)
    output_dir.mkdir(parents=True, exist_ok=True)
    if synthetic:
        marker.write_text("Random weights/calibration; never acceptance evidence.\n", encoding="utf-8")
    record = {"split_point_s": s, "quant_mode": quant_mode, "input_shape": list(shape),
              "checkpoint": None if synthetic else {"path": str(checkpoint_path), "sha256": CHECKPOINT_SHA256},
              "calibration": calibration, "synthetic": synthetic, "acceptance_evidence": not synthetic,
              "dry_run": dry_run, "dpu_validation": "NOT_RUN"}

    print(f"--- BẮT ĐẦU LƯỢNG TỬ HÓA: s={s}, mode={quant_mode}, input_shape={shape} ---")

    if dry_run:
        with torch.no_grad():
            out = tail_model(calib_samples_list[0])
        print(f"[DRY-RUN] Forward pass thành công! Đầu ra logits: {tuple(out.shape)}; không tạo xmodel.")
        write_provenance(output_dir, {**record, "dry_run_logits_shape": list(out.shape)})
        return 0

    try:
        from pytorch_nndct.apis import torch_quantizer  # type: ignore
    except ImportError:
        print("[ERROR] Không tìm thấy thư viện 'pytorch_nndct' (vai_q_pytorch).", file=sys.stderr)
        print("[ERROR] Hãy chạy script này bên trong Vitis-AI Docker container!", file=sys.stderr)
        print("[HINT] Hoặc dùng cờ --dry-run để kiểm thử cấu trúc trên môi trường host.", file=sys.stderr)
        return 1

    record["compatibility_fixes"] = fix_vai25_conv1d_padding()
    quantizer = torch_quantizer(
        quant_mode=quant_mode,
        module=tail_model,
        input_args=(calib_samples_list[0],),
        output_dir=str(output_dir),
        device=torch.device("cpu")
    )
    quant_model = quantizer.quant_model

    # Chạy forward pass cho tập calibration
    with torch.no_grad():
        for sample in calib_samples_list:
            _ = quant_model(sample)

    if quant_mode == "calib":
        quantizer.export_quant_config()
        print(f"[SUCCESS] Đã xuất cấu hình lượng tử hóa cho s={s} tại {output_dir}")
    elif quant_mode == "test":
        quantizer.export_xmodel(output_dir=str(output_dir), deploy_check=False)
        gen_xmodel = output_dir / "Sequential_int.xmodel"
        target_xmodel = output_dir / (f"tail_{s}_SYNTHETIC_int.xmodel" if synthetic else f"tail_{s}_int.xmodel")
        if gen_xmodel.exists():
            # Luôn thay bản sao cũ để xmodel khớp checkpoint/calibration của lần chạy này.
            shutil.copyfile(gen_xmodel, target_xmodel)
            record["xmodel_sha256"] = sha256(target_xmodel)
        print(f"[SUCCESS] Đã xuất XIR model cho s={s} tại {output_dir}")
    write_provenance(output_dir, record)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Lượng tử hóa Tail Model cho Vitis AI DPU (SV2 Week 4)")
    parser.add_argument("-s", "--split", type=int, required=True, choices=range(10),
                        help="Điểm cắt s (0..9)")
    parser.add_argument("--quant_mode", choices=["calib", "test"], default="test",
                        help="Chế độ lượng tử hóa (calib để hiệu chỉnh dải động, test để xuất file _int.xmodel)")
    parser.add_argument("--output_dir", type=Path, required=True,
                        help="Thư mục lưu kết quả lượng tử hóa")
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT,
                        help="Checkpoint PyTorch đã duyệt (kiểm SHA-256)")
    parser.add_argument("--calib-split", choices=CALIBRATION_SPLITS, default="train",
                        help="Split processed dùng sinh activation calibration (không bao giờ là test)")
    parser.add_argument("--calib-samples", type=int, default=DEFAULT_CALIBRATION_SAMPLES,
                        help="Số mẫu calibration, chọn đều và tất định trong split")
    parser.add_argument("--calib_data", type=Path, default=None,
                        help="File .npy activation z_s tự cung cấp (thay cho --calib-split)")
    parser.add_argument("--calib-data-split", choices=CALIBRATION_SPLITS, default=None,
                        help="Khai báo split nguồn của --calib_data")
    parser.add_argument("--synthetic-demo", action="store_true",
                        help="Trọng số và calibration ngẫu nhiên, đánh dấu SYNTHETIC, không dùng nghiệm thu")
    parser.add_argument("--dry-run", action="store_true",
                        help="Kiểm tra checkpoint, calibration và forward pass; không gọi vai_q_pytorch, không tạo xmodel")

    args = parser.parse_args()

    s = args.split
    output_dir = args.output_dir
    try:
        exit_code = run_quantization(
            s=s, quant_mode=args.quant_mode, output_dir=output_dir,
            checkpoint_path=args.checkpoint, calib_data_path=args.calib_data,
            dry_run=args.dry_run, calib_split=args.calib_split, calib_samples=args.calib_samples,
            calib_data_split=args.calib_data_split, synthetic=args.synthetic_demo)
    except TailQuantizationError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        exit_code = 2
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
