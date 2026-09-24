# I3 — SV3 input to the shared LUT schema

**Status: OPEN; final schema requires cross-team/GV approval.** SV3 is
consulted for I3 and does not own the final `lut.json` schema.

The local Project documents
`ml/docs/project_sources/requirements/Huong1_Bao_cao_trien_khai_3SV.docx`
and `Huong1_Phan_cong_nhom_nghien_cuu.docx` describe I3 as a shared Week 2
schema/interface item. They require units in field names and give examples
`E_dev_uJ`, `t_dev_ms`, and `bytes_payload`. Those examples are preserved here;
they do not constitute a complete approved schema.

SV3 will eventually contribute privacy-related measurements indexed by split
point `s` and protection strength `rho`, with the metric definition and units
agreed by the team. No `Pi(s,rho)` values, energy measurements, split-point
profiles, or controller fields are available from this Week 2 baseline. SV3
therefore supplies no fabricated LUT rows or final field names for them.

The later [I2/1 technical specification](i2_protection_v1.md) fixes one
reversible transform and does not define a numeric `rho` or provide privacy,
energy, or latency measurements. I3 still needs a separate measured metric and
approved schema; no I2 test vector is an I3 LUT row.

Open for the shared schema owner and GV: complete field inventory, index
representation for `(s, rho)`, metric semantics, required units, versioning,
missing-value rules, and approval of the combined LUT. No `lut.json` is
created by this document.
