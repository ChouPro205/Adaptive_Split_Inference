# Protocol mô phỏng G5 — v1.1

Mã tài liệu: `ASI-G5-SIM-PROTOCOL v1.1`. Người lập: SV1 (Lê Hải Châu), ngày 12/11/2026 (v1 và v1.1).
Thẩm quyền: SV1 quyết theo ủy quyền của GVHD (quyết định nhóm 03/11 và 05/11/2026).

Tài liệu này **khóa trước** toàn bộ cách đánh giá controller chọn (s, ρ) lúc chạy:
mô hình độ trễ và năng lượng, controller đề xuất, baseline, ablation, trace, thông số
chính, chỉ số, tiêu chí G5, thống kê và kiểm tra đúng đắn. Code mô phỏng
(`experiments/g5_sim/`, viết từ tuần 12) phải làm đúng theo file này. Số đo đến sau chỉ là
**đầu vào**, không được dùng để sửa định nghĩa.

## 0. Trạng thái dữ liệu lúc khóa

Đã thấy khi viết bản này (chỉ số đo phía thiết bị tuần 8–9, đã công bố trong repo):

| Dữ liệu | File | SHA-256 |
|---|---|---|
| E_dev(s), t_dev(s), B(s) radio tắt, s0–s10, 3 phiên | `results/week9/device/analysis/table_iii_e_dev.csv` | `e6ef12d7…b500ad` |
| Chu kỳ s2 với KV260 (E_dev, E_prot P1, E_tx, E_wait, P_conn) | `results/week9/device/analysis/table_kv260_s2_pooled.csv` | `974fba4c…02110` |
| Tổng hợp phân tích tuần 9 | `results/week9/device/analysis/week9_analysis.json` | `36e56ebb…729d6` |
| Khối tải E_wait tuần 10 (seed 20261111), chưa đo | CSV gửi SV2 ngày 10/11 | `38937e54…9035e` |

**Chưa thấy** lúc khóa (không có trong repo, chưa ai gửi): mọi giá trị Π(s, ρ) (kể cả thử
sớm trên DS1), macro-F1 của head/tail NoPeek, tham số nhiễu ρ2, E_tx(B) theo payload,
P_conn(k) ngoài trạng thái chính, E_prot/E_wait/E_dev lúc radio bật của tuần 10, t_edge(s) ngoài
s2, trace kênh thật, trace tải nhiều client. Mục nào phải viết lại sau khi đã thấy một trong các
số này sẽ được đánh dấu **[sau Π]** hoặc **[sau đo]** trong lịch sử phiên bản (§17).

Protocol có hai lượt chạy, cùng định nghĩa, chỉ khác đầu vào (§16):
- **G5-early**: chạy trước 06/12/2026 (cuối tuần 13), dùng Π thử DS1 và số đo tuần 9–11.
- **G5-final**: tuần 19 (11–17/01/2027), dùng Π DS2, LUT đã xác nhận (I3 v1, registry r3),
  E_tx mã hóa bật, trace kênh thật.

## 1. Ký hiệu và đơn vị

| Ký hiệu | Nghĩa | Đơn vị |
|---|---|---|
| s ∈ S | điểm cắt; s10 = chạy hết trên thiết bị | — |
| ρ ∈ {ρ0, ρ1, ρ2} | cường độ bảo vệ trước edge: không, NoPeek, NoPeek + nhiễu theo kênh | — |
| a = (s, ρ) | hành động | — |
| n | chỉ số lần suy luận (một nhịp tim) | — |
| τ_n | thời điểm nhịp n đến | s |
| Δ_n = τ_{n+1} − τ_n | khoảng giữa hai nhịp | s |
| B(s) | payload uplink (INT8 + scale + header I1 v2) | B |
| k | trạng thái liên kết: (PHY, công suất phát, connection interval) | — |
| r(t), r̂(t) | goodput uplink thật / ước lượng ở thiết bị | B/ms |
| q(t), q̂(t) | số job chờ ở edge lúc request đến / giá trị thiết bị biết | job |
| t_svc | thời gian phục vụ một job ở edge | ms |
| b(t) | năng lượng pin còn lại | µJ |
| Π(s, ρ) | mức riêng tư đo bằng tấn công mạnh nhất | [0, 1] |
| D | hạn độ trễ | ms |
| Z | hàng đợi ảo năng lượng | µJ |
| V | trọng số độ trễ | µJ²/ms |
| E_b | ngân sách năng lượng mỗi lần suy luận | µJ |
| K | độ dài epoch tính lại ngân sách | lần suy luận |

Năng lượng luôn là **gross tại 5 V** (đường VBUS → REG0, tương đương pin Li-ion một cell cấp VDDH),
theo W9-D9.

## 2. Tập hành động và lọc offline

S = {0, 2, s_m, 10}. s_m chọn theo luật đã chốt 05/11, áp dụng máy móc khi có Π thử:
xét ρ ∈ {ρ0, ρ1}; nếu s4 có một ρ đạt Π_min thì s_m = s4; nếu s4 không đạt mà s5 đạt thì
s_m = s5; cả hai không đạt thì s_m = s4 và xét ρ2.

