# Bản nháp threat model (Section III), gửi SV1 review

Ngày 20/11/2026. Người lập: SV3. Nhánh `dev/ml-sv3`.

**Trạng thái:** đây là bản nháp, chưa review. Nó thay phần Section III trong `docs/sv3_attack_protocol_threat_model_draft_20261105.md`; file đó giữ nguyên. Bản này viết theo hướng ASI chốt 19/11 (bản 2), tin SV1 ngày 19/11 (mục 7) và ngày 20/11 (mục 3(3)), và attack protocol v3 r2 (`8fae0a4e…`, chưa khóa).

**Về số liệu:**
- Mọi chỗ ghi `[DS2]` là số chính thức, chưa có.
- Số lượt thử (DS1) chỉ dùng trong ghi chú cho SV1 ở cuối file, không đưa vào thân bài.
- Các phần phụ thuộc v3 (B-composite, s9/s10, ρ2) sẽ đổi theo bản v3 được khóa.

**Cần SV1 chốt** (lặp lại từ tin v3 r2):
1. Trọng số rò rỉ trong ngân sách: theo Π (tái định danh), hay theo chỉ số tái tạo (nội dung)?
2. Cách gọi ε hay p trong bài: có ghi rằng với Π hiện tại hai cách gần như tương đương không?

---

## III. Threat Model and Privacy Evaluation

**System and assets.** A wearable device (nRF52840) classifies each heartbeat of a single-lead ECG with a 1D-CNN. For every beat (or batch of beats) the controller chooses a split point $s\in\{0,\dots,10\}$ and a BLE radio state. At $s=0$ the device sends the quantized beat (362 B), at $1\le s\le 9$ it sends the INT8 activation $z_s$ with per-channel FP16 scales, and at $s=10$ it classifies the beat locally and sends nothing to the edge. The assets are (i) the clinical content of each beat that leaves the device and (ii) the identity of the patient behind the beats.

