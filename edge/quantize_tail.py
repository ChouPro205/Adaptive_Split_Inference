#!/usr/bin/env python3
"""
quantize_tail.py - Lượng tử hóa mô hình Tail cho điểm cắt s bằng vai_q_pytorch (Vitis AI)
Thuộc phạm vi SV2 (FPGA / Edge) - Tuần 4
Dự án: Adaptive Split Inference
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional, List
import shutil
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


def build_tail_model(s: int, checkpoint_path: Optional[Path] = None) -> nn.Module:
    """Tạo mô hình Tail cho điểm cắt s từ mô hình baseline MitdbBaselineCNN."""
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

    full_model = MitdbBaselineCNN(dropout=0.0).eval()

    if checkpoint_path and checkpoint_path.exists():
        ckpt = torch.load(checkpoint_path, map_location="cpu")
        if "state_dict" in ckpt:
            state_dict = ckpt["state_dict"]
        elif "model_state_dict" in ckpt:
            state_dict = ckpt["model_state_dict"]
        else:
            state_dict = ckpt
        full_model.load_state_dict(state_dict)
        print(f"[INFO] Đã nạp checkpoint: {checkpoint_path}")
    else:
        print("[WARN] Không tìm thấy checkpoint; khởi tạo trọng số ngẫu nhiên cho mục đích kiểm thử.")

    # Tách module theo CUTS
    leaves = [(n, m) for n, m in full_model.named_modules() if n and not list(m.children())]
    modules = [m for _, m in leaves]
    tail_ops = modules[CUTS[s]:]
    tail_model = nn.Sequential(*tail_ops).eval()
    return tail_model


def get_calibration_data(s: int, calib_data_path: Optional[Path] = None, num_samples: int = 20) -> List[torch.Tensor]:
    """Lấy dữ liệu calibration: dùng golden z_s nếu có, hoặc sinh ngẫu nhiên đúng shape."""
    shape = SHAPES[s]
    if calib_data_path and calib_data_path.exists():
        data = np.load(calib_data_path)
        print(f"[INFO] Nạp dữ liệu calibration từ {calib_data_path}, shape: {data.shape}")
        samples = [torch.from_numpy(data[i:i+1]).float() for i in range(min(len(data), num_samples))]
        return samples

    # Tìm file golden mặc định từ ml/artifacts
    default_golden = REPO_ROOT / f"ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/golden/z_s{s}.npy"
    if default_golden.exists():
        data = np.load(default_golden)
        print(f"[INFO] Nạp dữ liệu calibration từ {default_golden}")
        return [torch.from_numpy(data[i:i+1]).float() for i in range(min(len(data), num_samples))]

    print(f"[INFO] Sinh {num_samples} mẫu giả lập có phân phối chuẩn cho s={s} shape={shape}")
    torch.manual_seed(42)
    return [torch.randn(*shape) for _ in range(num_samples)]


def run_quantization(s: int, quant_mode: str, output_dir: Path, checkpoint_path: Optional[Path],
                     calib_data_path: Optional[Path], dry_run: bool = False):
    """Thực hiện lượng tử hóa tail_s bằng vai_q_pytorch (hoặc dry-run)."""
    shape = SHAPES[s]
    dummy_input = torch.randn(*shape)
    tail_model = build_tail_model(s, checkpoint_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"--- BẮT ĐẦU LƯỢNG TỬ HÓA: s={s}, mode={quant_mode}, input_shape={shape} ---")

    if dry_run:
        print("[DRY-RUN] Kiểm tra tính hợp lệ của mô hình tail và tensor đầu vào:")
        with torch.no_grad():
            out = tail_model(dummy_input)
            print(f"[DRY-RUN] Forward pass thành công! Đầu ra logits: {tuple(out.shape)}")
        mock_xmodel = output_dir / f"tail_{s}_int.xmodel"
        mock_xmodel.write_text(f"Mock XIR for split {s}\n")
        print(f"[DRY-RUN] Đã tạo mock file lượng tử hóa: {mock_xmodel}")
        return 0

    try:
        from pytorch_nndct.apis import torch_quantizer  # type: ignore
    except ImportError:
        print("[ERROR] Không tìm thấy thư viện 'pytorch_nndct' (vai_q_pytorch).", file=sys.stderr)
        print("[ERROR] Hãy chạy script này bên trong Vitis-AI Docker container!", file=sys.stderr)
        print("[HINT] Hoặc dùng cờ --dry-run để kiểm thử cấu trúc trên môi trường host.", file=sys.stderr)
        return 1

    device = torch.device("cpu")
    quantizer = torch_quantizer(
        quant_mode=quant_mode,
        module=tail_model,
        input_args=(dummy_input,),
        output_dir=str(output_dir),
        device=device
    )
    quant_model = quantizer.quant_model

    # Chạy forward pass cho tập calibration
    calib_samples = get_calibration_data(s, calib_data_path)
    with torch.no_grad():
        for i, sample in enumerate(calib_samples):
            _ = quant_model(sample)

    if quant_mode == "calib":
        quantizer.export_quant_config()
        print(f"[SUCCESS] Đã xuất cấu hình lượng tử hóa cho s={s} tại {output_dir}")
    elif quant_mode == "test":
        quantizer.export_xmodel(output_dir=str(output_dir), deploy_check=False)
        gen_xmodel = output_dir / "Sequential_int.xmodel"
        target_xmodel = output_dir / f"tail_{s}_int.xmodel"
        if gen_xmodel.exists() and not target_xmodel.exists():
            shutil.copyfile(gen_xmodel, target_xmodel)
        print(f"[SUCCESS] Đã xuất XIR model cho s={s} tại {output_dir}")

    return 0


def main():
    parser = argparse.ArgumentParser(description="Lượng tử hóa Tail Model cho Vitis AI DPU (SV2 Week 4)")
    parser.add_argument("-s", "--split", type=int, required=True, choices=range(10),
                        help="Điểm cắt s (0..9)")
    parser.add_argument("--quant_mode", choices=["calib", "test"], default="test",
                        help="Chế độ lượng tử hóa (calib để hiệu chỉnh dải động, test để xuất file _int.xmodel)")
    parser.add_argument("--output_dir", type=Path, default=None,
                        help="Thư mục lưu kết quả lượng tử hóa")
    parser.add_argument("--checkpoint", type=Path, default=None,
                        help="Đường dẫn file PyTorch checkpoint .pt")
    parser.add_argument("--calib_data", type=Path, default=None,
                        help="Đường dẫn file .npy chứa các tensor kích hoạt golden")
    parser.add_argument("--dry-run", action="store_true",
                        help="Kiểm tra tương thích mô hình và forward pass mà không gọi vai_q_pytorch")

    args = parser.parse_args()

    s = args.split
    output_dir = args.output_dir or (REPO_ROOT / f"edge/build/quantized/s{s}")
    checkpoint_path = args.checkpoint
    if not checkpoint_path:
        default_ckpt = REPO_ROOT / "ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/model/checkpoint.pt"
        if default_ckpt.exists():
            checkpoint_path = default_ckpt

    exit_code = run_quantization(
        s=s,
        quant_mode=args.quant_mode,
        output_dir=output_dir,
        checkpoint_path=checkpoint_path,
        calib_data_path=args.calib_data,
        dry_run=args.dry_run
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
