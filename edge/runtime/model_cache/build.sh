#!/usr/bin/env bash
# Invoke in a child Bash, never source. Preserve every existing build.
set -Eeuo pipefail
[ "$#" = 1 ] || { echo 'Usage: bash build.sh NEW_BUILD_DIRECTORY'; exit 2; }
S10="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
test "$(uname -m)" = aarch64
test ! -e "$1"
mkdir -p "$1"
{ date -Is; uname -a; g++ --version; sha256sum "$S10/tail_cache_worker.cpp" "$S10/../single_input/tail_io.hpp" "$S10/../single_input/tail_runner.cpp" "$S10/build.sh"; } > "$1/build_environment.txt"
g++ -std=c++17 -O2 -Wall -Wextra -Werror "$S10/tail_cache_worker.cpp" -o "$1/asi-cache-worker" -lvitis_ai_library-graph_runner -lvart-runner -lxir -lglog
g++ -std=c++17 -O2 -Wall -Wextra -Werror "$S10/../single_input/tail_runner.cpp" -o "$1/asi-single-runner" -lvitis_ai_library-graph_runner -lvart-runner -lxir -lglog
(cd "$1" && sha256sum asi-cache-worker asi-single-runner > binary_sha256.txt)
printf 'BUILD_COMPLETE=%s\n' "$1"