Tập ứng viên (8 cặp): (0, ρ0); (2, ρ0), (2, ρ1), (2, ρ2); (s_m, ρ0), (s_m, ρ1), (s_m, ρ2); (10, —).
Nếu gói B có thêm ρ3 (nhiễu ×2, SV3 quyết trước cuối tuần 12) thì thêm (2, ρ3), (s_m, ρ3) theo đúng
các luật dưới đây, không cần sửa protocol.

Lọc offline, trước mọi lượt chạy, ghi lại cặp nào bị loại và vì sao:
1. **Tiện ích**: macro-F1 4 lớp trên validation, đường DPU, ≥ 0,95 × 0,5682 = 0,5398 (kể cả ρ0).
2. **Riêng tư**: Π(s, ρ) ≥ Π_min, Π lấy theo định nghĩa của protocol tấn công SV3 (1 − Adv,
   balanced accuracy, tấn công mạnh nhất). Π(s10) dùng số đo trên logits nếu có. Nếu không có thì coi
   Π(s10) = 1, vì ở s10 không gửi tensor nào lên edge; khi đó ghi rõ đây là giả định.
3. Với mỗi s, giữ **ρ\*(s) = ρ nhỏ nhất đạt cả 1 và 2**; không có thì bỏ s. Bước rút gọn này đúng theo
   mệnh đề cấu trúc: khi Π không đổi theo thời gian và chi phí không giảm theo ρ, ρ tối ưu tại mỗi s
   không phụ thuộc Z, V, r, q (đặc tả controller §6a). Code vẫn duyệt cả 8 cặp để kiểm mệnh đề này
   (S10, §15).

Giả định ứng dụng (giống cho mọi phương pháp): nhãn được dùng trên thiết bị. Ở s10 không gửi gì;
ở các s khác nhãn về qua gói kết quả.

## 3. Mô hình độ trễ (Khung eq (1), mở rộng)

Với s ≠ 10:

T_n(a) = t_ctrl + t_dev(s) + t_prot(s, ρ) + t_tx,n(B(s)) + t_q,n + t_switch,n + t_edge(s, ρ) + t_rx

- t_dev(s): thời gian head đo bằng marker **lúc radio bật** (W10-D4; s ngoài tập đo thì theo W10-D5).
- t_prot(s, ρ): 0 với ρ0 và ρ1 (cùng phép toán); ρ2 lấy số đo tuần 14–15.
- t_tx,n = B(s) / r(τ_n), r lấy từ trace kênh (§9.2).
- t_q,n: thời gian chờ thật trong hàng đợi FIFO của edge do mô phỏng sự kiện tính (§5). Controller
  chỉ thấy ước lượng t̂_q = q̂ · t̄_svc (Lộ trình 9.2). Hệ số đo ở tuần 10 (độ dốc t_wait theo q, W10-D3)
  dùng để kiểm mô hình này.
- t_switch,n: thời gian edge đổi xmodel khi (s, ρ) khác lần trước, số đo của SV2. Lần đầu nạp một
  xmodel tính riêng; các lần sau dùng cache.
- t_edge(s, ρ): thời gian tail trên DPU đo được, theo s.
- t_rx: từ lúc edge xong đến khi thiết bị có nhãn, lấy từ chu kỳ đo với KV260.
- t_ctrl: thời gian controller (marker D4), dùng 0 cho đến khi đo được, có quét độ nhạy (§10).

Với s10: T_n = t_ctrl + t_dev(10). Không có hạng tử truyền, hàng đợi, tail.

Thiết bị chỉ xử lý **một suy luận một lúc**. Nhịp đến khi suy luận trước chưa xong thì chờ (FIFO phía
thiết bị). Độ trễ luôn tính từ lúc nhịp đến τ_n, nên phần chờ này nằm trong T_n và có thể làm trễ hạn.

## 4. Mô hình năng lượng (Khung eq (2), mở rộng)

### 4.1 Năng lượng một lần suy luận

Với s ≠ 10:

E_n(a) = E_ctrl + E_dev,on(s) + E_prot(s, ρ) + E_tx(B(s), k, t_tx,n) + E_wait(t_wait,n, k)

- E_dev,on(s): năng lượng head đo lúc radio bật. Đây là số cho LUT; Bảng III giữ số radio tắt
  (W10-D4).
- E_prot: 0 với ρ0 và ρ1; ρ2 lấy số đo tuần 14–15. Trước khi có số đo, G5-early dùng giá trị tạm
  P_head(s) · 0,1 ms (P_head = E_dev/t_dev đo được), có quét ×10.
- E_tx(B, k, t_tx) = α_k + β_k · B + P_x · max{t_tx − B / r_k, 0}. α_k, β_k từ hồi quy tuần 11
  (7 mức payload ở 2M, cộng 3 mức ở 1M và 3 mức ở công suất phát thấp). Hạng thứ ba là phần thời gian
  truyền dài hơn danh định khi kênh xấu. P_x lấy từ hồi quy E_tx theo t_tx, kiểm lại bằng trace thật.
  G5-final dùng số **có mã hóa lớp liên kết** (bật cho mọi phương pháp).
