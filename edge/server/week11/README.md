# Week 11 KV260 model cache stress test

| Step | Owner |
|---|---|
| Verify inputs, run on the board, and analyze on the PC | Edge operator |
| Demonstrate the workload and confirm the result | Edge operator and project reviewer |

Use the sealed Week 10 preparation and parity from the same worker, model
bundle and CPU plugins. See the [Week 10 entry point](../week10/README.md)
for preparation and parity recovery. The retained inputs are authenticated
offline I1 vectors. The runner issues P0 requests with fresh IDs to the
same receiver used by the Week 10 benchmark.

On KV260, provide absolute paths to the existing preparation, worker, model
bundle, CPU plugins and sealed parity. Run with the verified board Python and
NumPy. The `board.sh` wrapper accepts `probe`, `stress` and `demo` for the
existing deployment. See `stress.py --help` for direct use with other paths.

```bash
python3 -B stress.py run --session SESSION --worker BUILD/asi-cache-worker \
  --deploy VERIFIED_BUNDLE --cpu-ops VERIFIED_PLUGINS --baseline SEALED_PARITY \
  --source-commit CHECKOUT_HEAD --output NEW_RUN
```

One process preloads s0–s9, warms up 20 requests per model and then handles
10,000 seeded transitions between different splits. Each request executes the
real tail and checks its FP32 logits against parity. The optional 100-switch
demo creates its own evidence. Every 100 switches the driver samples worker
and receiver memory outside the timing interval. RSS, PSS and private
memory use KiB. Available RAM, contiguous memory and swap depend on the
board kernel's exposed fields.

On the PC, from the repository root, analyze a sealed board directory:

```bash
python3 -B edge/server/week11/stress.py analyze --run RECEIVED_RUN \
  --core edge/server/week10 --output NEW_ANALYSIS
```

The analyzer checks checksums, seeded plan, request counts, model identity,
cache counters, parity, worker exit code and memory sample coverage. It
exports memory and timing CSVs alongside the summary. The
[notebook](../../../experiments/notebooks/sv2_edge_week11.ipynb) reads those
exports. Review the memory trend and crash evidence for the measured run
before recording acceptance.

## SV2 TỰ LÀM — queue tải bùng, echo và T1

Chuẩn bị hai thư mục công cụ mới trên HOST, từ repo root. Thay
`NEW_DELIVERY` bằng thư mục chưa tồn tại.

```bash
mkdir NEW_DELIVERY &&
mkdir NEW_DELIVERY/tool NEW_DELIVERY/burst_tool &&
cp edge/server/week11/{stress.py,board.sh} NEW_DELIVERY/tool/ &&
git rev-parse HEAD > NEW_DELIVERY/tool/source_commit.txt &&
(cd NEW_DELIVERY/tool && sha256sum board.sh stress.py source_commit.txt > delivery.sha256) &&
cp edge/server/week11/{burst.py,burst_board.sh,shared_queue.py} NEW_DELIVERY/burst_tool/ &&
(cd NEW_DELIVERY/burst_tool && sha256sum burst.py burst_board.sh shared_queue.py > delivery.sha256)
```

Chép hai thư mục đã kiểm vào một thư mục chạy mới trên KV260 qua SCP.
Board cần Python 3.9+, NumPy, psutil cho RSS, Vitis AI 2.5 và thư mục
chuẩn bị tuần 10 có `d2_environment.json`. Trong terminal KV260, đặt
`WEEK10_SESSION` tới thư mục chuẩn bị và `WEEK11_PARITY` tới parity đã
niêm, sau đó chạy một trong các lệnh sau từ thư mục chạy mới. Khi cần
đổi đường worker, đặt thêm `WEEK11_WORKER`.

```bash
WEEK10_SESSION=SESSION WEEK11_PARITY=SEALED_PARITY bash tool/board.sh probe
WEEK10_SESSION=SESSION WEEK11_PARITY=SEALED_PARITY bash tool/board.sh stress stress
WEEK10_SESSION=SESSION WEEK11_PARITY=SEALED_PARITY bash burst_tool/burst_board.sh burst 32
```

Lệnh probe đọc và kiểm đầu vào. Stress và burst lưu từng lượt dưới
`runs/`, dùng chung khóa chạy. Đóng phiên đang sử dụng DPU trước khi bắt
đầu phiên mới. FIFO trong `shared_queue.py` có cùng byte với bản lưu trong
capture. Burst thực thi 48 job s2 và lưu lịch đến, log job, provenance,
mã thoát và checksum. Chép cả thư mục lượt chạy về HOST để kiểm shell
checksum và phân tích.

```bash
python3 -B edge/server/week11/burst.py analyze --run BURST_CAPTURE/raw \
  --core edge/server/week10 --output NEW_ANALYSIS
python3 -B edge/server/week11/echo_host.py --vectors SV1_ECHO_VECTORS_JSON --output NEW_ECHO
```

Echo dùng bộ vector SV1 ngày 26/11 có SHA-256
`6aaaed46c5caf217330837bbc27ae75b4f61dfe4d13e6d9cf874fcafde73c950`.
Script lưu 52 kết quả sau khi kiểm bytes và phân mảnh/ghép ở MTU 23 và 247.
Hai vector 362 B được tạo cho ca bổ sung. Phần này thực thi trên HOST.

T1 dùng [Release M1 v4](https://github.com/ChouPro205/Adaptive_Split_Inference/releases/tag/sv3-m1-v4-package-a-20261112).
Xác thực ZIP và manifest theo Release, rồi kiểm inventory và checkpoint
theo `ml/scripts/package_m1_v4_a.py` trong môi trường ML. Bản ZIP dùng thứ
tự inventory của hệ tạo gói. Khi chạy trên Linux, đối chiếu đầy đủ mọi
trường inventory theo path trên manifest đã xác thực. Sau đó chạy
`edge.quantize_tail.run_quantization` với `dry_run=True`, `s=0`, SHA C5
trong tiến trình, `calibration/z_s0.npy`, `calib_data_split="train"` và
`calib_samples=1`. Ghi log logits shape `[1,5]` và thử lại cùng cấu hình
với checkpoint tuần 3 để kiểm bị từ chối do SHA khác.
[Cấu hình đã chạy](../../../experiments/configs/sv2_edge_week11.json) ·
[Báo cáo và kết quả](../../../docs/sv2_edge_week11_report.md)
