#!/usr/bin/env bash
# Invoke with bash; do not source into the login shell.
set -Eeuo pipefail
if [ "$#" -ne 1 ]; then
  printf 'Usage: bash build_tail_profiler.sh NEW_OUTPUT_DIR\n' >&2
  exit 2
fi
ASI_PROFILE_SOURCE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ASI_PROFILE_BUILD="$1"
test ! -e "$ASI_PROFILE_BUILD"
mkdir -p "$ASI_PROFILE_BUILD"
read -r -a ASI_PROFILE_CXX <<< "${CXX:-g++}"
{
  date -u +%Y-%m-%dT%H:%M:%SZ
  uname -m
  "${ASI_PROFILE_CXX[@]}" --version
  printf 'CXX=%s\n' "${CXX:-g++}"
  sha256sum "$ASI_PROFILE_SOURCE/profile_tail_runner.cpp" "$ASI_PROFILE_SOURCE/tail_io.hpp" "$ASI_PROFILE_SOURCE/build_tail_profiler.sh"
} > "$ASI_PROFILE_BUILD/build_environment.txt"
"${ASI_PROFILE_CXX[@]}" -std=c++17 -O2 -Wall -Wextra -Werror \
  "$ASI_PROFILE_SOURCE/profile_tail_runner.cpp" -o "$ASI_PROFILE_BUILD/asi-tail-profiler" \
  -lvitis_ai_library-graph_runner -lvart-runner -lxir -lglog
(cd "$ASI_PROFILE_BUILD" && sha256sum asi-tail-profiler > binary_sha256.txt)
printf 'PROFILER_BUILD_COMPLETE=%s\n' "$ASI_PROFILE_BUILD/asi-tail-profiler"