- E_wait(t_wait, k) = a_k + b_k · t_wait, với t_wait từ lúc TX xong đến lúc có nhãn
  (= t_q + t_switch + t_edge + t_rx). a, b từ hồi quy W10-D3. Nếu b lệch xa P_conn hoặc hồi quy không
  tuyến tính (R² < 0,9) thì E_wait dùng bảng theo khoảng t_wait (nội suy tuyến tính) thay cho dòng hồi
  quy. Luật này khóa ngay bây giờ.
- E_ctrl: chi phí controller (marker D4), dùng 0 cho đến khi có số đo, có quét.

Với s10: E_n = E_ctrl + E_dev,on(10). Trong controller, s10 vẫn **giữ kết nối**, để có thể quay lại
các s khác.

### 4.2 Năng lượng nghỉ giữa các suy luận

Từ lúc suy luận n xong đến lúc suy luận kế tiếp bắt đầu, thiết bị tiêu P_idle,on(k) = P_conn(k) nếu đang
giữ kết nối, hoặc P_idle,off = 25,4 µA × 5 V nếu radio tắt (chỉ có ở baseline device-only). Thêm năng
lượng nhận notify trạng thái mỗi 500 ms khi không có suy luận (§5.3), dùng số đo T17 khi có. Trước đó
lấy tạm a_k của E_wait, có quét. Khi T < Δ, cách tính này trùng hạng tử
P_conn(k) · max{Δ − T, 0} của đặc tả controller.

### 4.3 Năng lượng thật và năng lượng controller ước lượng

Mô phỏng phân biệt hai loại:
- **Năng lượng thật** (trừ vào pin): mỗi pha lấy mẫu lại (bootstrap) từ các chu kỳ đo thật của đúng
  cấu hình đó. Mỗi trace seed gán ngẫu nhiên một phiên đo cho mỗi cấu hình, để giữ lệch giữa phiên
  của REG0 (W9-D9…D12). Những pha chỉ có hồi quy (E_tx theo B) thì lấy giá trị hồi quy cộng phần dư
  lấy mẫu lại.
- **Năng lượng ước lượng Ê** (controller dùng để cập nhật Z): giá trị LUT gộp phiên, cộng hạng tử
  phụ thuộc thời gian tính từ t_tx, t_wait đo bằng timer (đặc tả §5, §6f).

Sai lệch Ê so với năng lượng thật được báo như một kết quả phụ của N3.

## 5. Mô phỏng hệ thống

Mô phỏng theo sự kiện rời rạc, đồng hồ tính bằng ms (float64). Các thành phần như sau.

### 5.1 Thiết bị

Nhịp đến theo trace (§9.1). Thiết bị gọi controller, thực thi a_n, đo t_tx và t_wait. Sau mỗi kết quả
gọi `commit` (cập nhật Z, r̂, q̂, E_b). Pin giảm theo năng lượng thật. Hết pin (b ≤ 0) thì dừng phục vụ;
các nhịp còn lại tính là không phục vụ.

### 5.2 Kênh

r(t) lấy từ trace kênh, hằng trong mỗi ô thời gian của trace. Thiết bị ước lượng
r̂ ← (1 − 0,3) · r̂ + 0,3 · B/t_tx sau mỗi lần truyền. Lúc đầu r̂ = r_k danh định. Nếu không truyền
quá 5 s thì r̂ trở về r_k (khi không có quan sát mới, không giữ ước lượng cũ vô hạn).

### 5.3 Edge và hàng đợi

Hàng đợi FIFO một server. Job nền đến theo trace tải (§9.3), tối đa 8 job nền đang chờ, không tính job
đang phục vụ; đầy thì job nền bị bỏ. Request của thiết bị luôn được nhận và xếp vào cuối hàng, đúng ngữ
nghĩa W10-D3. Thời gian phục vụ job nền lấy mẫu lại từ log t_service của SV2 tuần 10; job của thiết bị
có thời gian t_switch + t_edge(s, ρ).

q và t_svc được gửi kèm gói kết quả. Khi không có suy luận quá 500 ms, edge gửi notify định kỳ mỗi
500 ms. Thiết bị dùng q̂ = q từ gói hoặc notify mới nhất; nếu không nhận gì quá 500 ms thì vẫn dùng giá
trị cũ và đánh dấu stale (quyết định 03/11 câu 17). Giả thiết: tải chính đến từ client khác, nên quyết
định của một thiết bị không làm thay đổi phân phối q (đặc tả §6d).

### 5.4 Ngưỡng và tham số mô phỏng

Thời gian chờ phản hồi tối đa 5 s. Quá hạn này tính là lỗi, vẫn trừ năng lượng chờ. Không mô phỏng
mất gói BLE ở tầng ứng dụng: phát lại ở tầng liên kết đã nằm trong r(t).

