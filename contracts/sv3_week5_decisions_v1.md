# Quyết định SV3 tuần 5 — decision note v1

Ngày: 2026-10-09, Asia/Saigon. Nguồn quyết định: S6 do người dùng truyền đạt từ
SV1 trong yêu cầu ngày 2026-10-09; checklist 1.1. `CURRENT WEEK=5`,
`REVIEW_STATUS=PENDING`. Version note là 1, không đổi I1 v1 hoặc I2/1.

Ba quyết định scale, shape I2 và gate accuracy đã chốt. Không cần hỏi lại.
Implementation và kiểm thử Python độc lập đạt; **tổng tuần 5 BLOCKED** do
repository chưa có ID registry wire được phê duyệt. Không coi test profile là
deployment profile. [Hồ sơ kiểm thử/bàn giao](../ml/docs/week5_technical_20261009.md)
ghi gate, lệnh chạy và hạn chế.

## Nguồn thực thi và schema hiện hành

| Vai trò | Nguồn chuẩn |
|---|---|
| I2/1, API, PRNG/key/nonce, NCL và lỗi | [Contract](i2_protection_v1.md), [Python](i2_ref/i2_reference.py), [C reference lịch sử](i2_ref/i2_reference.c) |
| Descriptor28, profile, enum lỗi và chữ ký C | [Header](i2_ref/i2_reference.h); schema descriptor tại mục 4 contract I2/1 |
| Vector I2 chuẩn, gồm INT8 -128 | [vectors.json](i2_ref/vectors.json), [host Python/C tests](i2_ref/test_i2.py) |
| I1 v1 metadata/scale schema | [I1 v1](i1_device_edge_packet_v1.md), mục 7–8; header packet tại mục 5 và vector packet mục 19 |
| FP32 registry model/split đã xác nhận | [Config](../ml/configs/week3_sv2_interface_review.json), [contract](sv3_sv2_week3_fp32.md), [wrappers/mapping](../ml/scripts/week3_sv2_common.py) |
| Reference lượng tử hóa đã review, giữ nguyên | [quantization.py](../ml/src/quantization.py), version `ncl-int8-fp16-v1-review`; code không đổi so với `b73a705` |
| Metadata ML tuần 5 bổ sung | [sv3_week5_ml_registry_v1.json](sv3_week5_ml_registry_v1.json): thông tin ML có đủ, wire ID chưa cấp, các field đó giữ `null` |
| Tài sản 20 mẫu và frozen test | [Receipt release](../ml/provenance/week5/external_assets.json); golden manifest `ml/artifacts/week5/quantization20/manifest.json`; processed manifest `ml/data/processed/mitdb/processed_manifest.json` |

Repository chưa có codec/header C cho I1 v1 hoặc file JSON Schema riêng cho
packet I1; schema normatif hiện là các bảng trong contract. Header
`device/src/week4_protocol.h` là giao thức demo FP32 tuần 4, không thay thế
header/schema I1. Không dùng I1 v2 proposal như chuẩn đã được duyệt.

## Scale và đường suy luận

INT8 symmetric per-sample/per-channel, zero-point=0, axis=1; scale lưu FP16
little-endian `[N,C]`. Giữ nguyên reference: maxima FP32 trên L; raw scale
maxima/127; kênh toàn zero scale=1; kênh khác floor tại FP16 min normal
2^-14; từ chối nonfinite hoặc raw scale vượt 65504. Cast FP16 rồi đọc lại làm
scale effective; q dùng ties-to-even và clip `[-127,127]`. P1 xử lý mọi byte
INT8, gồm -128, còn dequantizer reference symmetric từ chối q=-128.

I1 v1 scale wire là **FP32 little-endian mở rộng chính scale FP16 đã lưu/đọc
lại**. Không gửi scale raw, không tính lại scale, không gửi FP16 dưới nhãn I1
v1. [Component serializer](../ml/src/week5_interfaces.py) chỉ tạo vùng bytes
scale; không tạo packet, transport hoặc tuyên bố I1 end-to-end/FROZEN.

Thứ tự bắt buộc:
`head → quantize → protect → unprotect → dequantize → restore shape → tail`.
Scale thuộc kênh gốc. Dequantize tensor còn affine/hoán vị bằng scale kênh
gốc là sai. I2 NCL không đổi layout I1; NC s9/s10 thêm L=1 tại ranh giới I2
rồi bỏ L=1 trước tail; shape gốc NC và thứ tự kênh giữ nguyên.

## I2/1 và khả nghịch

Giữ API `protect(bytes, descriptor28, nonce12, key32, active_profile)` và
unprotect đối xứng. Active profile lấy từ registry cục bộ tin cậy, không suy
C/L từ payload. Descriptor phải khớp model/split/C/L/key/buffer của profile;
N=1, 1≤C≤256, 1≤C*L≤32768 và không vượt profile buffer. Reject metadata lỗi
theo thứ tự và mã lỗi của reference; không fallback shape hoặc ID.

IETF ChaCha20 dùng key32, nonce12, counter=0. C byte đầu cho a (`byte|1`), C
byte sau cho b; Fisher–Yates giảm i, đọc uint32 little-endian, rejection khi
r≥2^32−(2^32 mod (i+1)); `p[o]` chỉ kênh nguồn. Với s=p[o]:

`y[o,l] = (a[s]*q_byte[s,l] + b[s]) mod 256`.

Mỗi bước Fisher–Yates là swap, nên p là song ánh. Vì a[s] lẻ,
gcd(a[s],256)=1; tồn tại duy nhất inverse a⁻¹[s] modulo256. Bên nhận tái tạo
cùng a,b,p từ cùng key/nonce, tính
`q_byte[s,l] = a⁻¹[s]*(y[o,l]−b[s]) mod256`, đặt về kênh nguồn s. Thay công
thức y vào cho đúng q_byte modulo256; phép diễn giải lại two's complement
giữ nguyên mọi bit. Không có float trong P1. Phải đảo affine và đặt lại kênh
trước dequantize, theo đúng reference; không tự chọn PRNG/thuật toán khác.

Nonce là `sender_id:uint32_le || sequence:uint64_le`, key/nonce test public
chỉ cho kiểm thử. Hàm transform thuần không cấp nonce, không giữ state qua
reboot và không tự phát hiện reuse. Provisioning, sender scope, nonce bền và
receiver lifecycle thuộc SV1/Trung. P1 là obfuscation đảo được, không phải
mã hóa mạnh; không có MAC, authentication hoặc chống replay an toàn. Edge có
key khôi phục q; sai key hoặc payload sửa có thể trả tensor khác không lỗi.

## Accuracy và preservation

Đúng checkpoint `9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90`,
đúng preprocessing và test frozen 8.544 mẫu, mọi s=0..10. Gate chính là
`Accuracy_FP32 (%) − Accuracy_INT8 (%) <0,5 điểm phần trăm`, đúng 0,5 FAIL.
Runner dùng bất đẳng thức integer `200*(correct_FP32−correct_INT8)<8544`,
không quyết định từ số đã làm tròn hoặc trung bình 11 split. Tỷ lệ giảm tương
đối chỉ tham khảo, giá trị âm là accuracy cải thiện. 20 mẫu chỉ kiểm bytes/số
học, không kết luận accuracy. Chỉ vùng tensor FP32→INT8 giảm 4×, không phải
tổng packet có scale/header/nonce/CRC.

Không retrain, đổi kiến trúc, điểm cắt, split dataset, preprocessing hoặc
checkpoint. Không re-export/tái sinh goldens, sửa manifest hay tạo lại ZIP ML.
Tài sản lịch sử giữ nguyên; bằng chứng mới tại `ml/provenance/week5-20261009-v1/`
và `ml/results/week5-20261009-v1/`. Inventory 94.518 file trước/sau có 0 thay
đổi; hash và verification chi tiết trong hồ sơ. Tài sản được copy nguyên byte
vào checkout riêng; header fixture Device được generate chỉ trong checkout
mới để chạy regression host từ payload R4 đã xác thực.

## Đề xuất chưa áp dụng và trách nhiệm

- API cũ chỉ biết số byte trong proposal PR #7: superseded bởi I2/1.
- xoshiro hoặc runtime PRNG thay ChaCha20, layout NTC thay I2 NCL, gửi raw
  scale/FP16 trên wire I1 v1: không áp dụng.
- Mapping s+1 trong test P1: test-only, không có thẩm quyền cấp wire ID.
- I1 v2 mang I2: proposal, chưa triển khai; I1 v1 vẫn cấm protected payload.
- Gate relative 0,5% hoặc trung bình qua splits: không áp dụng.

Blocker W5-REGISTRY: FP32 registry ghi rõ không cấp I1 wire IDs; I1 mục 7 và
I2 mục 3 còn ghi chưa có registry deployment. Đề xuất **chưa áp dụng** để SV1
quyết định: cấp model_profile_id `0x4D495401` cho model/version/checkpoint trên,
wire split_id `256+s` cho s=0..10 (256..266), xác nhận không xung đột registry
của SV1/Trung. Không điền các giá trị đề xuất vào registry thực thi. Sau khi
được phê duyệt, tạo revision registry gồm ID đã cấp, nạp hai phía và rerun
descriptor/registry/real-tail gates; không cần sửa reference/goldens/ZIP.

SV3 chịu trách nhiệm ML metadata/reference/vector và code Python. Trung triển
khai phía nhận theo contract chung, khôi phục q trước dequantize/tail. SV1 và
Trung gán key_id/sender scope/buffer thực; SV1 triển khai MCU/nonce lifecycle;
Trung xác minh compile DPU/DPU+PS và runtime. Các giá trị key/buffer còn mở là
dependency deployment, không đồng nghĩa ba quyết định scale/shape/gate chưa
chốt. SV3 chuẩn bị hồ sơ, không gửi tin nhắn thay người dùng.

C P1/50 vector mới, tối ưu MCU, NoPeek/P2/LUT và tuần 6 chưa bắt đầu. Host test
C reference lịch sử không phải nghiệm thu firmware hoặc C handoff tuần 6.
Không đánh dấu người dùng đã học hiểu. Chưa review tổng thể, merge hoặc đổi tuần.
