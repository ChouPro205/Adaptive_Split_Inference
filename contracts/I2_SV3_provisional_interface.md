# I2 — SV3 protection interface, approval draft

**Status: PROVISIONAL / NOT COMPLETE — BLOCKED_ON_GV_APPROVAL.** This is a Week 2 interface proposal for
SV3 → SV1/SV2. It is not an approved wire format or a P1 implementation.

## A. Fixed Project-source facts

The local Project requirements in
`ml/docs/project_sources/requirements/Huong1_Bao_cao_trien_khai_3SV.docx`,
`Huong1_Phan_cong_nhom_nghien_cuu.docx`, and
`Huong1_Huong_dan_chi_tiet_tung_thanh_vien.docx` assign I2 to SV3 for
SV1/SV2 and call for `protect()/unprotect()`, key/nonce rules, and test vectors.
P1 is channel permutation plus keyed affine masking of quantized intermediate
features. It requires a keyed PRNG and nonce input, must reverse bit-exactly,
and later must interoperate between Python and C. The sources mention
**xoshiro128\*\*** or **ChaCha20** as alternatives; neither is selected.
Shared-key management is outside the P1 implementation scope.

## B. Provisional interface proposal

### Team-review target deployment direction (new in PR #7 review)

The target I2 deployment activation format is **INT8**, with layout
**NCL = [N, C, L]** and **N MUST equal 1**. These are newly agreed interface
constraints, not a claim that Week 1 froze them or that the Week 2 PyTorch
baseline has been converted to INT8. FP32 remains the reference model/output
baseline for the later Week 3 model handoff and cross-platform comparison.

`protect()` and `unprotect()` MUST operate on the quantized activation byte
representation. `protect()` MUST preserve payload byte count, and the round
trip MUST reproduce the original activation bytes exactly. Validation MUST
check dtype, NCL layout, N == 1, shape, expected element and byte count,
model profile, split profile, and contract/version compatibility. For this
INT8 target, element count and activation byte count are N*C*L. Malformed or
mismatched profile inputs MUST be rejected rather than guessed. Concrete
profile registries and protection-specific error codes remain open.

These signatures specify roles only; the wire metadata and exact API types
remain provisional:

```text
protect(activation_bytes, shape_ncl, model_profile, split_profile, key, nonce, contract_version)
    -> protected_tensor, metadata

unprotect(protected_tensor, metadata, shape_ncl, model_profile, split_profile, key, nonce, contract_version)
    -> activation_bytes
```

Both sides need the same agreed contract version and enough metadata to recover
the original tensor shape and channel order. Acceptance should check
`unprotect(protect(z, ...), ...) == z` byte for byte on valid inputs, including
Python/C interoperability after implementation. Invalid key, nonce, shape, or
version behavior needs an explicit error contract before implementation.
No encryption or confidentiality claim is made by this draft.

## C. Open decisions requiring GV approval

| Decision | Current status |
|---|---|
| PRNG: xoshiro128\*\* or ChaCha20 | BLOCKED_ON_GV_APPROVAL |
| Key size, generation, provisioning, and identifier | BLOCKED_ON_GV_APPROVAL |
| Nonce size, uniqueness/reuse/replay policy, and transport representation | BLOCKED_ON_GV_APPROVAL |
| Byte order, integer representation, and exact Python/C serialization | BLOCKED_ON_GV_APPROVAL |
| Key/nonce-to-PRNG seed derivation and domain separation | BLOCKED_ON_GV_APPROVAL |
| Permutation sampling and affine coefficient generation/order | BLOCKED_ON_GV_APPROVAL |
| Error behavior and contract version negotiation | BLOCKED_ON_GV_APPROVAL |
| Exact byte-level P1 algorithm and protection-specific error semantics | NOT VERIFIED / NOT FINAL |
| Required protected-payload wire metadata | NOT VERIFIED / NOT FINAL |
| Normative Python/C vectors and implementation equivalence | NOT VERIFIED / NOT FINAL |

The source roadmap shows an 8-byte nonce in a packet sketch but uses a
`uint32_t nonce` in pseudocode. Neither sketch is an approved I2 choice; this
inconsistency must be resolved explicitly. The draft does not settle nonce
length or reuse policy.

### Compatibility with current I1 v1

The [I1 v1 contract](i1_device_edge_packet_v1.md) still reserves/disables
`PROTECTED_PAYLOAD`: senders MUST keep `flags = 0` and `nonce_length = 0`,
with no nonce bytes. This I2 draft does not insert protection metadata into
that wire packet or change Device/Edge semantics. Activation protection
requires a separately coordinated I1 revision or approved protocol-version
change with the I1 owners before deployment.

## D. Implementation schedule

Python P1 and reversibility evidence are deferred to the later scheduled work
(approximately Week 5). C port, SV1/SV2 handoff, and normative cross-language
vectors are deferred to the subsequent handoff (approximately Week 6). No P1
algorithm, key derivation, or packet code is implemented in Week 2.

## E. Test-vector format now; normative values later

The following is a **draft field inventory**, not a normative vector or final
JSON schema. A future approved vector should contain: vector ID and contract
version; PRNG/derivation identifiers; synthetic key and nonce encoded in an
approved representation; input shape and quantized input bytes; protected
bytes and required metadata; recovered bytes; and an explicit bit-exact
comparison result. It should also state byte order and the Python/C
implementation versions. Final field names, encoding rules, and expected byte
values require GV approval and later implementations. No placeholder bytes here
are a cryptographic test vector.
