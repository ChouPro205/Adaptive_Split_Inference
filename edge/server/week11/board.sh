#!/usr/bin/env bash
# Run in a child Bash on the KV260. Every measurement has its own directory.
set -Eeu -o pipefail
export PATH="/usr/sbin:/sbin:$PATH"
tool=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(dirname "$tool")
cd "$tool"
sha256sum -c delivery.sha256
w10=${WEEK10_SESSION:-/home/root/asi_week10}
worker=${WEEK11_WORKER:-"$w10/build/asi-cache-worker"}
parity=${WEEK11_PARITY:-"$w10/parity"}
test "$(uname -m)" = aarch64
mode=${1:-}
case "$mode" in
  probe|stress|demo) ;;
  *) echo 'Usage: bash board.sh {probe|stress|demo} [RUN_NAME]'; exit 2 ;;
esac
mapfile -t env_paths < <(python3 -B - "$w10/d2_environment.json" <<'PY'
import json
import sys
with open(sys.argv[1]) as f:
    data = json.load(f)
for k in ('python', 'deploy', 'cpu_ops'):
    print(data[k])
PY
)
test "${#env_paths[@]}" = 3
python=${env_paths[0]}
test -x "$python"
args=(--session "$w10" --worker "$worker" --baseline "$parity"
      --deploy "${env_paths[1]}" --cpu-ops "${env_paths[2]}")
if [ "$mode" = probe ]; then
  "$python" -B "$tool/stress.py" probe "${args[@]}"
  exit
fi

name=${2:-$mode}
[[ "$name" =~ ^${mode}(_lan_[2-9][0-9]*|_lan_1[0-9]+)?$ ]] || {
  echo 'Use stress, demo, or the matching name with suffix _lan_2 etc.'
  exit 2
}
mkdir -p "$root/runs"
mkdir "$root/running" || { echo "Another run or stale lock: $root/running"; exit 2; }
trap 'rmdir "$root/running"' EXIT
run="$root/runs/$name"
mkdir "$run"
# Hold the lock for preflight, worker execution and shell log completion.
set +e
(
  set -Eeuo pipefail
  dmesg | awk 'tolower($0) ~ /out of memory|oom-kill|killed process|segfault/' \
    > "$run/kernel_before.log" || echo 'Kernel snapshot unavailable before run'
  date -Is
  uname -a
  cat /etc/os-release
  df -h "$root"
  awk '/^(MemAvailable|CmaFree|SwapFree):/ {print}' /proc/meminfo
  processes=$(ps -eo pid,args)
  if awk '$2 ~ /(^|\/)asi-(cache-worker|single-runner|tail-runner)$/ ||
      ($2 ~ /python/ && $0 ~ /(^|[\/ ])(ble_week10|ble_service)[.]py( |$)/) {
        print; found=1
      } END {exit !found}' <<< "$processes"; then
    echo 'Another inference worker is active. Stop your own service cleanly before retry.'
    exit 2
  fi
  xdputil query
  switches=10000
  [ "$mode" = stress ] || switches=100
  "$python" -B "$tool/stress.py" run "${args[@]}" --output "$run/raw" \
    --source-commit "$(cat "$tool/source_commit.txt")" --switches "$switches"
) 2>&1 | tee "$run/run.log"
codes=("${PIPESTATUS[@]}")
set -e
dmesg | awk 'tolower($0) ~ /out of memory|oom-kill|killed process|segfault/' \
  > "$run/kernel_after.log" || echo 'Kernel snapshot unavailable after run'
printf '%s\n' "${codes[0]}" > "$run/exit_code.txt"
(cd "$run" && sha256sum run.log exit_code.txt kernel_before.log kernel_after.log > shell.sha256)
printf 'Exit=%s Tee=%s Run=%s\n' "${codes[0]}" "${codes[1]}" "$run"
test "${codes[0]}" = 0 && test "${codes[1]}" = 0
