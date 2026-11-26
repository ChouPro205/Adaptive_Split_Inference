cmake_minimum_required(VERSION 3.20.0)
# Week 9 = E_dev(s) for every s (W9-D1..D5): week9/main.c + week9/dev_cycle.c (forks of the
# hash-locked week 8 main.c/g2_cycle.c without radio, NVS nonce or I2; the split of every cycle
# comes from the W9-D4 plan). prj.conf and app.overlay are week 7's, used unmodified;
# overlay-dev-usb.conf / overlay-dev.conf (EXTRA_CONF_FILE) select the variant.
set(WEEK7_APP "${CMAKE_CURRENT_SOURCE_DIR}/../week7")
set(CONF_FILE "${WEEK7_APP}/prj.conf")
set(DTC_OVERLAY_FILE "${WEEK7_APP}/app.overlay")
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(adaptive_split_week9)
if(NOT DEFINED WEEK9_GENERATED_DIR OR NOT EXISTS "${WEEK9_GENERATED_DIR}/week9_build.h" OR
   NOT EXISTS "${WEEK9_GENERATED_DIR}/week8_inputs.h" OR
   NOT EXISTS "${WEEK9_GENERATED_DIR}/week9_plan.h")
  message(FATAL_ERROR "Use device/scripts/build_week9.ps1: it authenticates the R3 headers, the "
                      "W8-D3 sample set and the W9-D4 plan and writes week9_build.h")
endif()
set(R3_FIRMWARE "${CMAKE_CURRENT_SOURCE_DIR}/../../ml/results/week4-r3/firmware")
# head_fast.c includes ../src/week4_head.c itself (shared static weights).
target_sources(app PRIVATE
  main.c dev_cycle.c
  ../week7/marker_ctrl.c ../week7/head_fast.c
  ../src/markers.c ../week6/sha256.c ../week5/quantization.c)
# WEEK9_GENERATED_DIR holds week9_build.h and the authenticated copies of week8_inputs.h and
# week9_plan.h.
target_include_directories(app PRIVATE . ../week7 ../src ../generated ../week6 ../week5
  "${R3_FIRMWARE}" "${WEEK9_GENERATED_DIR}")
# Same numerics flags as weeks 4-8 (no FMA contraction).
target_compile_options(app PRIVATE -ffp-contract=off -fno-fast-math)
