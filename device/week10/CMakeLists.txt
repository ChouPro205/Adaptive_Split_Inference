cmake_minimum_required(VERSION 3.20.0)
# Week 10 = radio-on cycle at every s (W10-D4, W10-D8): week10/main.c + week10/ble_cycle.c (forks of the
# hash-locked week 8 main.c/g2_cycle.c and week 9 dev_cycle.c: rho0 only, no NVS nonce, split per plan
# entry, s10 device-only). ble_link.c is week 8's (off-air after the session, W8-D2), unmodified.
# prj.conf, overlay-radio.conf and app.overlay are week 7's, unmodified; overlay-ble-usb.conf /
# overlay-ble.conf select the variant (build_week10.ps1 passes EXTRA_CONF_FILE).
set(WEEK7_APP "${CMAKE_CURRENT_SOURCE_DIR}/../week7")
set(CONF_FILE "${WEEK7_APP}/prj.conf")
set(DTC_OVERLAY_FILE "${WEEK7_APP}/app.overlay")
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(adaptive_split_week10)
if(NOT DEFINED WEEK10_GENERATED_DIR OR NOT EXISTS "${WEEK10_GENERATED_DIR}/week10_build.h" OR
   NOT EXISTS "${WEEK10_GENERATED_DIR}/week8_inputs.h" OR
   NOT EXISTS "${WEEK10_GENERATED_DIR}/week10_ble_plan.h")
  message(FATAL_ERROR "Use device/scripts/build_week10.ps1: it authenticates the R3 headers, the "
                      "W8-D3 sample set and the W10-D4 plan and writes week10_build.h")
endif()
set(CONTRACTS "${CMAKE_CURRENT_SOURCE_DIR}/../../contracts")
set(R3_FIRMWARE "${CMAKE_CURRENT_SOURCE_DIR}/../../ml/results/week4-r3/firmware")
# head_fast.c includes ../src/week4_head.c itself (shared static weights). ble_link.h stays the week 6
# header (API unchanged); g2_plan.h (label rule) is week 8's. i2_reference.c only resolves packets.c.
target_sources(app PRIVATE
  main.c ble_cycle.c ../week8/ble_link.c
  ../week7/marker_ctrl.c ../week7/head_fast.c
  ../src/markers.c ../week6/sha256.c ../week6/frag.c ../week6/packets.c ../week5/quantization.c
  "${CONTRACTS}/i1v2_ref/i1v2_codec.c"
  "${CONTRACTS}/i2_ref/i2_reference.c")
target_include_directories(app PRIVATE . ../week8 ../week7 ../src ../generated ../week6 ../week5
  "${CONTRACTS}/i1v2_ref" "${CONTRACTS}/i2_ref" "${R3_FIRMWARE}" "${WEEK10_GENERATED_DIR}")
# Same numerics flags as weeks 4-9 (no FMA contraction).
target_compile_options(app PRIVATE -ffp-contract=off -fno-fast-math)
