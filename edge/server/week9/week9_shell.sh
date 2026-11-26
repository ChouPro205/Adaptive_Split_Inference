# Source in the terminal; each task runs in its own child Bash with logs.
w9_step() {
  local tag="$1" base n=2 codes
  test -d "${W9:-}/logs" || { echo 'Khoi phuc W9/logs truoc'; return 2; }
  [[ "$tag" =~ ^[a-zA-Z0-9_]+$ ]] || return 2
  base="$W9/logs/$tag"
  while [ -e "$base.log" ]; do base="$W9/logs/${tag}_lan_$n"; n=$((n+1)); done
  { printf '#!/usr/bin/env bash\nset -Eeuo pipefail\n'; cat; } > "$base.command.sh" || return
  bash "$base.command.sh" 2>&1 | tee "$base.log"
  codes=("${PIPESTATUS[@]}")
  printf '%s\n' "${codes[0]}" > "$base.exit_code.txt"
  printf 'Exit=%s Tee=%s Log=%s\n' "${codes[0]}" "${codes[1]}" "$base.log"
  test "${codes[0]}" = 0 && test "${codes[1]}" = 0
}
w9_host() {
  export REPO_ROOT="$(git rev-parse --show-toplevel)"
  export W9="$(cat "$REPO_ROOT/edge/build_vai25/ket_qua_hien_tai/week9/phien_dang_dung.txt")"
  export P9="$REPO_ROOT/.cache/jupyter_week5/venv/bin/python"
  export BOARD='root@192.168.0.134'
  test -d "$W9/logs" && test -x "$P9"
}
w9_board() {
  export W9="$(cat /home/root/asi_week9_phien_dang_dung.txt)"
  export W8="$(cat /home/root/asi_week8_phien_dang_dung.txt)"
  export DEPLOY="$(cat /home/root/asi_week5_phien_dang_dung.txt)"
  export CPU_OPS="$(cat /home/root/asi_week5_cpu_ops_dang_dung.txt)"
  export WORKER="$W8/build/asi-tail-worker"
  export P9="$W9/venv/bin/python"
  export PATH="/usr/sbin:/sbin:$PATH"
  test -d "$W9/logs" && test -x "$P9" && test -x "$WORKER"
}
