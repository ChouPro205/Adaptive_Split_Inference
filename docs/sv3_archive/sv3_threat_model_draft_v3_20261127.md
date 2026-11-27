# Bản nháp threat model, bản 3 (Section III), gửi SV1 review

Ngày 27/11/2026. Người lập: SV3. Nhánh `dev/ml-sv3`.

**Trạng thái:** bản nháp, chờ SV1 đọc lại. Bản này thay bản 2 ([`sv3_threat_model_draft_v2_20261127.md`](sv3_threat_model_draft_v2_20261127.md), giữ nguyên), theo mục 4 tin 27/11 của SV1 (`ml/provenance/m1-sv1-evidence-20261127/`, SHA `696f3309…`). Bản 2 đã sửa theo:
- review ngày 25/11 của SV1, mục 4;
- Hướng xử lý ASI bản 3;
- attack protocol v3 r5 đã khóa (`9235b795…`, file khóa `b3a89cbb…`).

**Về số liệu:**
- Chỗ ghi `[DS1]` là số phần a, b, c, d trên DS1. Các số này đã có từ 27/11 (receipt a, b, d `e3996a01…`, receipt c `2e571b70…`) nhưng chỉ là số phát triển và cảnh báo sớm, nên thân bài vẫn để chỗ trống.
- Chỗ ghi `[DS2]` là số của lượt DS2 riêng tư (tuần 14).
- Trong thân bài chưa có số nào. Số lượt thử 13/11 chỉ là cảnh báo sớm, không đưa vào bài.

## Những gì đổi so với bản 2

| Mục | Bản 2 | Bản này | Theo |
|---|---|---|---|
| Câu mở đầu "Leakage budget" | "Offloading actions cannot hide identity", khẳng định trước khi có kết quả | Câu điều kiện: không hành động gửi nào che được danh tính, trừ khi một cấu hình có nhiễu đạt; nếu đạt thì có thêm chế độ che danh tính, giá báo ở Section V | Tin 27/11 mục 4(c) |
| Nhịp gửi có nhiễu | Không nói | Vẫn tính là gửi trong ràng buộc tỉ lệ tại chỗ ≥ p, vì Y giới hạn nội dung ECG chứ không giới hạn danh tính | Tin 27/11 mục 4(c) |
| Ý "Identity" trong ngân sách | Danh tính chỉ được che khi cả phiên ở lại thiết bị hoặc bằng chính sách theo phiên (ngoài phạm vi) | Thêm: hoặc bằng chế độ che danh tính nếu có cấu hình đạt. Sửa cho khớp câu mở đầu mới | Theo câu mở đầu mới |
| "Cost" | Một mục riêng, trỏ tới G5 | Một câu trỏ sang Section V. Câu "virtual queue" chuyển sang Section IV (xem ghi chú cuối) | Tin 27/11 mục 4(a) |
| Số byte S0c | "about 36 B", theo phép thử 20/11 | 36,4 B trung bình trên DS1 validation (9.523 nhịp; p95 41 B, tối đa 44 B), cộng 2 B scale; số chính thức `[DS2]` | Tin 27/11 mục 4(b) |

## Những gì bản 2 đổi so với bản 20/11

| Mục | Bản 20/11 | Bản này | Theo |
|---|---|---|---|
| Ngân sách rò rỉ | (1/T)·Σ(1 − Π(a_t)) ≤ ε, trọng số theo Π, hỏi SV1 chọn trọng số | Tỉ lệ nhịp gửi dữ liệu đi ≤ 1 − p, tức tỉ lệ nhịp xử lý hoàn toàn tại chỗ ≥ p. Bỏ câu hỏi trọng số và công thức p ≈ 1 − ε/(1 − Π̄). Π và mức dựng lại chỉ báo kèm | Review 25/11 mục 4; ASI bản 3 |
| S0 | Nhịp thô 362 B | S0 chuẩn là S0c: gom 46 giá trị, INT8 với scale FP16, mã Rice; thân trung bình khoảng 36 B cộng 2 B scale (bản 3 ghi số chính xác) | Review 25/11 mục 4; S0c v1 |
| Cận ghép | "Gửi nhịp thô không thể riêng tư hơn gửi activation" | Đúng cho S0 thô (sai khác chỉ do lượng tử). Với S0c, bước gom làm mất thông tin nên cận chỉ đúng tới sai số của bước gom, và được **đo** bằng tấn công ghép | Review 25/11 mục 4 |
| Bảo vệ bằng nhiễu | Đối chứng cộng nhiễu lên nhịp thô ở s0; luật đạt chỉ có Π | Đối chứng C0c (nhiễu trên 46 giá trị S0c). Luật đạt gồm macro-F1, Π theo nhịp, Π_k10 (đa số, mềm, trung bình; liên tiếp, rải rác; mọi kẻ tấn công, kể cả kẻ tấn công sạch ρ0), rồi xác nhận trên DS2 | Review 25/11 mục 1 và 4; r5 |
| Tấn công | B-naive, B-composite, B-adaptive | Thêm bỏ phiếu và trung bình theo k nhịp; nhiễu sinh mới mỗi epoch cho kẻ tấn công thích nghi; tấn công trên logits FP32 ở s10 | r5 |
| Lượt DS2 | Một lượt | Hai lượt: chất lượng (10/12) và riêng tư (tuần 14); mọi cổng macro-F1 trên DS2 tính tương đối theo A | r5 |

