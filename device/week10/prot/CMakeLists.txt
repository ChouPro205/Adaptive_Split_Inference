cmake_minimum_required(VERSION 3.20.0)
# Week 10 E_prot firmware (W10-D1, W10-D2, W10-D8), radio off: week10/prot/main.c + prot_cycle.c (forks of
# the hash-locked week 9 main.c/dev_cycle.c and week 8 g2_cycle.c: per plan entry a P1 cycle (CTRL, HEAD,
# PROT), a P0 cycle (CTRL, HEAD) or the HEAD-only s1 cycle (features.0 + ReLU, no quantization)). The NVS
# nonce store and I2 protect are week 6's, unmodified. prj.conf and app.overlay are week 7's, unmodified;
# overlay-nvs.conf + overlay-prot-usb.conf / overlay-prot.conf select the variant (build_week10.ps1).
set(WEEK7_APP "${CMAKE_CURRENT_SOURCE_DIR}/../../week7")
set(CONF_FILE "${WEEK7_APP}/prj.conf")
set(DTC_OVERLAY_FILE "${WEEK7_APP}/app.overlay")
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(adaptive_split_week10_prot)
if(NOT DEFINED WEEK10_GENERATED_DIR OR NOT EXISTS "${WEEK10_GENERATED_DIR}/week10_build.h" OR
   NOT EXISTS "${WEEK10_GENERATED_DIR}/week8_inputs.h" OR
   NOT EXISTS "${WEEK10_GENERATED_DIR}/week10_prot_plan.h")
  message(FATAL_ERROR "Use device/scripts/build_week10.ps1: it authenticates the R3 headers, the "
                      "W8-D3 sample set and the W10-D1 plan and writes week10_build.h")
endif()
set(DEVICE "${CMAKE_CURRENT_SOURCE_DIR}/../..")
set(CONTRACTS "${DEVICE}/../contracts")
set(R3_FIRMWARE "${DEVICE}/../ml/results/week4-r3/firmware")
# head_fast.c includes ../src/week4_head.c itself (shared static weights). nonce_nvs.c includes the week 6
# ble_link.h for link_cycles() only; prot_cycle.c defines it (DWT), no ble_link.c is linked.
target_sources(app PRIVATE
  main.c prot_cycle.c
  ${DEVICE}/week7/marker_ctrl.c ${DEVICE}/week7/head_fast.c
  ${DEVICE}/src/markers.c ${DEVICE}/week6/sha256.c ${DEVICE}/week6/packets.c
  ${DEVICE}/week6/nonce_store.c ${DEVICE}/week6/nonce_nvs.c ${DEVICE}/week5/quantization.c
  "${CONTRACTS}/i1v2_ref/i1v2_codec.c"
  "${CONTRACTS}/i2_ref/i2_reference.c")
target_include_directories(app PRIVATE . ${DEVICE}/week8 ${DEVICE}/week7 ${DEVICE}/src ${DEVICE}/generated
  ${DEVICE}/week6 ${DEVICE}/week5 "${CONTRACTS}/i1v2_ref" "${CONTRACTS}/i2_ref" "${R3_FIRMWARE}"
  "${WEEK10_GENERATED_DIR}")
# Same numerics flags as weeks 4-9 (no FMA contraction).
target_compile_options(app PRIVATE -ffp-contract=off -fno-fast-math)
