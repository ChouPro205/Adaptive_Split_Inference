cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(adaptive_split_device)

target_sources(app PRIVATE
  src/markers.c
)

if(CONFIG_APP_IDLE_MEASUREMENT)
  target_sources(app PRIVATE src/main_idle.c)
elseif(CONFIG_APP_WEEK3_HEAD)
  set(WEEK3_PACKAGE_HEADER "${CMAKE_CURRENT_SOURCE_DIR}/../ml/artifacts/week3/mitdb-week3-fp32-20260925-v2/firmware/head_parameters.h")
  set(WEEK3_INPUT_HEADER "${CMAKE_CURRENT_SOURCE_DIR}/generated/week3_inputs.h")
  if(NOT EXISTS "${WEEK3_PACKAGE_HEADER}" OR NOT EXISTS "${WEEK3_INPUT_HEADER}")
    message(FATAL_ERROR "Week 3 v2 package header or generated input header is missing; run build_week3_head.ps1")
  endif()
  target_sources(app PRIVATE src/main_week3.c src/week3_head.c)
  target_include_directories(app PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
    "${CMAKE_CURRENT_SOURCE_DIR}/generated"
    "${CMAKE_CURRENT_SOURCE_DIR}/../ml/artifacts/week3/mitdb-week3-fp32-20260925-v2/firmware")
  target_compile_options(app PRIVATE -ffp-contract=off)
else()
  target_sources(app PRIVATE src/main.c)
endif()
