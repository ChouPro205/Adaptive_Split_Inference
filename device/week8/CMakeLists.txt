cmake_minimum_required(VERSION 3.20.0)
# Week 8 = G2 end-to-end firmware (W8-D6): week8/main.c + week8/g2_cycle.c (forks of the hash-locked
# week 7 main.c/energy_cycle.c: 100 W8-D3 samples, paired P1/P0 session, label on the dongle) and
# week8/ble_link.c (W8-D2: off-air after the device ends its session). prj.conf, overlays and
# app.overlay are used unmodified from ../week7; week8/Kconfig adds WEEK8_PAIRS and sources
# ../week7/Kconfig. Only the radio variants exist (bench has no link: build it from week7).
set(WEEK7_APP "${CMAKE_CURRENT_SOURCE_DIR}/../week7")
set(APPLICATION_CONFIG_DIR "${WEEK7_APP}")
set(KCONFIG_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/Kconfig")
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(adaptive_split_week8)
if(NOT DEFINED WEEK8_GENERATED_DIR OR NOT EXISTS "${WEEK8_GENERATED_DIR}/week8_build.h" OR
   NOT EXISTS "${WEEK8_GENERATED_DIR}/week8_inputs.h")
  message(FATAL_ERROR "Use device/scripts/build_week8.ps1: it authenticates the R3 headers and the "
                      "W8-D3 sample set and writes week8_build.h")
endif()
if(CONFIG_WEEK7_BENCH)
  message(FATAL_ERROR "Week 8 builds energy-usb and energy only; bench is device/week7")
endif()
set(CONTRACTS "${CMAKE_CURRENT_SOURCE_DIR}/../../contracts")
set(R3_FIRMWARE "${CMAKE_CURRENT_SOURCE_DIR}/../../ml/results/week4-r3/firmware")
# head_fast.c includes ../src/week4_head.c itself (shared static weights). ble_link.h stays the
# week 6 header (API unchanged).
target_sources(app PRIVATE
  main.c g2_cycle.c ble_link.c
  ../week7/marker_ctrl.c ../week7/head_fast.c
  ../src/markers.c ../week6/sha256.c ../week6/frag.c ../week6/nonce_store.c ../week6/nonce_nvs.c
  ../week6/packets.c ../week5/quantization.c
  "${CONTRACTS}/i1v2_ref/i1v2_codec.c"
  "${CONTRACTS}/i2_ref/i2_reference.c")
# WEEK8_GENERATED_DIR holds week8_build.h and the authenticated copy of week8_inputs.h.
target_include_directories(app PRIVATE . ../week7 ../src ../generated ../week6 ../week5
  "${CONTRACTS}/i1v2_ref" "${CONTRACTS}/i2_ref" "${R3_FIRMWARE}" "${WEEK8_GENERATED_DIR}")
# Same numerics flags as weeks 4-7 (no FMA contraction).
target_compile_options(app PRIVATE -ffp-contract=off -fno-fast-math)
