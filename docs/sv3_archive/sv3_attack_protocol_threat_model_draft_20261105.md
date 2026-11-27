# Protocol tấn công v1 và bản nháp threat model (gửi SV1 review)

Ngày 05/11/2026. Người lập: SV3. Trạng thái: **ứng viên, chưa khóa; chưa viết code tấn công, chưa chạy tấn công.**

| Mục | Đường dẫn |
|---|---|
| Protocol tấn công v1 | `ml/configs/mitdb_m1_attack_protocol_v1.json`, SHA-256 `869170470794aa2b1e7fca6eb217bc96b7eb0396be0720e39ca82cf79a19b5a0` |
| Nguồn | Bản chốt 03/11 câu 7–11; tin review của SV1 ngày 05/11, điểm 4 và mục 6a–6b |

Protocol ghi lại các quyết định đã có: kẻ tấn công là edge honest-but-curious; dùng 4 tấn công A1–A3 và B; Π tính bằng balanced accuracy; Π_min = 0,5; chia theo thời gian, bỏ ±30 s quanh mẫu 325.000; thử tuần 11 trên DS1 với N = 22; các nhánh đã khai trước; luật chọn điểm cắt giữa. SV3 đã kiểm lại từ metadata DS1 các số SV1 nêu: bỏ 1.681/50.995 nhịp; mỗi bệnh nhân còn 767–1.637 nhịp phía kẻ tấn công và 799–1.613 nhịp test; bệnh nhân đông nhất chiếm 6,59 % số nhịp.

## Cần SV1 quyết trước khi khóa

1. **N cho Π chính thức trên DS2:** 21 (bỏ 202, như câu 10 của bản chốt) hay 22 (theo cách viết ở điểm 4 tin ngày 05/11)?
2. **CI95 cho Π:** cách Wilson trên accuracy không còn áp dụng thẳng cho balanced accuracy. Ứng viên: bootstrap theo từng bệnh nhân trên các nhịp test, 2000 lần lấy mẫu, seed 20261105, lấy khoảng phân vị 95 % của balanced accuracy rồi đổi sang Π.
3. **Mô hình tấn công và ngân sách huấn luyện** (mục `attack_models_candidate`): kiến trúc bộ phân loại B và decoder A1, lr, số epoch, cách dừng sớm, số seed. Đây mới là ứng viên.
4. **Dữ liệu huấn luyện decoder trong lượt thử tuần 11:** dùng phía kẻ tấn công của 22 bản ghi DS1. Ở lượt chính thức thì dùng train DS1 làm dữ liệu phụ trợ, như câu 10.

## Bản nháp Section III: Threat Model and Privacy Metric (tiếng Anh, cho bản LaTeX)

**Adversary.** We consider an honest-but-curious edge server. It runs the agreed protocol but stores every tensor it receives and tries to (i) reconstruct the ECG window and (ii) re-identify the patient. The edge observes exactly the transmitted tensor at split point $s$: INT8 per-channel values with FP16 scales and, for $\rho_2$, the learned additive noise. It knows the network architecture, the tail weights, the protection algorithm and its parameters ($\lambda$, noise distribution), and it has auxiliary data drawn from the same distribution. Eavesdroppers on the radio link are handled by BLE LE Secure Connections (AES-CCM, implemented in nRF52840 hardware), enabled for every method in our experiments; $\Pi$ is therefore defined against the edge only. Physical and side-channel access, data poisoning and an actively malicious edge are out of scope.

**Attacks.** We evaluate three reconstruction attacks of increasing strength and one re-identification attack. A1 is a decoder trained with mean squared error. A2 adds a discriminator (GAN decoder). A3 is an adaptive attacker: A2 retrained on protected tensors with full knowledge of the protection. B re-identifies the patient from a single beat, in three variants: B-naive (trained on unprotected tensors at the same $s$), B-adaptive (trained on protected tensors) and B-rec (applied to signals reconstructed by A3).

**Privacy metric.** Let $N$ be the number of identities and $\mathrm{bacc}$ the balanced accuracy of B on held-out beats, i.e. the mean per-patient recall. Balanced accuracy is used because beat counts differ between patients, so always predicting the largest patient already exceeds $1/N$. We define the adversary's advantage and the privacy level as

$$\mathrm{Adv}(s,\rho)=\operatorname{clip}_{[0,1]}\frac{\mathrm{bacc}-1/N}{1-1/N},\qquad \Pi(s,\rho)=1-\max_{B\in\{\text{naive},\text{adaptive},\text{rec}\}}\mathrm{Adv}_B(s,\rho).$$

$\Pi=1$ means the strongest attacker does no better than chance; $\Pi=0$ means it re-identifies every patient. A configuration is admissible only if $\Pi(s,\rho)\ge\Pi_{\min}$, with $\Pi_{\min}=0.5$ fixed before any measurement and a sensitivity sweep over $\Pi_{\min}\in\{0,0.1,\dots,0.9\}$. Reconstruction quality of A1–A3 (NRMSE, Pearson correlation, R-peak error) is reported separately and is not folded into $\Pi$, because it lives on a different scale. A low distance correlation alone is not treated as a privacy guarantee.

**Protocol.** Identities are MIT-BIH patients unseen in training. In every record, beats whose R peak lies within 30 s of the record midpoint (sample 325 000) are discarded; earlier beats train the attacker (the last 20 % of them for its validation), later beats are used for testing. DS2 is used only for this evaluation, never to choose protection parameters, which are fixed on DS1 validation beforehand. A preliminary run on DS1 patients, who were seen during training, serves only as an early warning and does not contribute to reported results.

**Limitations.** The number of identities is small (one MIT-BIH split). Sex and age inference is not evaluated, and larger cohorts such as PTB-XL are left for future work.
