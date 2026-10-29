# Báo cáo SV2 / Edge — Tuần 8

**Ngày:** 27/10/2026. **Phạm vi:** tích hợp Device–KV260 tại split s=2,
P0/P1, kiểm số học/timing và hồ sơ bổ sung PHY. Báo cáo tổng hợp kết quả đã lưu
ngày 26–27/10; không chạy lại model hoặc radio khi xuất bản.

## 1. Kết quả và trạng thái

G2 Device–KV260 đã được **SV1 xác nhận PASS** trong review ngày 27/10:
100 mẫu × P0/P1 = 200 chu kỳ, không lỗi, logits Device khớp offline KV260.
Tái kiểm phía Edge xác nhận 212 request toàn phiên (1+1+10+200), 0 cache hit,
200/200 request G2 có q/scale đúng mẫu và logits trùng bit offline KV260.
Hai lượt offline cùng backend trùng bit 100/100; bổ sung 21/21 request cũng
trùng bit offline. Bằng chứng và số tính lại ở [results/week8/edge](../results/week8/edge/README.md).

| Nội dung | Trạng thái tại ngày báo cáo |
|---|---|
| Native parity persistent/single-input, 3 mẫu | Bit-exact 3/3 theo receipt ARM |
| Offline s2, 100 mẫu, hai lượt | Thực thi đủ; hai lượt trùng bit 100/100 |
| BLE G2 chính thức, 100 mẫu × 2 mode | Edge 200/200 trùng offline; Device PASS theo SV1 |
| Agreement nhãn với reference | 87/100; không phải accuracy test độc lập |
| Gói bổ sung 1+10+10 | SV1 import PASS, 21/21 dòng khớp raw, 0 cache hit |
| Trace HCI cả buổi bổ sung | Chưa khôi phục; receiver chấp nhận log Dongle + Read PHY, ghi giới hạn |
| Tiêu chí Device | SV1 báo 8/9 PASS, TC7 registry chờ SV2 |
| Revision registry r2 | Đã review delta và 9 checksum evidence; chờ người dùng xác nhận trong PR, không sửa registry lịch sử |
| Đo toàn bộ 8.544 mẫu | Chưa thực hiện; tùy chọn sau khi xác nhận pipeline |

