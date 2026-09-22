cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(adaptive_split_device)

target_sources(app PRIVATE
  src/markers.c
)

if(CONFIG_APP_IDLE_MEASUREMENT)
  target_sources(app PRIVATE src/main_idle.c)
else()
  target_sources(app PRIVATE src/main.c)
endif()
