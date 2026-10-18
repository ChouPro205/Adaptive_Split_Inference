cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(adaptive_split_week6)
if(NOT DEFINED WEEK6_GENERATED_DIR OR NOT EXISTS "${WEEK6_GENERATED_DIR}/week6_vectors.c")
  message(FATAL_ERROR "Use device/scripts/build_week6.ps1: it authenticates the SV3 P1 package "
                      "and generates the vector tables")
endif()
set(CONTRACTS "${CMAKE_CURRENT_SOURCE_DIR}/../../contracts")
# Reference codecs are compiled unmodified (A2: no malloc/stdio, bounded stack).
target_sources(app PRIVATE
  main.c ble_link.c frag.c exchange.c nonce_store.c nonce_nvs.c packets.c sha256.c
  "${CONTRACTS}/i1v2_ref/i1v2_codec.c"
  "${CONTRACTS}/i2_ref/i2_reference.c"
  ../week5/quantization.c
  ../src/markers.c
  "${WEEK6_GENERATED_DIR}/week6_vectors.c")
target_include_directories(app PRIVATE . "${CONTRACTS}/i1v2_ref" "${CONTRACTS}/i2_ref" ../week5 ../src
  "${WEEK6_GENERATED_DIR}")
# Same numerics flags as week 5 quantization.
target_compile_options(app PRIVATE -ffp-contract=off -fno-fast-math)