Kết luận Device/link do SV1 review được ghi riêng trong
[sv1_review.json](../results/week8/edge/sv1_review.json). Fetch cuối nhận PR [#39](https://github.com/ChouPro205/Adaptive_Split_Inference/pull/39)
đã merge: [báo cáo Device](sv1_device_week8_report.md),
[49 file receipt có manifest](../results/week8/device/manifest.json) và delta r2
đã được đồng bộ. Đã kiểm 49 SHA receipt và hash log Edge mà Device importer
đã đọc khớp log G2 phía Edge. Đây là kiểm kết quả đã lưu, không chạy lại checker
trên CDC raw hoặc firmware. Nguồn này thay trạng thái chưa có report/delta ở
lần fetch đầu của phiên xuất bản.
Việc thiếu btsnoop bổ sung và schema log riêng không còn là yêu cầu phải gửi
thêm theo receiver review mới; giới hạn bằng chứng vẫn được bảo toàn.

## 2. Setup và luồng thực thi

- KV260 SD-A: PetaLinux 2022.1, kernel 5.15.19-xilinx-v2022.1, aarch64,
  Vitis AI 2.5 / XRT / XIR / VART; DPU B4096, root GraphRunner CPU+DPU.
- Worker C++ build với GCC 11.2.0. Conv1d/MaxPool1d/ReLU dùng CPU plugins
  app-local đã pin; không gọi thời gian root runner là DPU-only.
- UB500 VID:PID 2357:0604, BlueZ 5.61, Bleak 0.22.3, NumPy board 1.21.2.
  Compile model theo lane Docker Vitis AI 2.5; không dùng setup PYNQ/VAI 3.5 cũ.
- Device nRF52840 là BLE peripheral/GATT server; KV260 là central. Laptop
  điều khiển CDC phía SV1, không thay KV260 làm inference peer.

```text
Device q/scale + I1 v2 + I2/1 P1 (hoặc P0)
 → BLE I1-BLE/1 reassembly → CRC/envelope/semantic checks
 → retry cache / P1 sequence check → unprotect → dequantize per-channel
 → persistent s2 root GraphRunner (CPU + DPU) → 5 logits FP32
 → response I1 64 B → BLE → Device
```

Native worker nạp model một lần trước loop, nhận từng tensor NCL [1,16,180]
qua stdin, chuyển layout/quantization theo tensor XIR, execute/wait và xuất
logits (1,5). Không lookup kết quả tham chiếu theo sample. Service giữ cache
retry 16 entry/60 s trong RAM; key theo peer/request ID và bytes, không cache
model động. P1 high-water cũng trong RAM, mất khi restart service.

Source: [service](../edge/server/week8/README.md),
[worker](../edge/runtime/persistent/README.md). Không đổi I1 v2, BLE binding,
I2/1, model, preprocessing hoặc registry. P1 là biến đổi đảo ngược, không thay
mã hóa/authentication; kết quả chỉ áp dụng bench nội bộ.

## 3. Đầu vào, provenance và phiên bản source

Reference NPZ có 100 ID duy nhất, q INT8 [100,16,180], scale FP16 [100,16],
logits FP32 [100,5], thứ tự N/S/V/F/Q. File được pin SHA-256
`e7407378e7870afbfa94b850f809c85165a1d640673d1f01bbd32f6d1aab76d5`.
Nhãn `label_ref` là argmax reference logits, không phải ground truth bệnh lý.
Bộ mẫu tích hợp được chọn có chủ đích, không đại diện toàn bộ test set.

| Artifact/source | SHA-256 |
|---|---|
| s2 xmodel | `68c5f86b5ca60479176aa7a5da0e9fef5b79ac436b43468e8ba0ae5353deeaa9` |
| Worker ARM đã đo | `9f542a2c5aaaf97e94a08a7c529ddd371e0894e5e74f9c5962bc31b5e6da222b` |
| Service phiên G2 212 request | `79a1da1bea8e4c07825efa1f0500a2b24ffce46e53e4ac4b3824323a2faf67e5` |
| Service cả ba lượt bổ sung | `a424bc905265e109ee225bc712a063695b9af25b010483162be8c6c16c0337bc` |
| Source persistent worker | `25a597692abc07437c1ff7940c34b4a3cb9396bf1e02441ef35db755bd99cd77` |

Patch bổ sung thêm `--hold-after-count` để giữ kết nối sau đủ request và kiểm
PHY, không sửa worker/model. Restart cuối dùng cùng SHA service; command log
đổi `--max-s 900` thành `1800`, vẫn `--expect 10 --hold-after-count`. Source
trong Git được tách lịch sử G2 và patch bổ sung; hash receipt gốc không thay.
Helpers export/review phát triển sau đo được phân biệt với source thực thi.
Không gửi HEAD cũ trước khi source tuần8 được commit như phiên bản đã chạy.

Exporter [export_week8_evidence.py](../edge/export_week8_evidence.py) kiểm ba
anchor archive/ZIP và extracted bytes, checksums, model/worker/plugins, source
receipt, q/scale/order/P0-P1/sequence/logits. Danh sách SHA đầy đủ và số file
được kiểm nằm trong [provenance.json](../results/week8/edge/provenance.json).
Raw/NPZ/model/binary/ZIP/btsnoop/key giữ cục bộ, không di chuyển hoặc đưa vào Git.

## 4. Số học: offline và end-to-end

Native parity 3/3 cho thấy persistent worker khớp single-input runner trên
cùng tensor; đây là kiểm ARM thật đã lưu, không phải fixture HOST.
Offline hai lượt cùng model/worker/plugins trùng bit 100/100.

| Nhãn tham chiếu | Số mẫu | KV260 khớp nhãn reference |
|---|---:|---:|
| N | 55 | 54 |
| S | 11 | 8 |
| V | 25 | 25 |
| F | 1 | 0 |
| Q | 8 | 0 |
| Tổng | 100 | 87 |

Max absolute error logits với reference: **5.721122741699219**. Không tune,
calibrate trên 100 mẫu này, loại mẫu hoặc dùng ngưỡng FP32 để gọi INT8 PASS.
Radio và offline KV260 trùng bit, q/scale đúng 200/200 nên sai khác reference
không do truyền BLE theo bằng chứng và kết luận receiver hiện có.

SV1 báo nguyên nhân là lượng tử tail DPU, internal output fix_point=3 và logit
Q bị giảm có hệ thống; đã báo SV3/GV. Đây là kết luận SV1, chưa phải audit độc
lập từng tensor DPU trong phiên viết báo cáo. Root runner receipt Edge ghi
input XINT8 [1,180,16], fix_point=5; final output FLOAT32 [1,5], fix_point=null.
Không nhầm fix_point tensor nội bộ DPU với output cuối root GraphRunner.

G2 200 request cuối bao đủ mẫu0…99, mỗi mẫu P0/P1. Toàn bộ 212 request gồm
106 P1 sequence tăng ngặt từ 60647426 đến 60647531. Không cache hit và chỉ một
kết nối; write-submit thành công phía Edge tự nó không chứng minh Device nhận,
phần Device reception do SV1 review xác nhận riêng.

## 5. Timing và liên kết

Thống kê trên **toàn bộ 212 request**, không chỉ200 G2:

| Phép đo | Mean | Std (population) | p95 | Min…max |
|---|---:|---:|---:|---:|
| Native root tail (ms) | 45.674226 | 0.156676 | 45.798139 | 45.533725…47.765797 |
| Edge RX hoàn chỉnh → TX submit (ms) | 75.330189 | 5.595183 | 81 | 69…83 |

Native timer `steady_clock` gồm input conversion/quantization, copy/sync,
execute/wait và output conversion; không gồm model load, BLE, Python parser,
unprotect hoặc pipe IPC. Edge timer là monotonic integer ms, kết thúc khi
BlueZ nhận write submissions, không phải ACK radio/Device hoặc E2E latency.
[Báo cáo SV1 §4](sv1_device_week8_report.md#4-thời-gian) giải thích DWT CYCCNT
dừng khi CPU ngủ (WFI trong lúc chờ notify/response). Vì thế tx_us/wait_us chỉ
đo thời gian CPU thức, không phải latency thực; wait_us khoảng 3 ms không mâu
thuẫn với tail khoảng 45,7 ms. Timing TX/WAIT thực lấy từ PPK2 marker D2/D3.
Đây là kết luận SV1 dựa trên firmware/đo Device; phiên xuất bản không đo lại
hoặc tự coi DWT là đồng hồ E2E. Số năng lượng B5 peer laptop chỉ kiểm hành vi
image, không đưa vào Table II hoặc thay bàn đo KV260 tuần 9.

Link do SV1 xác nhận từ Dongle cùng liên kết: **MTU 247, DLE 251/251, interval
45 → 15 ms, supervision timeout 4 s; PHY mặc định 1M, lên 2M sau LE Set PHY**.
MTU 247 cũng có trong connected event Edge. Lượt bổ sung1 có1 request P0 ở 1M;
lượt 2 có5 cặp/10 request ở 1M; lượt cuối SV1 gọi lượt 4 có5 cặp/10 request ở 2M.
Thư mục Edge cuối là `trial3_2m`, được ghi mapping, không rename raw.
Read PHY phía Edge có TX/RX 1M trước và2M sau Set PHY trên đúng handle.

Trace phiên 26/10 còn nhưng chỉ quan sát scan/advertising, không đủ connection
records. Trace cả buổi bổ sung27/10 chưa khôi phục; không dùng trace cũ thay thế.
SV1 chấp nhận dùng Device link logs + Edge Read PHY/state, ghi rõ hạn chế.
Không tái tạo HCI events, mốc giờ lệnh hoặc suy mọi request ở 2M chỉ từ lần đọc
PHY sau cùng. Nhận định lượt cuối chạy2M dựa thêm vào xác nhận Device của SV1.

Gói bổ sung có 88 checksum hợp lệ,3 import PASS,21/21 JSONL trùngraw theo receiver;
logits numeric được export tự động và kiểm FP32 bit-exact, scale hash FP16 LE.
Raw `peer.jsonl` có hex logits/FP32 scale hash và bản numeric/FP16 riêng;
không gọi file dẫn xuất là file service gốc. Receiver đã xác nhận format import
được, không còn yêu cầu gửi schema PEER_LOG_FIELDS.

## 6. Kiểm tra và tái lập

HOST Python 3.11.9 có NumPy; các lệnh chạy từ repo root, không đòi DPU:

```bash
python -B contracts/i1v2_ref/test_i1v2.py
python -B contracts/i2_ref/test_i2.py
python -B edge/tests/test_week8_service.py
python -B edge/tests/test_week8_ble_session.py
python -B edge/tests/test_week8_review.py
python -B edge/tests/test_week8_supplement.py
```

Fixture HOST kiểm parser/cache/duplicate/high-water, luồng 212 một kết nối,
review/tamper, hold/cancel và Set/Read PHY encoding; không chứng nhận radio/DPU.
Các kiểm tra mới đạt: I1 v2 **23**, I2 **5**, service **8**, session **1**,
review **1**, supplemental **4**, single-input **3**, runtime **5**: tổng **50 test**.
Notebook chạy được bằng kernel PC với export thật.

Source worker khớp ARM receipt đã đo; không rebuild ARM hoặc rerun radio trong
phiên xuất bản. Helper kế thừa single-input/runtime cũng được hồi quy HOST.

Export thật và hai negative checks (output tồn tại; archive đổi byte) được
kiểm khi xuất bản. Xem [README kết quả](../results/week8/edge/README.md) cho
lệnh exporter. Notebook chỉ đọc checksum/bảng/biểu đồ trong
[experiments](../experiments/notebooks/sv2_edge_week8.ipynb), không SSH/build/đo lại.
Cấu hình đã chạy: [sv2_edge_week8.json](../experiments/configs/sv2_edge_week8.json).

## 7. Việc còn lại và bàn giao tuần 9

- **TC7 đóng tuần 8:** đọc delta `mitdb-week5-i2-registry-v1-r2` và PR do SV1
  gửi, xác nhận cùng revision. [Delta r2](../contracts/sv1_sv2_week8_registry_revision_r2.json)
  đã có qua PR39: chỉ ACCEPTED counter nonce persistence của Dongle;
  provisioning vẫn NOT_ACCEPTED, p1_transmission_authorized=false. Đã kiểm
  base registry SHA, 9 SHA evidence, scope và giới hạn RAM high-water Edge;
  [kết quả review](../results/week8/edge/registry_r2_review.json) đủ để người
  dùng gửi xác nhận đúng phạm vi. File delta vẫn PENDING_EDGE_CONFIRMATION;
  không tự sửa registry v2 hoặc thay trạng thái xác nhận của người dùng.
- **Trước đo tuần 9:** mỗi connect/reconnect phải Set PHY 0032 đúng handle mới,
  Read PHY 0030 xác nhận TX/RX 2M, ghi log rồi mới cho SV1 phát request. Service
  tuần 8 chưa tự động bước này. Phiên không xác nhận 2M không tính theo SV1.
- Bàn đo tuần 9 đã chốt theo SV1: peer KV260, cách Dongle khoảng 50 cm,
  interval 15 ms, MTU 247, DLE 251, PHY 2M, P1/P0 luân phiên theo cặp, cùng
  format log. Queue/MQTT cần triển khai riêng; buffer một frame tuần 8 chưa
  phải queue Poisson hoặc MQTT tuần 9.
- Edge high-water sequence phải lưu bền trước khi dùng ngoài bench; không
  chặn tuần 9 theo SV1. Chưa bảo đảm từ chối sequence cũ qua restart service.
- Offline 8.544 mẫu là tùy chọn để đánh giá theo lớp trên test set độc lập;
  chưa thực hiện.
- Thu bằng chứng dài ưu tiên serial/UART cho TRACE; xác nhận collector/file
  trước request, dừng sạch và kiểm decode/phạm vi/checksum trước đóng gói.
  Chưa xác định SSH là nguyên nhân thiếu trace; serial không thay kiểm file.

Không cần đo lại buổi bổ sung chỉ để hoàn thiện tài liệu: receiver đã kết thúc
review. Việc ghi giới hạn ở đây bảo toàn phạm vi bằng chứng, không mở lại các
mục receiver đã đóng.

## 8. Source Git và hồ sơ công bố

- Commit `16d5b43`: service G2 nguyên bytes SHA `79a1…`, persistent worker và
  test service/session.
- Commit `4b605e9`: service giữ kết nối SHA `a424…`, PHY/review helpers và test
  bổ sung. Helpers được phát triển sau đo không được gọi là source G2.
- Báo cáo, exporter, config, notebook và kết quả nhỏ được commit riêng tiếp
  theo. Xem [publication.json](../results/week8/edge/publication.json) cho full
  commit SHA; [validation.json](../results/week8/edge/validation.json) cho kiểm tra.

Chỉ push nhánh dev/edge-sv2; đưa vào main bằng PR và review của thành viên khác.
Không tự tạo/merge PR hoặc thay lời xác nhận registry của người dùng.
