# SV3 → SV2: bàn giao Week 3 FP32 Linux

Trạng thái: source portable đã kiểm thử trên máy tác giả; **SV2 receiver acceptance PENDING**.
Branch: [sv3/fix-week3-sv2-linux-fp32](https://github.com/ChouPro205/Adaptive_Split_Inference/tree/sv3/fix-week3-sv2-linux-fp32).
Commit và PR chính xác được ghi trong README của gói bàn giao
`SV2_WEEK3_LINUX_FP32_HANDOFF_<short-commit>.zip`; checkout commit đó, không chỉ tip mới nhất của branch.

## Lỗi và hợp đồng vẫn được giữ

Verifier cũ yêu cầu recomputation FP32 bitwise với goldens Windows và FAIL tại s=9
trên Ubuntu/WSL đã thử. Diagnostic khoanh vùng sai lệch đầu tiên tại Linear1,
với cùng bytes input/weight/bias; chưa chứng minh kernel, FMA hoặc thứ tự reduction
cụ thể là nguyên nhân duy nhất. Xem [báo cáo fix](sv3_ml_week3_linux_fp32_fix_report.md)
và [review v2](sv3_ml_week3_linux_fp32_review_v2_report.md).

`bitwise-v1` vẫn là mặc định. `portable-fp32-v2` là lựa chọn opt-in mà recipe gọi:

- s=0..8 vẫn bitwise.
- s=9 yêu cầu strict `max_abs < 1e-5`.
- Logits và ONNX yêu cầu strict `max_abs < 1e-3`.
- Inventory, hash, size và bytes package phải chính xác; tolerance chỉ áp dụng
  recomputation, không chấp nhận golden hoặc artifact đã sửa.

Package `mitdb-week3-sv2-fp32-20261001-v1` giữ nguyên 41 file. Manifest SHA-256:

```text
a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6
```

Dùng verifier và recipe trong **repository tại commit bàn giao**. Các script
trong package v1 là snapshot lịch sử: giữ nguyên và không overlay lên `ml/scripts/`.
Model/checkpoint, trọng số, preprocessing, sample IDs/order, split mapping, goldens,
ONNX, manifest, dependency pins và numerical policy không thay đổi khi bàn giao.

## Cách nhận và chạy

README trong ZIP bàn giao điền sẵn commit, link PR và tên ZIP thật. File `.sha256`
đi kèm nằm ngoài ZIP. Trên Ubuntu/WSL, chạy `sha256sum --check <file>.zip.sha256`
trước khi giải nén. Clone vào thư mục riêng, checkout đúng SHA trong README,
rồi giải nén gói vào **gốc checkout** để package nằm tại:

```text
ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/
```

Không cần dataset. Recipe tự tạo venv Linux Python **3.11.9**, cài dependency đã pin
và ghi cả setup/download/authentication vào log. Cần mạng và đủ dung lượng cho
Python, PyTorch CUDA wheel cùng dependencies; kiểm tra dung lượng bằng `df -h`.
Wheel được pin để khớp runtime gate; lượt FP32 này dùng CPU, không chứng nhận DPU.

Từ gốc checkout:

```bash
export ASI_LINUX_ENV_ROOT="$HOME/asi-sv2-week3-fp32-handoff"
export ASI_LINUX_LOG_ROOT="$HOME/asi-sv2-week3-runs/$(date -u +%Y%m%dT%H%M%S%NZ)"
bash ml/scripts/reproduce_week3_sv2_linux.sh
printf 'Logs: %s\n' "$ASI_LINUX_LOG_ROOT"
cat "$ASI_LINUX_LOG_ROOT/recipe.exit_code.txt"
```

Mỗi lượt phải chọn log directory mới; recipe từ chối ghi đè. Nếu venv có sẵn
Python sai phiên bản, chọn `ASI_LINUX_ENV_ROOT` mới thay vì sửa model/tolerance.
`receipt.json` chỉ được cấp khi thành công. Khi FAIL vẫn có command, cwd,
stdout/stderr, exit code và `summary.txt`; gửi lại cả thư mục log dù không có receipt.

Kết quả mong đợi trên môi trường phù hợp: portable verifier **200 comparisons PASS**,
tamper **19** expected rejections, cache **16/16**, numerical policy **8/8**.
Receipt ghi SHA-256 của script `.sh`, source/requirements thực sự dùng và Python
thực tế, cùng authentication artifact trước/sau.

## Bằng chứng và giới hạn nghiệm thu

Review v2 xác minh bytes qua Git checkout và patch áp dụng thật, gồm 125 file
provenance lịch sử và 61 file CRLF. Ngoại lệ `.gitattributes` chỉ áp dụng
`ml/provenance/week3-sv2-linux/** -text`. Receipt cũ vẫn xác thực source cũ;
snapshot recipe cũ nằm trong `review-v2/source-before/`, không gán receipt đó
cho recipe hiện tại. Receipt/log chạy từ commit bàn giao nằm trong ZIP mới,
không ghi đè evidence cũ. Hai báo cáo cũ giữ nguyên mô tả trạng thái lúc review.

Remote main trước bàn giao là `9bce483ddbf3be2ca471e522833352ab18331736`.
Base review `415d53431c81c465784dc08be42b568827a39cff` có thêm hai commit Week 5
chưa trên main. PR fix được dựng từ remote main để chỉ bàn giao Week 3;
12 source/requirements recipe khớp SHA bằng chứng WSL v2, không đưa Week 5 vào PR.

Đã kiểm thử trên Ubuntu 24.04.5 / WSL2 x86_64, Python 3.11.9. Đây là kiểm chứng
FP32 CPU trên máy tác giả, **không phải chứng nhận chạy DPU trên KV260**.
Vitis AI, INT8, XMODEL và KV260 acceptance thuộc bước độc lập của SV2.
SV1 Linux và R4 giữ trạng thái riêng; không sửa anchor/source-hash gate R4
và không tuyên bố toàn Week 3/4 PASS Linux.

SV2 gửi lại commit đang checkout, OS/kernel/CPU, Python/dependency, toàn bộ log
và receipt (nếu có), kể cả khi FAIL. Không yêu cầu SV2 sửa model hoặc nới tolerance.
Chỉ cập nhật nghiệm thu sau khi có bằng chứng từ máy nhận; hiện vẫn **PENDING**.
