cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(adaptive_split_week7)
if(NOT DEFINED WEEK7_GENERATED_DIR OR NOT EXISTS "${WEEK7_GENERATED_DIR}/week7_build.h")
  message(FATAL_ERROR "Use device/scripts/build_week7.ps1: it authenticates the R3 headers and "
                      "writes week7_build.h")
endif()
set(CONTRACTS "${CMAKE_CURRENT_SOURCE_DIR}/../../contracts")
set(R3_FIRMWARE "${CMAKE_CURRENT_SOURCE_DIR}/../../ml/results/week4-r3/firmware")
# Earlier weeks' modules are compiled unmodified through their paths (their hashes are locked).
# head_fast.c includes ../src/week4_head.c itself (shared static weights), so week4_head.c is
# not listed here.
target_sources(app PRIVATE main.c marker_ctrl.c head_fast.c ../src/markers.c ../week6/sha256.c)
target_include_directories(app PRIVATE . ../src ../generated ../week6 "${R3_FIRMWARE}"
  "${WEEK7_GENERATED_DIR}")
if(NOT CONFIG_WEEK7_BENCH)
  target_sources(app PRIVATE
    energy_cycle.c
    ../week6/ble_link.c ../week6/frag.c ../week6/nonce_store.c ../week6/nonce_nvs.c
    ../week6/packets.c ../week5/quantization.c
    "${CONTRACTS}/i1v2_ref/i1v2_codec.c"
    "${CONTRACTS}/i2_ref/i2_reference.c")
  target_include_directories(app PRIVATE ../week5 "${CONTRACTS}/i1v2_ref" "${CONTRACTS}/i2_ref")
endif()
# Same numerics flags as weeks 4-6 (no FMA contraction).
target_compile_options(app PRIVATE -ffp-contract=off -fno-fast-math)
