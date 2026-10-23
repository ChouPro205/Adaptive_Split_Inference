#!/usr/bin/env bash
# Invoke with bash: errors stop this child shell, never the user's login shell.
set -Eeuo pipefail
if [ "$#" -ne 1 ]; then
  printf 'Usage: bash build_tail_runner.sh NEW_OUTPUT_DIRECTORY\n' >&2
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
  sha256sum "$ASI_SOURCE_DIR/tail_runner.cpp" "$ASI_SOURCE_DIR/tail_io.hpp" "$ASI_SOURCE_DIR/build_tail_runner.sh"
} > "$ASI_OUTPUT_DIR/build_environment.txt"
"${ASI_COMPILER[@]}" -std=c++17 -O2 -Wall -Wextra -Werror \
  "$ASI_SOURCE_DIR/tail_runner.cpp" -o "$ASI_OUTPUT_DIR/asi-tail-runner" \
  -lvitis_ai_library-graph_runner -lvart-runner -lxir -lglog
sha256sum "$ASI_OUTPUT_DIR/asi-tail-runner" > "$ASI_OUTPUT_DIR/binary_sha256.txt"
printf 'BUILD_COMPLETE=%s\n' "$ASI_OUTPUT_DIR/asi-tail-runner"
