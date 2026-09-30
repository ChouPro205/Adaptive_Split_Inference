# SV3 to SV2 Week 3 FP32 reference contract

Status: **CONFIRMED** by team authority relayed by the user on 2026-10-01.
The authoritative executable mapping is in
[interface config](../ml/configs/week3_sv2_interface_review.json).
The historical filename is retained; its current status is CONFIRMED, not REVIEW.
The 2026-09-30 review config/audit are preserved under ml/provenance/week3/history/.

Model name/version: mitdb_week2_cnn_v1, MIT-BIH/1.0.0, epoch 3, unchanged checkpoint
SHA-256 9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90.
L=10 counts eight Conv1d and two Linear layers. s counts weighted layers in head.
ReLU belongs to its preceding weighted layer, MaxPool to its preceding even Conv.
Flatten and inactive Dropout prepare layer 9. Use eval mode throughout.

| s | Head endpoint | z_s N=1 | Layout | Tail starts |
|---|---|---|---|---|
| 0 | Normalized input / identity | (1,1,360) | NCL | features.0 |
| 1 | features.1 ReLU1 | (1,16,360) | NCL | features.2 |
| 2 | features.4 Pool2 / accepted P2 | (1,16,180) | NCL | features.5 |
| 3 | features.6 ReLU3 | (1,32,180) | NCL | features.7 |
| 4 | features.9 Pool4 | (1,32,90) | NCL | features.10 |
| 5 | features.11 ReLU5 | (1,48,90) | NCL | features.12 |
| 6 | features.14 Pool6 | (1,48,45) | NCL | features.15 |
| 7 | features.16 ReLU7 | (1,64,45) | NCL | features.17 |
| 8 | features.19 Pool8 | (1,64,22) | NCL | classifier.0 |
| 9 | classifier.3 ReLU after Linear1 | (1,32) | NC | classifier.4 |
| 10 | classifier.4 Linear2 logits | (1,5) | NC | Identity / no edge compute |

All activations are float32 C-order. Export exactly tail_0.onnx through tail_9.onnx,
ONNX opset 13 **CONFIRMED**, fixed batch 1, no dynamic dimensions. No tail_10.onnx.
Input is input_activation=z_s; output logits is pre-softmax AAMI float32 (1,5),
class order N/S/V/F/Q. Argmax is outside ONNX. s=0 is edge-only, s=10 device-only.
The reference split_id equals s. This does not allocate I1 wire IDs: I1 wire 0
remains reserved, and deployment/session/protocol mapping is a separate contract.

Use the same 20 sample IDs/order/inputs as immutable SV1 v2. Exact frozen Week 1
preprocessing occurs before head inference; no preprocessing inside tails and no
refit/second normalization. Never alter or relabel SV1 v2.

For every sample and s=0..9, PyTorch tail(head(x)) and ONNX tail(z_s) must be
compared to the original full PyTorch logits. ONNX error must be strictly <1e-3
for all 200 cases. Verify s=10 full head and identity separately. Preserve per-case
results and maxima, not averages. The package manifest requires an independently
trusted raw SHA-256 before parsing; delivered files are checked against its inventory.

SV3 delivers the FP32 reference, checkpoint/model code, golden activations/logits,
export/verifier scripts, provenance and reproducible evidence outside Git for binaries.
SV2 owns Vitis AI/operator compatibility, quantization, compiling .xmodel files,
DPU target compatibility, VART/KV260 execution and independent reporting. The FP32
<1e-3 criterion is NOT automatically an INT8/DPU acceptance threshold.
No SV2 ACCEPTED, VART/KV260/INT8/XMODEL PASS without real independent evidence.

See [handoff report](../ml/docs/week3_sv2_split_audit.md). Overall Week 3 remains
incomplete until required SV1 evidence and independent SV2 flow validation exist.
No Week 4 work is authorized by this contract.
