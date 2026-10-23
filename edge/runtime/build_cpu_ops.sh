#!/usr/bin/env bash
# App-local CPU extensions; no installation into /usr/lib or runtime replacement.
set -Eeuo pipefail
if [ "$#" -ne 1 ]; then
  printf 'Usage: bash build_cpu_ops.sh NEW_OUTPUT_DIRECTORY\n' >&2
  exit 2
fi
ASI_SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ASI_OUTPUT_DIR="$1"
test ! -e "$ASI_OUTPUT_DIR"
mkdir -p "$ASI_OUTPUT_DIR"
read -r -a ASI_COMPILER <<< "${CXX:-g++}"
{
  date -u +%Y-%m-%dT%H:%M:%SZ
  uname -m
  "${ASI_COMPILER[@]}" --version
  printf 'CXX=%s\n' "${CXX:-g++}"
  sha256sum "$ASI_SOURCE_DIR/build_cpu_ops.sh" "$ASI_SOURCE_DIR"/cpu_ops/*
} > "$ASI_OUTPUT_DIR/build_environment.txt"
for ASI_OP in conv1d maxpool1d relu; do
  "${ASI_COMPILER[@]}" -std=c++17 -O2 -ffp-contract=off -Wall -Wextra -Werror -fPIC -shared \
    "$ASI_SOURCE_DIR/cpu_ops/$ASI_OP.cpp" -o "$ASI_OUTPUT_DIR/libvart_op_imp_$ASI_OP.so" \
    -lxir -lvart-runner -lvitis_ai_library-runner_helper -lglog
done
(cd "$ASI_OUTPUT_DIR"; sha256sum libvart_op_imp_conv1d.so libvart_op_imp_maxpool1d.so libvart_op_imp_relu.so > sha256sum_cpu_ops.txt)
printf 'CPU_OPS_BUILD_COMPLETE=%s\n' "$ASI_OUTPUT_DIR"
