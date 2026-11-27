cmake_minimum_required(VERSION 3.20.0)
# Week 11 = link-state measurements for the week 12 lab (W11-D2, W11-D3): week11/main.c + link_cycle.c (ops
# STATE/IDLE/ECHO/S0C/RECONNECT), week11/ble_link.c (fork of the hash-locked week8/ble_link.c with the link-state
# controls), echo_frames.c (echo frame / ECHO-ACK v1), s0c.c (S0c v1 encoder). No head, no I1 request: the
# KV260 runs its echo service. prj.conf, overlay-radio.conf and app.overlay are week 7's, unmodified;
# overlay-link-radio.conf adds Coded / dynamic TX power / RSSI; overlay-link-usb.conf / overlay-link.conf select
# the variant (build_week11.ps1 passes EXTRA_CONF_FILE).
set(WEEK7_APP "${CMAKE_CURRENT_SOURCE_DIR}/../week7")
set(CONF_FILE "${WEEK7_APP}/prj.conf")
set(DTC_OVERLAY_FILE "${WEEK7_APP}/app.overlay")
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(adaptive_split_week11)
if(NOT DEFINED WEEK11_GENERATED_DIR OR NOT EXISTS "${WEEK11_GENERATED_DIR}/week11_build.h" OR
   NOT EXISTS "${WEEK11_GENERATED_DIR}/week8_inputs.h" OR
   NOT EXISTS "${WEEK11_GENERATED_DIR}/week11_link_plan.h")
  message(FATAL_ERROR "Use device/scripts/build_week11.ps1: it authenticates the W8-D3 sample set and the "
                      "W11-D3 plan and writes week11_build.h")
endif()
set(CONTRACTS "${CMAKE_CURRENT_SOURCE_DIR}/../../contracts")
# "." comes first so week11/ble_link.h is the link header (week6/ble_link.h stays on the path for frag.h's
# directory only). i1v2_codec.c only provides i1v2_crc32() here.
target_sources(app PRIVATE
  main.c link_cycle.c ble_link.c echo_frames.c s0c.c
  ../week7/marker_ctrl.c ../src/markers.c ../week6/sha256.c ../week6/frag.c ../week5/quantization.c
  "${CONTRACTS}/i1v2_ref/i1v2_codec.c")
target_include_directories(app PRIVATE . ../week7 ../src ../week6 ../week5 "${CONTRACTS}/i1v2_ref"
  "${WEEK11_GENERATED_DIR}")
# Same numerics flags as weeks 4-10 (no FMA contraction): the S0c encoder must equal s0c_v1_ref.py.
target_compile_options(app PRIVATE -ffp-contract=off -fno-fast-math)
