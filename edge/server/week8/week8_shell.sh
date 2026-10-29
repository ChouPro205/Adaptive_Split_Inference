# Source this helper; every step executes in its own child Bash.
w8_step() {
  local tag="$1" base n=2 codes
  test -d "${W8:-}/logs" || { echo 'Khoi phuc W8/logs truoc'; return 2; }
  [[ "$tag" =~ ^[a-zA-Z0-9_]+$ ]] || return 2
  base="$W8/logs/$tag"
  while [ -e "$base.log" ]; do base="$W8/logs/${tag}_lan_$n"; n=$((n+1)); done
  { printf '#!/usr/bin/env bash\nset -Eeuo pipefail\n'; cat; } > "$base.command.sh" || return
  bash "$base.command.sh" 2>&1 | tee "$base.log"
  codes=("${PIPESTATUS[@]}")
  printf '%s\n' "${codes[0]}" > "$base.exit_code.txt"
  printf 'Exit=%s Tee=%s Log=%s\n' "${codes[0]}" "${codes[1]}" "$base.log"
  test "${codes[0]}" = 0 && test "${codes[1]}" = 0
}
w8_host() {
  export REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
  export W8="$(cat "$REPO_ROOT/edge/build_vai25/ket_qua_hien_tai/week8/phien_dang_dung.txt")"
  export P8="$REPO_ROOT/.cache/jupyter_week5/venv/bin/python"
  export BOARD='root@192.168.0.134'
  test -d "$W8/logs" && test -x "$P8"
}
w8_board() {
  export W8="$(cat /home/root/asi_week8_phien_dang_dung.txt)"
  export W8_SOURCE="$W8/source"
  export DEPLOY="$(cat /home/root/asi_week5_phien_dang_dung.txt)"
  export CPU_OPS="$(cat /home/root/asi_week5_cpu_ops_dang_dung.txt)"
  export WORKER="$W8/build/asi-tail-worker"
  test -d "$W8/logs" && test -d "$W8_SOURCE"
}