## 6. Controller đề xuất (Algorithm 1 đã chỉnh)

```
Offline: A* = {(s, ρ*(s))} theo §2
Z ← 0; E_b ← b(0) / N_rem(0); r̂ ← r_k; q̂ ← 0
cho mỗi nhịp n:
    với mỗi a ∈ A*: tính T̂(a), Ê(a) từ LUT, r̂, q̂, t̄_svc, k, và trạng thái cache xmodel
    F ← {a ∈ A* : T̂(a) ≤ D}
    nếu F rỗng: a_n ← argmin_{a ∈ A*} T̂(a), ghi "dự báo trễ hạn"
    ngược lại:  a_n ← argmin_{a ∈ F} V · T̂(a) + Z · Ê(a)
    thực thi a_n; đo t_tx, t_wait; tính Ê_n
    Z ← max{Z + Ê_n − E_b, 0}
    sau mỗi K lần: E_b ← b(t) / N_rem(t)
```

- Ê(a) dự báo gồm cả năng lượng nghỉ tới nhịp kế tiếp: P_conn(k) · max{Δ̄ − T̂(a), 0}, với Δ̄ là trung
  bình chạy của khoảng giữa các nhịp. Riêng ở s10 cộng như vậy là chủ ý: thiết bị vẫn giữ kết nối.
- N_rem(t) = (H − t) / Δ̄(t), H là thời gian phục vụ mục tiêu của một lần sạc (§9.4), Δ̄(0) = 0,8 s
  (danh định), sau đó là trung bình chạy của khoảng giữa các nhịp đã thấy. Dùng N_rem ≥ K để tránh chia
  cho số nhỏ ở cuối.
- Tham số: K = 100 (≈ 80 s), EMA 0,3, D = 500 ms. V chọn theo §12.
- Hòa: chọn s nông hơn, rồi ρ nhỏ hơn (tất định).
- Triển khai Python có hai bản: float64 (để phân tích) và float32 (cho port C, kiểm S8).

## 7. Baseline

Mọi phương pháp chạy trên **cùng trace nhịp, trace kênh, trace tải, phiên đo được gán và cùng pin**,
cùng tập S và cùng bộ lọc tiện ích. Khác nhau chỉ ở luật chọn.

| Tên | Luật chọn | Ghi chú |
|---|---|---|
| Device-only | luôn s10, **tắt radio** giữa các nhịp (P_idle,off) | có lợi cho baseline; báo Π(s10) |
| Edge-only | luôn (s0, ρ0) | báo tỉ lệ vi phạm Π_min (dự kiến 100 %) |
| Static-best | một cặp cố định trong A* cho cả trace, chọn **có biết trước** trace đánh giá: N_ok lớn nhất, hòa thì T̄ nhỏ nhất | lợi thế hindsight cho baseline |
| Neurosurgeon | argmin T̂ trên {(s, ρ0) : s ∈ S}, không xét Π, không xét pin | dùng t_dev, t_edge đo được (có lợi cho baseline); báo vi phạm Π_min; báo thêm bản chạy trên đủ s0–s10 |
| Neurosurgeon-Π | argmin T̂ trên F (có Π, có D) | so sánh công bằng |
| Energy-greedy | argmin Ê trên F, không có ngân sách | F rỗng thì argmin T̂ |
| Battery-weighted greedy | argmin (1 − w) · T̂/D + w · Ê/E_b(0) trên F, w = 1 − b(t)/b(0) | dạng w(b) của Lộ trình 1.2; dự phòng cho bản hội nghị |
| Oracle | biết trước toàn bộ r(t), tải, năng lượng thật; thư giãn Lagrange: mỗi nhịp chọn argmin của M · 1{T > D} + T + μ · E trên A*, với T, E thật; μ ≥ 0 tìm bằng chia đôi để tổng năng lượng ≤ b(0) trong H, M = 10⁶ ms | mốc trên tham khảo; báo "% Oracle". Không gọi là tối ưu chứng minh được (hàng đợi phía thiết bị gây ghép giữa các nhịp) |

Không chạy Edgent và BottleNet++: cả hai cần đổi kiến trúc mô hình. Nêu trong Related Work và Table I.

## 8. Ablation

| Biến thể | Định nghĩa | Vai trò |
|---|---|---|
| Full | §6 | — |
| **Depth-only** (= "w/o protection") | chỉ ρ0: A* gồm (s, ρ0) với Π(s, ρ0) ≥ Π_min | **tiêu chí N2** (§13) |
| **Fixed budget** | E_b = b(0)/N_rem(0) giữ nguyên, không tính lại (K = ∞) | **tiêu chí N1** (§13) |
| w/o battery | Z ≡ 0 (gần trùng Neurosurgeon-Π) | chỉ báo |
| w/o joint | chọn s theo argmin V · T̂ + Z · Ê với chi phí ρ0, không xét Π; rồi lấy ρ nhỏ nhất đạt Π_min tại s đó; không có ρ nào thì về s10 | chỉ báo. Biến thể "fallback sang s kế tiếp" trùng Full (mệnh đề §2), nêu trong bài |
| Always-strongest | ρ ≡ ρ mạnh nhất có ở mỗi s (ρ2; s0 và s10 giữ nguyên) | chỉ báo: E7, macro-F1, accuracy DPU, Π |
| w/o queue | q̂ ≡ 0 (vẫn nhận notify, vẫn tốn năng lượng nhận) | chỉ báo |
| w/o channel | r̂ ≡ r_k danh định | chỉ báo |

