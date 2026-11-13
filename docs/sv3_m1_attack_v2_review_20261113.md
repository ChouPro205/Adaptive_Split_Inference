# Attack protocol v2 (M1) và code tấn công: bản sẵn sàng khóa

Ngày 13/11/2026. Người lập: SV3. Nhánh `dev/ml-sv3`.

**Trạng thái: chưa khóa. Chưa chạy tấn công nào trên MITDB và chưa mở DS2.** Smoke chỉ chạy trên dữ liệu giả.

| Mục | Đường dẫn | SHA-256 |
|---|---|---|
| Attack protocol v2 | `ml/configs/mitdb_m1_attack_protocol_v2.json` | `7a174dd9a8ea43003090c32db63db1ed3eae25e9abba8de07d9ec4f6bba019b0` |
| Bản trước (v1, không sửa, chưa từng khóa) | `ml/configs/mitdb_m1_attack_protocol_v1.json` | `869170470794aa2b1e7fca6eb217bc96b7eb0396be0720e39ca82cf79a19b5a0` |
| Plan tấn công (ràng buộc code, checkpoint, arrays DS1) | `ml/manifests/mitdb-attack-m1-v2/plan-manifest.json` | `8fc252d23c935a93d17fb0080f939fca105e22b8d37e769b2da7940fd32fb177` |
| Runner | `ml/scripts/attack_m1_v2.py` | `5064e09da9210da7a262818a1eab3647cbd0ef040929debc453f3040ea2f24b8` |
| Test | `ml/scripts/test_attack_m1_v2.py` | `6ae0a3903f89d13f97748f9144cb6e4786be8a0eaf9f338cec39fe2b5687819c` |
| Tin SV1 ngày 13/11 (review evidence của lần khóa) | `ml/provenance/m1-nopeek-v2-release-20261113/sv1_evidence/tra_loi_Ky_Anh_NoPeek_v2_goiA_20261113.txt` | `08b27b292b4c54e18c9a0b69a0cc2b4759a1ccd629d53a277f26f03403d3028b` |
| Receipt code, log, diff | `ml/provenance/m1-attack-v2-code-20261113/` | xem `SHA256SUMS.txt` cùng thư mục |

## 1. Thay đổi so với v1

Diff dòng của protocol nằm ở `ml/provenance/m1-attack-v2-code-20261113/diffs/protocol-v1-v2.diff`. Danh sách đầy đủ, kèm nguồn của từng mục, nằm trong trường `changes_from_v1` của protocol.

**Mục 1–10: theo đúng tin SV1 ngày 09/11 và 13/11.** SV1 viết: "Nếu diff so với v1 chỉ gồm các điểm này thì bạn khóa luôn".

| # | Nội dung | Nguồn |
|---|---|---|
| 1 | N = 22 cho lượt thử (DS1), N = 21 cho lượt chính thức (DS2 bỏ 202); Limitations ghi N = 21 | 09/11 mục 1, 5(1) |
| 2 | CI95: bootstrap trong từng bệnh nhân theo khối 10 nhịp liên tiếp, giữ nguyên tập danh tính, 2000 lần, seed 20261105, khoảng phân vị đổi sang Π | 09/11 5(2) |
| 3 | B chạy 3 seed: Adv của mỗi biến thể là trung bình 3 seed; Π = 1 − max theo biến thể; báo min–max theo seed; so với Π_min bằng ước lượng điểm | 09/11 5(2) |
| 4 | Mô hình tấn công theo bản ứng viên v1 | 09/11 5(3) |
| 5 | Kiểm năng lực B-naive ở s0 (ρ0) trước tiên, ngưỡng 0,80, tăng năng lực tối đa một lần | 09/11 5(3) |
| 6 | Decoder ở lượt thử học trên phía kẻ tấn công của 22 bản ghi DS1; lượt chính thức học trên train DS1 | 09/11 5(4) |
| 7 | Ràng buộc NoPeek v2, `grid-selection.json`, SHA của 4 ρ1 và của A; TF32 tắt | 13/11 mục 4; 09/11 4(5) |
| 8 | Điểm 3(c): lượt chính thức chạy thêm B-naive cho 2 seed còn lại ở s2 và s_m; ghi sẵn SHA của s2, s4, s5 | 13/11 3(c) |
| 9 | Thứ tự lượt thử: s0, rồi s2, s4, s5, s8, mỗi s chạy ρ0 và ρ1; báo Π(s2) ngay; receipt ghi lưu ý về 18 bản ghi DS1 | 13/11 mục 4, 3(b) |
| 10 | Bản chốt 03/11 trỏ vào bản chép trong provenance | 09/11 mục 5 |

**Mục 11–15: chi tiết thực thi mà v1 để trống.** Các mục này phải cố định trước khi chạy, nên mình liệt kê để SV1 thấy.

