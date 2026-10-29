#!/usr/bin/env bash
# Run as a child Bash, never source this script.
set -Eeuo pipefail
[ "$#" = 1 ] || { echo 'Usage: bash build.sh NEW_BUILD_DIR'; exit 2; }
ASI_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
[ ! -e "$1" ]; mkdir -p "$1"
{ date -u +%FT%TZ; uname -a; g++ --version; sha256sum "$ASI_DIR/tail_worker.cpp" "$ASI_DIR/../single_input/tail_io.hpp" "$ASI_DIR/build.sh"; } > "$1/build_environment.txt"
g++ -std=c++17 -O2 -Wall -Wextra -Werror "$ASI_DIR/tail_worker.cpp" -o "$1/asi-tail-worker" -lvitis_ai_library-graph_runner -lvart-runner -lxir -lglog
(cd "$1" && sha256sum asi-tail-worker > binary_sha256.txt)
echo "BUILD_COMPLETE=$1/asi-tail-worker"