## 9. Trace (khai trước)

Mọi trace sinh bằng splitmix64 + Fisher–Yates của `week9_common`, seed ghi trong manifest. Trace dùng
để chọn V (dev) và trace đánh giá (eval) không bao giờ trùng seed hay trùng bản ghi.

### 9.1 Nhịp đến

- **A-ecg (chính cho E7)**: thời điểm đỉnh R thật từ chú thích MIT-BIH (360 Hz), nối các bản ghi theo
  thứ tự hoán vị theo seed, mỗi nhịp một lần suy luận (Δ trung bình ≈ 0,8 s, nhịp tim đổi theo bệnh
  nhân). Chỉ dùng **thời điểm**, không dùng nhãn hay dự đoán. Phân chia: G5-early có dev = 11 bản ghi
  DS1, eval = 11 bản ghi DS1 còn lại (chia theo seed 20261113); G5-final có dev = 22 bản ghi DS1, eval
  = 21 bản ghi DS2 (bỏ 202), mở sau khi DS2 đã mở theo protocol của SV3.
- **A-per**: tuần hoàn Δ ∈ {0,8 (chính cho E5, E6, E8); 2; 5; 10} s. Dùng để thấy vùng áp dụng: từ
  Δ ≈ 2,6 s trở lên, s10 tắt radio rẻ hơn s2 giữ kết nối (P_conn 1,46 mW net ở interval 15 ms).

### 9.2 Kênh

- **C-static**: trạng thái chính k0 = (2M, công suất phát mặc định, interval 15 ms), r = r_k0 đo được.
- **C-ge** (tổng hợp, chỉ G5-early và độ nhạy): Gilbert–Elliott hai trạng thái trên hệ số goodput
  g ∈ {1, γ}, thời gian lưu theo phân phối mũ, trung bình 60 s ở trạng thái tốt và 10 s ở trạng thái
  xấu; γ chính 0,3, quét {0,5; 0,3; 0,15}. Trong bài ghi rõ đây là trace tổng hợp.
- **C-real** (chính cho G5-final): ≥ 3 file ghi thật, mỗi file ≥ 10 phút, gồm r(t) và RSSI mỗi 1 s,
  mang dongle di chuyển (tuần 14+). Trace dài hơn file thì nối các khối 60 s lấy mẫu lại theo seed.
- **C-1M**: cả trace ở trạng thái 1M (α, β, P_conn của 1M). Độ nhạy theo lớp kênh.

### 9.3 Tải edge

- **L0**: không có job nền.
- **L-blk**: khối 20 s, λ ∈ {0, 15, 30} job/s chọn ngẫu nhiên, cùng cấu trúc phiên đo W10-D3.
- **L-burst (chính)**: on-off. Trạng thái OFF λ = 5 job/s, ON λ = 30 job/s (vượt năng lực ≈ 22 job/s,
  hàng đầy, chờ ≈ 0,4 s), mỗi trạng thái kéo dài theo phân phối mũ, trung bình ON 20 s; tỉ lệ thời
  gian ON φ chính 0,2, quét φ ∈ {0; 0,1; 0,2; 0,3; 0,5}. Job đến theo Poisson trong từng trạng thái.
- **L-steady** (thêm ở v1.1): tải nền Poisson hằng λ ∈ {0, 5, 10, 15, 18, 20, 22} job/s cả trace. Dùng để vẽ
  đường lợi ích theo mức tải: theo ước lượng từ số đo, đánh đổi E–T chỉ có khi q nằm trong một dải hẹp
  (s10 nhanh hơn s2 nhưng s2 vẫn kịp D), nên đường này cho thấy vùng nào controller có giá trị, thay vì
  dựa vào một điểm tải.
- **L-real** (G5-final, nếu SV2 có trace E8 nhiều client): dùng thay L-burst ở một dòng độ nhạy,
  không thay kịch bản chính.

Trace chính bắt buộc có đoạn tắc nghẽn (φ > 0). Kịch bản không tắc nghẽn vẫn chạy và báo: theo ước
lượng từ số đo, lúc đó mọi phương pháp tiết kiệm năng lượng chọn cùng một cặp (S9, §15).

### 9.4 Pin

- Thời gian phục vụ mục tiêu H = độ dài trace nhịp eval (G5-final: 21 bản ghi × 30 phút ≈ 10,5 h, đúng
  một lần sạc trong ngày của thiết bị đeo). Chạy đến hết H hoặc hết pin.