| # | Nội dung | Vì sao |
|---|---|---|
| 11 | Ranh giới chia: bỏ nhịp có \|r − 325000\| ≤ 10800; validation của kẻ tấn công là ⌈0,2 n⌉ nhịp cuối của phía kẻ tấn công mỗi bản ghi; nhãn là thứ hạng số của record id | v1 chỉ nói bằng lời. Đã tính lại đúng các số v1: bỏ 1.681/50.995 nhịp, phía kẻ tấn công 767–1.637 nhịp, phía test 799–1.613 nhịp, người đông nhất 6,59 % |
| 12 | Kiến trúc tăng năng lực cố định trước khi chạy: NCL 3 khối 128 kênh; NC là MLP 256-256. Thống kê kiểm năng lực là trung bình bacc test ở s0 của 3 seed B | SV1 chỉ nêu "ví dụ 3 khối, 128 kênh"; nếu không cố định thì kiến trúc sẽ được chọn sau khi đã thấy kết quả s0 |
| 13 | Chuẩn hóa đầu vào theo kênh, dùng mean/std của phần train phía kẻ tấn công; A1 dùng weight decay 1e-4 như B; seed B là 20261030, 20261031, 20261101; seed A1 là 20261030; giữ epoch tốt nhất, hòa thì lấy epoch sớm hơn | v1 không nêu |
| 14 | A1 ở s0 là phép đồng nhất, vì kẻ tấn công đã có tín hiệu lượng tử; công thức NRMSE, Pearson và sai số vị trí đỉnh R theo từng nhịp | v1 chỉ nêu tên chỉ số |
| 15 | z_s tính trên CPU (s0–s8 theo lô, s9–s10 từng nhịp), cả hai trùng bit golden gói A; lượng tử bằng `ml/src/quantization.py` của registry v2 | Hàm tuần 5 đã khớp bit với thiết bị |

## 2. Code tấn công làm gì

- `prepare` ghi plan. Plan ràng buộc SHA của 7 file nguồn, 5 checkpoint (ρ0 và 4 ρ1) và các arrays train/val của DS1. Mỗi ρ1 được đối chiếu với `grid-selection.json`, plan NoPeek và receipt grid.
- `preflight` chỉ đọc metadata DS1 (không đọc arrays, không chạy mô hình), rồi kiểm số chia khớp protocol.
- `run-trial` từ chối chạy khi chưa có file khóa và authorization đúng loại, ràng buộc protocol, plan và đúng file tin SV1 ngày 13/11. Việc kiểm này diễn ra trước khi đọc bất kỳ dữ liệu, mô hình hay đầu ra nào. Sau đó runner:
  1. kiểm z_s của ρ0 trùng bit với golden gói A ở mọi s;
  2. chạy B-naive ở s0 với kiến trúc cơ bản và áp luật năng lực;
  3. lần lượt chạy s2 ρ0, s2 ρ1, s4, s5, s8. Mỗi cặp ghi một file kết quả ngay khi xong, nên Π(s2) có sớm.
- Với mỗi cặp (s, ρ), runner ghi:
  - Π, CI95, min–max theo seed, kết quả từng seed (epoch tốt nhất, bacc trên validation và test, recall của từng bệnh nhân);
  - bacc theo phiên (bỏ phiếu theo khối 10 nhịp, chỉ để thảo luận);
  - chỉ số tái tạo của A1;
  - dự đoán test, trọng số kẻ tấn công, và một tín hiệu tái tạo mẫu cho mỗi bệnh nhân.
- `smoke` dùng metadata và nhịp giả do chính nó tạo ra, cùng checkpoint ρ0/ρ1 thật, nên không đọc file MITDB nào.

## 3. Đã kiểm

| Lệnh | Kết quả |
|---|---|
| `python -B ml/scripts/test_attack_m1_v2.py` | exit 0, 27/27 |
| `python -B -O ml/scripts/test_attack_m1_v2.py` | exit 0, 27/27 |
| `python -B [-O] ml/scripts/attack_m1_v2.py preflight` | exit 0, hai output trùng nhau, số chia khớp protocol |
| `python -B ml/scripts/attack_m1_v2.py smoke --output ml/data/smoke-attack-m1-v2-20261113` | exit 0, `SMOKE_PASS_RANDOM_DATA_NOT_MITDB`, chạy lại s2 ρ1 cho kết quả trùng hệt |

Các test bao gồm:
- luật chia theo thời gian ở đúng ranh giới;
- bacc, Adv, Π, bootstrap (tất định, cùng một lần rút cho cả 3 seed), bỏ phiếu khi hòa, chỉ số tái tạo;
- hình dạng decoder và classifier ở mọi s;
- luồng kiểm năng lực ở cả hai nhánh: giữ kiến trúc cơ bản và tăng năng lực;
- tính tất định của `fit`;
- `observed` đúng bằng lượng tử của registry; tính theo lô trùng bit với tính từng nhịp;
- golden check; nạp ρ1;
- cổng authorization;
- `run_trial` chạy từ đầu đến cuối trên arrays giả.

Smoke dùng dữ liệu giả và chỉ chạy 3 epoch, nên số của nó không nói gì về MITDB. Lần smoke này rơi vào nhánh tăng năng lực (bacc s0 0,49 < 0,80), nhờ đó nhánh ấy được chạy trọn vẹn.

Chưa kiểm: lượt thử thật trên DS1, vì cần file khóa. Thời gian chạy thật cũng chưa đo.

## 4. Cần quyết trước khi khóa

- **Có khóa luôn không?** Mục 11–15 là chi tiết thực thi, không đổi luật của SV1. SV3 quyết khóa luôn hay gửi SV1 xem trước.
- **Số đếm DS2 (tin 09/11 mục 1).** Protocol v2 ghi rằng các số này tính từ metadata DS2 trước lượt chính thức, không tính lúc khóa bản này, vì khóa bản này là để chạy lượt thử trên DS1 và không cần DS2.