Không có câu hỏi mở nào cho SV1 trong bản này. Các điểm trong bản 20/11 đã được trả lời ở review 25/11.

---

## III. Threat Model and Privacy Evaluation

**System and assets.** A wearable device (nRF52840) classifies each heartbeat of a single-lead ECG with a 1D-CNN. For every beat the controller chooses an action: a split point and a BLE radio state.
- The standard full-offload action is S0c. The device reduces the normalized 360-sample beat to 46 bin averages, quantizes them to INT8 with one FP16 scale and Rice-codes the successive differences. On DS1 validation the payload is 36.4 B on average (9,523 beats; p95 41 B, max 44 B), body including the first value and the $k$ byte, plus the 2 B FP16 scale; the value for the evaluation set is `[DS2]`. The edge decodes the values, interpolates them back to 360 samples and runs the whole model.
- At an intermediate split $1\le s\le 9$ the device sends the INT8 activation $z_s$ with per-channel FP16 scales.
- At $s=10$ it classifies the beat locally and sends nothing to the edge.

The assets are (i) the clinical content of every beat that leaves the device and (ii) the identity of the patient behind the beats.

**Adversary.** We consider an honest-but-curious edge server (KV260). It runs the agreed protocol but keeps every tensor it receives, and it tries to reconstruct the ECG and to re-identify the patient. It observes exactly the transmitted payload. It knows:
- the architecture and all model weights, since it runs the tail;
- the quantization and the S0c codec;
- any protection mechanism together with its parameters, and it can draw fresh samples from the noise distribution at no cost;
- labelled auxiliary beats of the same patients.