- Dung lượng pin quy theo độ chặt κ: b(0) = κ · N_arr · Ē_ref, với N_arr là số nhịp của trace và Ē_ref
  là năng lượng trung bình mỗi nhịp (gồm nghỉ) của **energy-greedy** chạy không giới hạn pin trên chính
  trace đó. κ chính = 1,2; quét κ ∈ {0,8; 0,9; 1,0; 1,1; 1,2; 1,5; 2,0; 3,0}. Trong bài kèm quy đổi κ
  sang mAh ở 3,7 V cho một trace điển hình (chỉ để minh họa).
- Cách đọc b(t) giống fuel gauge: năng lượng còn lại thật, lượng tử hóa 1 % của b(0).
- Tải ngoài mô hình u (các khối khác của thiết bị tiêu năng lượng, controller không biết): chính u = 0;
  quét u ∈ {0; 0,05; 0,1; 0,2} × E_b(0)/Δ̄, công suất ngẫu nhiên đổi mỗi 10 phút trong [0, 2u].
- Lý do định nghĩa theo κ: kết quả E7 được báo tương đối nên không phụ thuộc một dung lượng tự chọn.
  Toàn bộ đường theo κ đều được báo.

## 10. Kịch bản và thông số

Bộ thông số chính **P\***: A-ecg, C-ge (early) hoặc C-real (final), L-burst φ = 0,2, k0, D = 500 ms,
Π_min = 0,5, κ = 1,2, u = 0, K = 100, V theo §12, mã hóa lớp liên kết bật (final).

| Thí nghiệm | Trace | Mục đích | Đầu ra |
|---|---|---|---|
| E5 kênh tĩnh | A-per 0,8; C-static; L0 và L-blk | kết quả chính khi kênh ổn định | Fig. 7: T̄ theo Ē của mọi phương pháp, kèm đường Pareto của Full khi quét V |
| E6 kênh động | A-per 0,8; C-ge/C-real; L0 | thích nghi theo kênh | Fig. 8 |
| **E7 pin** | **P\*** | **N1, N2** | Fig. 9: SoC theo thời gian, N_ok; đường N_ok theo κ |
| E8 tải bùng phát | A-per 0,8; C-static; L-burst | giá trị của tín hiệu hàng đợi | Fig. 10: chuỗi thời gian q, s chọn, Z; đường lợi ích theo φ |
| E8b tải ổn định (v1.1) | A-ecg, C-static, L-steady theo λ, các thông số khác như P\* | vùng tải mà controller có giá trị | đường N_ok, T̄ của mọi phương pháp và d_X theo λ |
| E9 ablation | P\* | tách đóng góp | Table VI |
| E11 độ nhạy | P\*, đổi từng thông số | chứng minh không chọn thông số có lợi | Fig. 12 |

Độ nhạy E11 (mỗi lần đổi một thông số, giữ các thông số khác ở P\*): V (lưới §12); Π_min ∈ {0; 0,1; …;
0,9}; D ∈ {300, 400, 500, 700, 1000} ms; κ; φ; Δ (A-per); K ∈ {10, 100, 1000, ∞}; γ; u; C-1M; năng
lượng theo trung bình phiên nhỏ nhất và lớn nhất (W9-D12); Π lấy cận dưới CI95 thay cho điểm ước
lượng; E_ctrl và năng lượng notify ×{0, 1, 10} số đo; E_prot(ρ2) ×10 (early). Với D = 300 ms, s10 không
bao giờ kịp hạn (T(s10) ≈ 377 ms): giá trị này được giữ trong lưới để báo đúng vùng không khả thi.

## 11. Chỉ số

Tính cho từng trace seed:

- **N_ok** (chỉ số chính E7): số nhịp được phục vụ xong với T ≤ D trước khi hết pin, trong H. Báo kèm
  tỉ lệ phục vụ σ = N_ok / N_arr.
- Tỉ lệ trễ hạn (trên các nhịp được phục vụ), thời gian sống (lúc hết pin, hoặc H), T trung bình, p95,
  p99; Ē mỗi nhịp; số lần đổi (s, ρ); tỉ lệ dùng từng cặp.
- Tiện ích: G5-early báo macro-F1 kỳ vọng (macro-F1 offline của từng cặp, trọng số theo tần suất dùng),
  ghi rõ là xấp xỉ. G5-final tính macro-F1 thật của lần chạy từ dự đoán DPU từng nhịp DS2 của cặp được
  chọn (cần dự đoán từng nhịp theo (s, ρ) từ SV2/SV3).
- Riêng tư: tỉ lệ nhịp vi phạm Π_min; Π trung bình theo tần suất dùng.
- So với Oracle: N_ok / N_ok,Oracle, và T̄ − T̄_Oracle.
- N3 phụ: sai lệch tương đối (Σ Ê − Σ E thật) / Σ E thật, theo phương pháp.
- Ràng buộc chấp nhận một phương pháp (Lộ trình 11.3): tỉ lệ trễ hạn ≤ 5 % và tiện ích đạt lọc §2. Không
  đạt thì vẫn báo số, đánh dấu "không đạt ràng buộc".