**Adversary.** We consider an honest-but-curious edge server (KV260). It runs the agreed protocol but keeps every tensor it receives and tries to reconstruct the ECG and to re-identify the patient. It observes exactly the transmitted tensor. It knows the architecture, all model weights (it runs the tail), the quantization, any protection mechanism and its parameters, and it holds labelled auxiliary data from the same distribution. Because the edge holds every operation after $s$, it can compute from $z_s$ the activation $z_{s'}$ of any deeper split $s'>s$ and the logits; our attacks exploit this explicitly. Eavesdroppers on the radio link are handled by BLE LE Secure Connections (AES-CCM in nRF52840 hardware), enabled for every method, so privacy is defined against the edge only. Physical and side-channel access, data poisoning and an actively malicious edge are out of scope.

**What re-identification means here.** The edge already knows which device is sending, so learning "which device" is not the threat. The threat is linking a patient's beats to an identity known from another dataset or session, for instance a recording the adversary holds from elsewhere. We measure this with closed-set re-identification of $N$ patients: the attacker is trained on the first part of each record and tested on the last part of the same record. Because both parts come from one recording session, identity is confounded with session features (electrode placement, posture), so this task is easier than cross-session linking. MIT-BIH has one session per patient and cannot separate the two effects. The in-session advantage reported below is therefore an upper bound on the cross-session linking advantage.

**Attacks.**
- *Reconstruction.* A1 is a decoder trained with mean squared error to map the observed tensor back to the 360-sample beat.
- *Re-identification.* B is a classifier that predicts the patient from one observed beat, trained with three seeds.
  - *B-naive* is trained on the tensors observed at the evaluated $(s,\rho)$.
  - *B-composite* uses the edge's ability to run the tail: from the tensor observed at $s$ it computes the observed tensor of a deeper split $s'$ (including the logits, $s'=10$) and applies the attacker trained at $s'$.
  - *B-adaptive* applies to noise-based protection. It knows the mechanism and its parameters and is trained on freshly drawn noisy tensors; its composite form trains the deeper-split attacker on the same noisy pipeline.
- The privacy level of a configuration is set by the strongest of these variants.

**Privacy metric.** Let $\mathrm{bacc}$ be the balanced accuracy of B on held-out beats, i.e. the mean per-patient recall. Balanced accuracy is used because beat counts differ between patients. We define

$$\mathrm{Adv}_B(s,\rho)=\operatorname{clip}_{[0,1]}\frac{\mathrm{bacc}_B-1/N}{1-1/N},\qquad \Pi(s,\rho)=1-\max_{B}\mathrm{Adv}_B(s,\rho),$$

where $\mathrm{Adv}_B$ is the mean over the three attacker seeds and the maximum runs over the attack variants available for $(s,\rho)$.
- $\Pi=1$ means the strongest attacker does no better than chance; $\Pi=0$ means it re-identifies every beat.
- The threshold $\Pi_{\min}=0.5$ was fixed before any measurement; we also report a sweep $\Pi_{\min}\in\{0,0.1,\dots,0.9\}$.
- Reconstruction quality of A1 (NRMSE, Pearson correlation, R-peak error) is reported separately and is not folded into $\Pi$.
- At $s=10$ nothing leaves the device, so $\Pi(10)=1$ by construction. The attack on the logits is used only as an upper bound for $s<10$.

**Reading $\Pi$ as a bound.** Every reported $\Pi$ is an upper bound on the true in-session privacy level, because a stronger attacker can only lower it. The two bounds above point in opposite directions:
- with respect to attacker strength, measured $\Pi$ can only overstate in-session privacy;
- with respect to the session confound, in-session $\Pi$ understates cross-session privacy.

We therefore state our negative result for the in-session closed-set task. A conclusion of the form "no configuration reaches $\Pi_{\min}$" is robust to attacker strength. It does not claim that cross-session linking would succeed equally well.

**Composite bound for one model.** When every split point shares one checkpoint, the edge that receives $z_s$ can reproduce $z_{s'}$ for every $s'>s$, up to the quantization error at $s$. Hence $\Pi(s)\lesssim\min_{s'\ge s}\Pi(s')$, and in particular sending the raw beat cannot be more private than sending any intermediate activation. Without the composite attack, shallow splits would look more private only because a single-beat classifier on the raw signal is a weaker attacker. We report the composite-based $\Pi$ and treat this ordering as an artefact. Measured values: `[DS2]`.

**Leakage budget used by the controller.** Split points that send data cannot hide identity, so the controller does not try to keep $\Pi$ above $\Pi_{\min}$ per beat. Instead it enforces a long-term budget on how much beat content leaves the device:

$$\frac{1}{T}\sum_{t=1}^{T}\bigl(1-\Pi(a_t)\bigr)\le\varepsilon,$$

where $a_t$ is the action for beat $t$ and $\Pi(a_t)$ is taken from the measured table; local classification ($s=10$) contributes $0$. The controller enforces the budget through a virtual queue. Three points define what this constraint does and does not protect:

1. *Asset.* The protected asset is the clinical content of each beat, in line with data minimization for medical data. It is not the patient's identity.
2. *Identity.* The budget does not hide identity. A handful of beats suffices to re-identify a patient: re-identification accuracy versus the number $k$ of beats the edge sees per patient, consecutive or scattered, is reported in `[DS2]`. Identity is protected only if a whole session is processed locally, or by a session-level policy, which is outside this work.
3. *Weight.* $1-\Pi$ is a re-identification advantage, used here as the per-beat leakage weight. With our measurements every offloading action has nearly the same weight (all $s<10$ have $\Pi$ far below $\Pi_{\min}$ and near-perfect reconstruction), so the budget behaves like a lower bound $p\approx 1-\varepsilon/(1-\bar\Pi)$ on the fraction of beats classified locally. Because each $\Pi$ is an upper bound, $1-\Pi$ is a lower bound on per-beat leakage, and the budget is optimistic rather than conservative. `[SV1: keep the Π-based weight, or use a reconstruction-based weight for the content asset?]`

**Protection mechanisms considered.**
- *NoPeek* (distance-correlation training, $\rho_1$) is reported as a result. It does not raise $\Pi$ at any evaluated split, so it is not part of the action set.
- *Additive noise* ($\rho_2$, per-channel Gaussian noise at $s=2$) is evaluated together with a control that adds noise to the raw beat and sends it at $s=0$. The two are compared at equal validation macro-F1, and $\Pi$ is computed with adaptive and composite attackers. A noisy configuration enters the action set only if it reaches $\Pi\ge\Pi_{\min}$ at macro-F1 $\ge 0.95\times$ that of the unprotected model. If the raw-beat control qualifies, it replaces the split-point variant, because it is cheaper on the device. Result: `[DS1 privacy-utility curves]`.
- *Encryption of the application payload* ($P_1$) does not change what the edge sees, so it has no effect on $\Pi$ against this adversary. It is implemented and measured but not part of the action set.

**Evaluation protocol.**
- Identities are MIT-BIH DS2 patients, excluding record 202, which belongs to the same person as 201 in DS1 ($N=21$). None of them was seen in training.
- In every record, beats whose R peak lies within 30 s of the record midpoint are discarded. Earlier beats train the attacker (the last 20 % of them for its validation), and later beats are used for testing.
- 95 % confidence intervals use a within-patient block bootstrap: 2000 resamples, blocks of 10 consecutive test beats, identity set fixed.
- DS2 is used only for this evaluation, never to choose any parameter.
- A preliminary run on DS1 patients, who were seen during training, served only as an early warning and is not reported as a result.

**Limitations.**
- The cohort is small ($N=21$) and has one session per patient, so in-session and cross-session re-identification cannot be separated.
- Re-identification is easy on this task, which partly explains the low $\Pi$ at every split.
- Sex and age inference is not evaluated.
- The INT8 logits produced by the edge accelerator are not attacked separately. Omitting a variant can only leave $\Pi$ higher, so the reported values remain upper bounds.
- The composite attack is defined only when all splits share one model.
- Noise-based protection is evaluated with the classifier frozen, without noise-aware fine-tuning.

---

## Ghi chú cho SV1 (không đưa vào bài)

- Số lượt thử DS1 (13/11), chỉ là cảnh báo sớm, đọc theo B-naive:
  - Π(s, ρ0) = 0,183 (s0); 0,100 (s2); 0,081 (s4); 0,076 (s5); 0,068 (s8).
  - ρ1 gần như bằng ρ0 ở mọi s.
  - A1 ở s2 có Pearson 0,999.
  - bacc theo phiên (bỏ phiếu 10 nhịp) ở s0 là 0,89–0,91.
  - Thứ tự giảm dần theo s là do kẻ tấn công ở s0 yếu. Phần b của v3 đo cận ghép.
- Đoạn "Composite bound" và "Leakage budget" dựa trên tin SV1 ngày 19/11 (mục 2) và 20/11 (mục 3(3)). Câu về p ≈ 1 − ε/(1 − Π̄) chỉ đúng khi mọi hành động gửi đi có cùng Π̄; SV1 kiểm giúp cách viết.
- Mục "Protection mechanisms" viết theo luật ρ2 trong v3 r2. Nếu SV1 sửa luật khi review thì đoạn này sửa theo.
