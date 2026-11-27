#!/usr/bin/env bash
# Run the burst in an isolated output directory using the proven Week 10 runtime.
set -Eeuo pipefail
export PATH="/usr/sbin:/sbin:$PATH"
tool=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(dirname -- "$tool")
session=${WEEK10_SESSION:-/home/root/asi_week10}
stress_tool=${WEEK11_STRESS_TOOL:-"$root/tool"}
worker=${WEEK11_WORKER:-"$session/build/asi-cache-worker"}
baseline=${WEEK11_PARITY:-"$stress_tool/parity"}
name=${1:-burst}
limit=${2:-32}
[[ "$name" =~ ^burst(_lan_([2-9]|[1-9][0-9]+))?$ ]]
test "$(uname -m)" = aarch64
(cd "$tool" && sha256sum -c delivery.sha256)
(cd "$stress_tool" && sha256sum -c delivery.sha256)

mkdir -p "$root/runs"
mkdir "$root/running" || { echo 'An existing run holds the KV260 lock'; exit 2; }
trap 'rmdir "$root/running"' EXIT
run="$root/runs/$name"
mkdir "$run"
set +e
(
  set -Eeuo pipefail
  date -Is
  uname -a
  commands=$(ps -eo pid,args)
  if awk '$2 ~ /(^|\/)asi-(cache-worker|single-runner|tail-runner)$/ ||
    ($2 ~ /python/ && $0 ~ /(^|[\/ ])(ble_week10|ble_service)[.]py( |$)/) {
      print; found=1
    } END {exit !found}' <<< "$commands"; then
    echo 'Another inference process is active'
    exit 2
  fi
  xdputil query
  mapfile -t paths < <(python3 -B - "$session/d2_environment.json" <<'PY'
import json
import sys
with open(sys.argv[1]) as stream:
    runtime = json.load(stream)
for name in ("python", "deploy", "cpu_ops"):
    print(runtime[name])
PY
)
  test "${#paths[@]}" = 3
  "${paths[0]}" -B "$tool/burst.py" run --stress-tool "$stress_tool" \
    --session "$session" --worker "$worker" --baseline "$baseline" \
    --deploy "${paths[1]}" --cpu-ops "${paths[2]}" --output "$run/raw" \
    --seed 11 --max-pending-background-jobs "$limit"
) 2>&1 | tee "$run/run.log"
codes=("${PIPESTATUS[@]}")
set -e
printf '%s\n' "${codes[0]}" > "$run/exit_code.txt"
(cd "$run" && sha256sum run.log exit_code.txt > shell.sha256)
printf 'Exit=%s Tee=%s Run=%s\n' "${codes[0]}" "${codes[1]}" "$run"
test "${codes[0]}" = 0 && test "${codes[1]}" = 0