## 12. Chọn V và khóa

- Lưới V = 10^{0; 0,5; 1; …; 6} µJ²/ms (13 điểm).
- Chỉ dùng trace dev (A-ecg dev, 10 seed 1–10, các thông số khác như P\*).
- Luật: chọn V có N_ok trung bình lớn nhất. Nếu nhiều V cách giá trị lớn nhất không quá 0,5 % thì chọn
  V có T̄ nhỏ nhất trong số đó, còn hòa thì chọn V nhỏ hơn.
- V chọn xong ghi vào manifest, rồi mới chạy eval. Không chọn lại V sau khi đã chạy eval. Đường theo V
  trên eval chỉ báo trong E11.
- Baseline có tham số (battery-weighted greedy) không có tham số tự do, nên không cần chọn.

## 13. Tiêu chí G5 và nhánh quyết định

Seed eval: 30 seed (101–130) cho mỗi lượt. So sánh **theo cặp cùng seed**. Gọi d_X là khoảng kém tương
đối của X so với Full trên mỗi seed: d_X = (N_ok,Full − N_ok,X) / N_ok,Full.

- **N2 đạt** khi ở P\*: mean d_depth-only ≥ 5 % **và** cận dưới CI95 của d_depth-only > 0. Nếu điểm
  Π_min = 0,5 không đạt, N2 vẫn đạt khi điều kiện này đúng ở ≥ 3 điểm liên tiếp của lưới Π_min trong
  {0,3; …; 0,8} ("dải đáng kể"). Trường hợp này báo rõ là đạt theo dải.
- **N1 đạt** khi ở P\*: mean d_fixed-budget ≥ 10 % **và** cận dưới CI95 > 0.
- w/o joint, w/o battery, always-strongest, w/o queue, w/o channel: chỉ báo, không có ngưỡng.
- Câu chính cho abstract, khai trước: Full so với Neurosurgeon-Π và so với baseline không hindsight mạnh
  nhất (N_ok lớn nhất trong Neurosurgeon-Π, energy-greedy, battery-weighted greedy) ở P\*, kèm % Oracle.

Nhánh, theo quyết định 05/11:
1. Sau Π thử tuần 11 (trước G5-early): s2 trượt Π_min ở ρ0 nhưng đạt ở ρ1 hoặc ρ2 → kịch bản chính,
   N2 đứng đầu. s2 đạt sẵn ở ρ0 → giữ Π_min = 0,5, dùng lượt quét Π_min để tìm dải mà bảo vệ có ích
   (khi đó N2 chỉ có thể đạt "theo dải"). Π không tăng theo s, hoặc ρ1, ρ2 không nâng được Π → SV1 quyết
   chuyển T4 trong tuần 12.
2. G5-early (cuối tuần 13): N2 và N1 cùng đạt → giữ đúng cấu trúc bài. N2 đạt, N1 không → N2 và N3 dẫn
   bài, controller là cơ chế thực thi, bỏ câu "N1 ≥ 10 %". N1 đạt, N2 không → N1 và N3 dẫn bài, bảng Π(s, ρ)
   giữ làm kết quả đo; SV1 xem lại tên bài. Cả hai không đạt → chuyển T4 (bài đo đạc: LUT đo bằng phần
   cứng, sai số mô hình, vùng áp dụng theo Δ, φ, κ).
3. G5-final (tuần 19) là kết quả của bài. Early đạt mà final không đạt → báo số final, SV1 quyết theo
   mục 2.

## 14. Thống kê

- Chỉ số liên tục theo seed: mean ± CI95 Student-t (n = 30 seed). Khoảng kém theo cặp: mean ± CI95 của
  d_X, kiểm Wilcoxon signed-rank (chính xác), báo p chính xác, hiệu chỉnh Holm–Bonferroni trên họ so
  sánh Full với mọi baseline và ablation theo N_ok.
- Tỉ lệ (trễ hạn, vi phạm Π): Wilson score trên số nhịp gộp, kèm khoảng theo seed.
- So nhiều phương pháp: Friedman + Nemenyi, có biểu đồ critical difference (báo kèm, không quyết định).
- Effect size: Cliff's δ ghép cặp.
- Không bỏ seed nào. Seed lỗi do bug thì sửa bug, chạy lại **mọi** seed của mọi phương pháp, giữ cả hai
  kết quả và ghi khác biệt.

## 15. Kiểm tra đúng đắn (phải đạt trước khi đọc kết quả)

