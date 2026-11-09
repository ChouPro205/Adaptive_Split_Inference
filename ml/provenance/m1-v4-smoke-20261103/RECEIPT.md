# Receipt smoke M1 v4 trên GPU máy train (03/11/2026)

Mục đích: ghi chú 2a trong review M1 v4 của SV1 (`docs/inbox/sv1_v4_review_20261103/sv1_review_m1_v4_20261103.txt`,
SHA-256 `f0ca9ebcae8383498265653c96f4672c61acd86c072a1f903e37c0bbe2b1b1b3`): chạy smoke tương tự trên máy dùng để train,
trước slot đầu. Smoke không đổi SHA nào của protocol, plan hay assets.

## Script

- `smoke_v4.py`: bản sao nguyên byte của script SV1 gửi kèm review, nguồn `docs/inbox/sv1_v4_review_20261103/smoke_v4.py`,
  SHA-256 `452fa9fa3e7c5355349c4a987ca460767ce3c88991485cd4b330c9d0965352be`. Không sửa.
- Lệnh (chạy từ gốc worktree), exit code 0:

  ```
  ../../ml/.venv/Scripts/python.exe -B docs/inbox/sv1_v4_review_20261103/smoke_v4.py <gốc worktree> ml/data/smoke-m1-v4-20261103
  ```

- Dữ liệu: chỉ mảng ngẫu nhiên do script tự sinh (`default_rng(12345)`, số nhịp từng lớp bằng train/val thật) trong
  `ml/data/smoke-m1-v4-20261103/fake_arrays/` (thư mục bị ignore). Không đọc file MITDB nào, không mở DS2.
  `attempt-identity.json` của cả ba lượt ghi `DS2_arrays_opened: false`, `summary.json` ghi `DS2_evaluated: false`.
- Code được gọi: `ml/scripts/train_mitdb_baseline_v4.py` (`b9ff8479…a0b4540`), config slot `C0-seed20261030.json`
  (`753ba53e…c9654`) và `C4-seed20261030.json` (`944e8178…f41`) của plan v4 (`1ce2f811…d956`); script chỉ đổi `epochs` thành 3 trong bộ nhớ.

## Môi trường (`environment.json`, sinh bằng `environment_capture.py`)

| Mục | Giá trị |
|---|---|
| GPU | NVIDIA GeForce RTX 5060, 8151 MiB (8.546.484.224 byte theo torch) |
| Compute capability | 12.0 (sm_120) |
| Driver | 591.86 (hỗ trợ CUDA tới 13.1) |
| CUDA runtime của torch | 13.0 |
| torch | 2.14.0+cu130 |
| cuDNN | 92400 (9.24.0) |
| Python / numpy | 3.11.9 / 2.4.6 |
| OS | Windows 11 Pro 10.0.26200 |

Sửa trước commit (03/11/2026, SV3 duyệt): trường `python_executable` trong `environment.json` ban đầu là đường dẫn
tuyệt đối trên máy cá nhân, được thay bằng `../../ml/.venv/Scripts/python.exe`; mọi byte khác giữ nguyên.
SHA-256 `environment.json` trước khi sửa `341a41e838e5c256541a621fc3a2d4d70a929972120c5fd83aa79c0b51af3e11`,
`SHA256SUMS` trước khi sửa `4c9b7ade68641a5e4beb6901c213cf755f9cd76fa3bc454bdbca467fa9284cf5`. Hai file đó chưa gửi ai
và chưa commit. `environment_capture.py` giữ nguyên như lúc chạy (vẫn ghi `sys.executable`).

## Kết quả (`smoke_result.json`, `smoke_stdout.txt`, `receipt_derived.json`)

| Lượt | Thời gian/epoch (s, train + val) | Lượt rút/epoch | reload_exact | Epoch chọn | SHA-256 checkpoint |
|---|---|---|---|---|---|
| C0-seed20261030-a | 2,866 / 1,960 / 1,951 | 41.472 ×3 | true | 2 | `c92a127247c903a7a139ad41b838bfc46741906d561c76e55bc2d0c0be5d3178` |
| C4-seed20261030-a | 1,933 / 1,975 / 1,895 | 41.472 ×3 | true | 3 | `494f966af0b7737c51c301a78aeb5f4d59df45cf158c0d3bd2f54fd60bc1db8a` |
| C4-seed20261030-b | 1,958 / 1,929 / 2,012 | 41.472 ×3 | true | 3 | `494f966af0b7737c51c301a78aeb5f4d59df45cf158c0d3bd2f54fd60bc1db8a` |

- Thời gian epoch suy từ mtime các file `epoch-*.json` (epoch 1 tính từ `attempt-identity.json`). Epoch 1 của lượt
  đầu có cả thời gian khởi động CUDA.
- SHA checkpoint đầy đủ lấy từ `summary.json` và được tính lại từ file `.pt`: hai giá trị trùng nhau. Script SV1 chỉ in 16 ký tự đầu.
- VRAM: `vram_samples.csv` lấy mẫu `memory.used` toàn GPU mỗi 200 ms (133 mẫu). Mức nền 2164 MiB, đỉnh 2515 MiB, chênh
  351 MiB. Trên Windows/WDDM, `nvidia-smi` không báo VRAM theo tiến trình, nên con số này gồm cả CUDA context và cache allocator,
  không phải `torch.cuda.max_memory_allocated`.
- Cửa sổ chạy (UTC): `run_window_utc.txt`.

## Tiêu chí

| Tiêu chí | Kết quả |
|---|---|
| Mỗi epoch đúng 41.472 lượt rút (9/9 epoch) | PASS |
| `reload_exact` true (3/3 lượt) | PASS |
| Hai lượt C4 cho SHA-256 checkpoint đầy đủ trùng nhau | PASS |

Không so SHA với kết quả smoke của SV1 (RTX 3050 Laptop): khác GPU thì checkpoint khác là bình thường.

## Phạm vi

PASS ở đây chỉ chứng minh luồng code fit_slot v4 (cả shuffle C0 lẫn sampler C4) chạy hết trên GPU này và lặp lại được
theo bit trong cùng máy. Đây không phải bằng chứng về chất lượng mô hình, không phải nghiệm thu phần cứng, và không
dùng để chọn tham số. Số liệu trên dữ liệu ngẫu nhiên không mang ý nghĩa phân loại.
