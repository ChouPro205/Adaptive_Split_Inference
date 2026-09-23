# I2 — SV3 protection interface, approval draft

**Status: BLOCKED_ON_GV_APPROVAL.** This is a Week 2 interface proposal for
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

These signatures specify roles only. Types and serialized layout remain open.

```text
protect(tensor_int8, shape, key, nonce, contract_version)
    -> protected_tensor, metadata

unprotect(protected_tensor, metadata, shape, key, nonce, contract_version)
    -> tensor_int8
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

The source roadmap shows an 8-byte nonce in a packet sketch but uses a
`uint32_t nonce` in pseudocode. Neither sketch is an approved I2 choice; this
inconsistency must be resolved explicitly. The draft does not settle nonce
length or reuse policy.

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