| Mã | Kiểm | Đạt khi |
|---|---|---|
| S1 | Full với Z ≡ 0 và Neurosurgeon-Π trên cùng seed | chuỗi a_n trùng hoàn toàn |
| S2 | Full với V = 10⁻⁹ khi Z > 0 | chọn trùng energy-greedy ở mọi nhịp có Z > 0 |
| S3 | Bảo toàn năng lượng: tổng các pha + nghỉ + notify = b(0) − b(cuối) | lệch tương đối ≤ 10⁻⁹ |
| S4 | Bất đẳng thức hàng đợi ảo theo đường mẫu: Σ(Ê_n − E_b) ≤ Z(cuối) − Z(0), từng epoch | đúng mọi epoch |
| S5 | Tất định: chạy hai lần cùng seed | SHA-256 file kết quả trùng |
| S6 | Phát lại chu kỳ s2 đo với KV260 (q = 0, r và thời gian đo được) | Ê trung bình khớp E_cycle đo ≤ 5 %; báo số lệch (N3) |
| S7 | Oracle so với mọi phương pháp không hindsight | N_ok,Oracle ≥ N_ok,X ở mọi seed; không đạt thì báo và tìm nguyên nhân, không giấu |
| S8 | Controller float32 so với float64 | trùng ≥ 99,9 % số nhịp |
| S9 | φ = 0, C-static, A-per 0,8 | energy-greedy, battery-weighted greedy và Full (mọi V trong lưới) chọn cùng cặp; ghi là kết quả mong đợi "không có đánh đổi E–T khi không tắc nghẽn" |
| S10 | Mệnh đề cấu trúc: Full duyệt đủ 8 cặp so với duyệt A* | chuỗi a_n trùng hoàn toàn |

## 16. Đầu vào và nguồn

| Đại lượng | Nguồn | Có cho G5-early | Có cho G5-final |
|---|---|---|---|
| t_dev(s), E_dev,on(s) | SV1 tuần 10 (W10-D4), mọi s | có | có (đo lại khác ngày, tuần 13) |
| E_dev,off(s), B(s) | SV1 tuần 9 (Bảng III) | có | có |
| E_prot(ρ2), t_prot(ρ2) | SV1 tuần 14–15 | tạm (§4.1) | có |
| α_k, β_k, P_x, P_conn(k) | SV1 tuần 11 | có (không mã hóa) | có (mã hóa bật) |
| a_k, b_k của E_wait | SV1 tuần 10 (W10-D3) | có | có |
| t_edge(s, ρ), t_rx, t_switch, t_svc | SV2 tuần 10, log KV260 | có (ρ0) | có (mọi ρ) |
| Năng lượng notify, E_ctrl, t_ctrl | SV1 T17, marker D4 (tuần 14+) | tạm (§4.2, §3) | có |
| Π(s, ρ) | SV3: thử DS1 tuần 11; DS2 chính thức | thử | chính thức |
| macro-F1 DPU val (s, ρ) | SV2 + SV3 (gói A, gói B) | gói A; gói B ứng viên | có |
| Dự đoán DPU từng nhịp DS2 | SV2 + SV3 | không | có |
| Trace kênh thật | SV1 + SV2 (tuần 14+) | không (C-ge) | có |

Mọi đầu vào vào mô phỏng qua `lut.json` (contract I3 v1, SV1 soạn cuối tuần 12, ba người xác nhận tuần
13) và manifest trace. Không chép số tay vào code. Thiếu đầu vào ở cột "có" thì lượt chạy đó chưa được
chạy; không thay bằng số đoán, trừ các giá trị tạm đã khai ở §3, §4.

## 17. Khóa, tái lập, thay đổi

- Trước mỗi lượt (early, final) commit cùng lúc: SHA của `lut.json`, manifest trace (seed + SHA), commit
  code mô phỏng, V đã chọn. Chạy eval **một lần**. Kết quả lưu ở `results/g5_sim/<lượt>/` kèm manifest
  SHA-256 và dữ liệu theo seed (CSV).
- Báo mọi phương pháp ở mọi kịch bản đã khai, kể cả kết quả bất lợi. Hạn chế bắt buộc nêu trong bài:
  trace kênh tổng hợp (early); một thiết bị, một edge; pin mô phỏng bằng tích lũy năng lượng ở 5 V
  (hiệu suất REG0 ở 3,7 V khác); Π là đo thực nghiệm dưới một họ tấn công; Oracle là mốc Lagrange,
  không phải tối ưu chứng minh được.
- Sửa protocol: tạo bản v1.x, ghi lý do, ngày, và mục sửa là trước hay sau khi thấy Π hoặc kết quả mô
  phỏng (**[sau Π]**, **[sau đo]**, **[sau mô phỏng]**). Sửa sau khi thấy kết quả mô phỏng thì báo cả
  hai kết quả trong bài hoặc phụ lục.

### Lịch sử phiên bản

| Bản | Ngày | Nội dung | Thấy Π / kết quả? |
|---|---|---|---|
| v1 | 12/11/2026 | Bản đầu, khóa trước khi có Π thử, E_tx(B), số đo tuần 10 | chưa thấy |
| v1.1 | 12/11/2026 | Thêm L-steady (§9.3) và E8b (§10). Lý do: ước lượng từ số đo tuần 9 cho thấy ở pha quá tải của L-burst mọi phương pháp đều phải chọn s10, nên một điểm tải không đủ. Kịch bản chính P\*, tiêu chí N1, N2 giữ nguyên | chưa thấy |
