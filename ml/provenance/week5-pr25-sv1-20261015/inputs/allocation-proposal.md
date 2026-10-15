ĐỀ XUẤT CHƯA PHÊ DUYỆT — không dùng làm registry triển khai.

Model/version: mitdb_week2_cnn_v1 / mitdb_week2_cnn_v1; checkpoint `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`.

model_profile_id đề xuất `0x4D495401` (1296651265); key_id đề xuất `1`, sender_id đề xuất `1`. Cả ba namespace phải được Châu/Trung xác nhận, chưa chứng minh không trùng bên ngoài repo.

| s | Wire ID đề xuất | Endpoint | Shape gốc | I2 NCL | Payload / max đề xuất B | FP16 B | FP32 LE wire B |
|---:|---:|---|---|---|---:|---:|---:|
| 0 | 256 | normalized_model_input (identity head) | 1×1×360 | 1×1×360 | 360 | 2 | 4 |
| 1 | 257 | features.1 | 1×16×360 | 1×16×360 | 5760 | 32 | 64 |
| 2 | 258 | features.4 | 1×16×180 | 1×16×180 | 2880 | 32 | 64 |
| 3 | 259 | features.6 | 1×32×180 | 1×32×180 | 5760 | 64 | 128 |
| 4 | 260 | features.9 | 1×32×90 | 1×32×90 | 2880 | 64 | 128 |
| 5 | 261 | features.11 | 1×48×90 | 1×48×90 | 4320 | 96 | 192 |
| 6 | 262 | features.14 | 1×48×45 | 1×48×45 | 2160 | 96 | 192 |
| 7 | 263 | features.16 | 1×64×45 | 1×64×45 | 2880 | 128 | 256 |
| 8 | 264 | features.19 | 1×64×22 | 1×64×22 | 1408 | 128 | 256 |
| 9 | 265 | classifier.3 | 1×32 | 1×32×1 | 32 | 64 | 128 |
| 10 | 266 | classifier.4 | 1×5 | 1×5×1 | 5 | 10 | 20 |

Device đã chứng minh quantized[5760], C≤64, FP16 scales[128] bằng source và artifact được nghiệm thu. FP32 LE scale tối đa 256 B là vùng scale wire; không chứng minh packet buffer hoặc hai buffer I2 đã triển khai. 32768 B là trần I2, không phải buffer Device. Đề xuất profile ceiling từng split bằng đúng payload trong bảng; cần Châu duyệt thay các ceiling 32768 hiện tại.

Trung cần xác nhận Edge ít nhất payload 5760 B/C64 và vùng scale FP32 LE 256 B, cùng namespace/model/checkpoint/mapping/key/sender/revision. Chưa có evidence capacity Edge.

Nonce đề xuất theo I2/1: sender:uint32 LE + sequence:uint64 LE, sequence bắt đầu 1; persist reservation trước phát; reboot bỏ số chưa dùng trong dải; nếu không chắc persistence thì dừng/rotate key+ID; retry phát nguyên request bytes, không protect lại; hết uint64 phải dừng/rotate.

Revision đề xuất `mitdb-week5-i2-registry-v1-pending`; hai phía cần cùng registry raw SHA256/revision và approval thực tế có trust anchor được cung cấp độc lập. Không có approved_by, chữ ký hoặc approval SHA giả trong báo cáo này.

Ngay cả khi allocation được duyệt, phải sửa regression `test_week5_p1.py` và review lại HEAD mới trước merge.