Because the edge holds every operation after $s$, it can compute from $z_s$ the activation $z_{s'}$ of any deeper split $s'>s$ and the logits, and from an S0c payload the interpolated beat and everything after it. Our attacks exploit this explicitly.

Eavesdroppers on the radio link are handled by BLE LE Secure Connections (AES-CCM in nRF52840 hardware), which is enabled for every method, so privacy is defined against the edge only. Physical and side-channel access, data poisoning and an actively malicious edge are out of scope.

**What re-identification means here.** The edge already knows which device is sending, so learning "which device" is not the threat. The threat is linking a patient's beats to an identity known from another dataset or session, for instance a recording the adversary holds from elsewhere.

We measure this with closed-set re-identification of $N$ patients: the attacker is trained on the first part of each record and tested on the last part of the same record. Both parts come from one recording session, so identity is confounded with session features such as electrode placement and posture, and the task is easier than cross-session linking. MIT-BIH has one session per patient and cannot separate the two effects. The in-session advantage reported below is therefore an upper bound on the cross-session linking advantage.

**Attacks.**
- *Reconstruction.* A1 is a decoder trained with mean squared error to map the observed tensor back to the 360-sample beat. For S0c we report both the training-free edge interpolation and a trained refiner, whichever is better on attacker validation.
- *Re-identification of a single beat.* B is a classifier that predicts the patient from one observed beat, trained with three seeds. Per-beat log-probabilities are kept.
  - *B-naive* is trained on the tensors observed for the evaluated action.
  - *B-composite* uses the edge's ability to run the frozen layers. From the tensor observed at the source (for S0c, the interpolated beat) it computes the re-quantized tensor of a deeper split $s'$, including the FP32 logits at $s'=10$, and applies the attacker trained at $s'$.
  - *B-adaptive* applies to noise-based protection. It knows the mechanism and its parameters and is trained on noise drawn fresh in every epoch. Its composite form trains the deeper-split attacker on the same noisy pipeline, recomputed every epoch.
- *Re-identification from $k$ beats.* The edge sees many beats of the same patient. For $k$ beats we use three aggregators: a majority vote over the per-beat predictions, the sum of the per-beat log-probabilities, and the element-wise mean of the $k$ dequantized observed tensors fed to the attacker. The mean reduces independent per-beat noise by a factor $k$ in variance. Beats are taken either as consecutive blocks or as random draws within a patient.
- The privacy level of an action is set by the strongest of these attackers.

**Privacy metric.** Let $\mathrm{bacc}$ be the balanced accuracy of B on held-out beats, i.e. the mean per-patient recall. Balanced accuracy is used because beat counts differ between patients. We define

$$\mathrm{Adv}_B=\operatorname{clip}_{[0,1]}\frac{\mathrm{bacc}_B-1/N}{1-1/N},\qquad \Pi=1-\max_{B}\mathrm{Adv}_B,$$

where $\mathrm{Adv}_B$ is the mean over the three attacker seeds and the maximum runs over the attack variants available for the action.
- $\Pi=1$ means the strongest attacker does no better than chance; $\Pi=0$ means it re-identifies every beat.
- $\Pi_k$ is defined in the same way on blocks or draws of $k$ beats, with the maximum also taken over the three aggregators and the two ways of choosing beats. We report $\Pi_k$ for $k\in\{1,2,5,10,20,50,100\}$ and use $k=10$ as the decision value.
- The threshold $\Pi_{\min}=0.5$ was fixed before any measurement; we also report a sweep $\Pi_{\min}\in\{0,0.1,\dots,0.9\}$.
- Reconstruction quality (NRMSE, Pearson correlation, R-peak error) is reported separately and is not folded into $\Pi$.
- At $s=10$ nothing leaves the device, so $\Pi(10)=1$ by construction. The attack on the logits only bounds the privacy of actions that let the edge compute them.

**Reading $\Pi$ as a bound.** Every reported $\Pi$ is an upper bound on the true in-session privacy level, because a stronger attacker can only lower it. The two bounds point in opposite directions:
- with respect to attacker strength, measured $\Pi$ can only overstate in-session privacy;
- with respect to the session confound, in-session $\Pi$ understates cross-session privacy.

We therefore state our negative result for the in-session closed-set task. A conclusion of the form "no offloading action reaches $\Pi_{\min}$" is robust to attacker strength. It does not claim that cross-session linking would succeed equally well.

**Composite bound for one model.** When every split point shares one checkpoint, the edge that receives $z_s$ can reproduce $z_{s'}$ for every $s'>s$, up to the quantization error at $s$. Hence $\Pi(s)\lesssim\min_{s'\ge s}\Pi(s')$. In particular, sending the uncompressed beat (362 B) cannot be more private than sending any intermediate activation, up to quantization.

For S0c the same argument holds only up to the information removed by the reduction to 46 values, so we do not assume the bound. We measure it with the composite attack from the interpolated beat.

Without the composite attack, shallow splits would look more private only because a single-beat classifier on the raw signal is a weaker attacker. We report the composite-based $\Pi$. Measured values: `[DS1]`, `[DS2]`.

**Leakage budget used by the controller.** Unless a noise-protected configuration qualifies (below), no offloading action hides identity `[DS1]`, `[DS2]`. If one qualifies, the system also offers an identity-protected mode in which every offloaded beat uses a qualifying action; its price is reported in Section V. The data budget therefore does not keep $\Pi$ above $\Pi_{\min}$ for every beat. It is a long-term minimum on the fraction of beats that are processed entirely on the device:

$$\frac{1}{T}\sum_{t=1}^{T}\mathbb{1}\left[a_t\ \text{sends data}\right]\le 1-p,$$

where $a_t$ is the action for beat $t$ and $p$ is the required local fraction. A beat sent with noise protection still counts as sent, because the constraint limits the ECG content that leaves the device, not identity. Two points define what it protects:

1. *Asset.* The constraint limits how much clinical content leaves the device, following data minimization for medical data. It is a count of offloaded beats, not a weighted sum: $\Pi$ and reconstruction quality are reported for each action but are not used as weights.
2. *Identity.* The constraint does not hide identity. A few beats suffice to re-identify a patient: $\Pi_k$ versus the number $k$ of beats the edge sees per patient, consecutive or scattered, is reported in `[DS1]`, `[DS2]`. Identity is protected only if a whole session stays on the device, in the identity-protected mode if a configuration qualifies, or by a session-level policy, which is outside this work.

Its energy and $N_{\mathrm{ok}}$ price as a function of $p$ are evaluated in Section V.

**Protection mechanisms considered.**
- *NoPeek* (distance-correlation training, $\rho_1$) is reported as a result. It does not raise $\Pi$ at any evaluated split, so it is not part of the action set.
- *Additive noise.* Route R adds per-channel Gaussian noise to $z_2$ before quantization, with standard deviation $\alpha\sigma_c$. The control C0c adds Gaussian noise to the 46 reduced values of S0c before quantization and Rice coding; it is the cheaper device-side alternative. The classifier is frozen.
  - For each configuration, $\alpha$ is set on DS1 validation to reach 99, 98, 97 and 95 % of the unprotected macro-F1, and the two configurations are compared at equal macro-F1.
  - A configuration is selected on DS1 only if, at macro-F1 $\ge 0.95$ of the unprotected model, both the per-beat $\Pi$ and $\Pi_{10}$ reach $\Pi_{\min}$ against adaptive, composite and clean attackers. The $\Pi_{10}$ check covers all three aggregators.
  - If C0c qualifies, it is preferred, because it costs less on the device.
  - A selected configuration enters the action set only if the DS2 privacy round confirms the same conditions. On DS2 the attackers are retrained with the same recipe on DS2 patients, and the macro-F1 threshold is relative to the unprotected model on DS2.
  - Result: `[DS1 privacy-utility curves]`, `[DS2]`.
- *Encryption of the application payload* ($P_1$) does not change what the edge sees, so it has no effect on $\Pi$ against this adversary. It is not part of the action set.

**Evaluation protocol.**
- Identities are MIT-BIH DS2 patients, excluding record 202, which belongs to the same person as 201 in DS1 ($N=21$). None of them was seen in training.
- In every record, beats whose R peak lies within 30 s of the record midpoint are discarded. Earlier beats train the attacker (the last 20 % of them for its validation), and later beats are used for testing.
- 95 % confidence intervals use a within-patient block bootstrap: 2000 resamples, blocks of 10 consecutive test beats, identity set fixed. For $k$-beat draws we report the 2.5 and 97.5 percentiles over the draws.
- DS2 is opened twice, each time once: a quality round for the classifier and a privacy round for the attacks. DS2 is never used to choose any parameter.
- Development runs on DS1 patients, who were seen during training, served only for development and as an early warning and are not reported as results.

**Limitations.**
- The cohort is small ($N=21$) and has one session per patient, so in-session and cross-session re-identification cannot be separated.
- Re-identification is easy on this task, which partly explains the low $\Pi$ of every offloading action.
- Sex and age inference is not evaluated.
- The INT8 logits produced by the edge accelerator are not attacked separately; the FP32 logits stand for them. Omitting a variant can only leave $\Pi$ higher, so the reported values remain upper bounds.
- The composite attack is defined only when all splits share one model.
- Noise-based protection is evaluated with the classifier frozen, without noise-aware fine-tuning. A stronger reconstruction attack (a decoder with a discriminator that knows the noise) is run only if a noisy configuration is selected.

---

## Ghi chú cho SV1 (không đưa vào bài)

- Số byte S0c trong "System and assets" viết đúng nguồn SV1 đưa ngày 27/11, khớp `results/week11/device/analysis/compression-20261120/codec_results.json` trên main (`s0_rice_46`: 36,44 B, p95 41 B). Số chính thức để `[DS2]`, lấy từ lượt DS2 chất lượng.
- Câu chuyển sang Section IV (Châu viết), đề xuất: "The controller enforces the constraint of Section III through a virtual queue." Section III không còn câu này.
- $N_{\mathrm{ok}}$ giữ đúng tên trong tin 27/11; định nghĩa nằm ở Section V.
- Kết quả phần c trên DS1 (27/11, receipt `2e571b70…`): không cấu hình R2 hay C0c nào đạt luật ở DS1 (`selected_on_DS1` rỗng). Đây chỉ là cảnh báo sớm; câu mở đầu "Leakage budget" vẫn viết dạng điều kiện cho tới quyết định 13/12 và lượt DS2 riêng tư.
- Mục "Protection mechanisms" viết theo r5 đã khóa. Kết quả nhánh R (11/12) và quyết định 13/12 sẽ quyết đoạn này giữ dạng nào.
- Đường cong Π_k (phần d, ρ0) chỉ để thảo luận, không phải luật quyết định. Bài dùng nó làm bằng chứng cho ý "không che danh tính".
