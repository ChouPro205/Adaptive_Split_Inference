# Source on HOST or BOARD. Only w10_step's child Bash enables errexit/nounset.
w10_output() {
  local candidate="$1" index=2
  while [ -e "$candidate" ]; do
    candidate="${1}_lan_$index"
    index=$((index+1))
  done
  printf '%s\n' "$candidate"
}
w10_step() {
  local tag="$1" log_base index=2 codes
  test -d "${W10:-}/logs" || { echo 'Khoi phuc W10/logs truoc'; return 2; }
  [[ "$tag" =~ ^[a-zA-Z0-9_]+$ ]] || return 2
  log_base="$W10/logs/$tag"
  while [ -e "$log_base.command.sh" ] || [ -e "$log_base.log" ]; do
    log_base="$W10/logs/${tag}_lan_$index"
    index=$((index+1))
  done
  { printf '#!/usr/bin/env bash\nset -Eeuo pipefail\n'; cat; } > "$log_base.command.sh" || return
  bash "$log_base.command.sh" 2>&1 | tee "$log_base.log"
  codes=("${PIPESTATUS[@]}")
  printf '%s\n' "${codes[0]}" > "$log_base.exit_code.txt"
  printf 'Exit=%s Tee=%s Log=%s\n' "${codes[0]}" "${codes[1]}" "$log_base.log"
  test "${codes[0]}" = 0 && test "${codes[1]}" = 0
}
w10_host() {
  export REPO_ROOT="$(git rev-parse --show-toplevel)" || return
  export W10="$(cat "$REPO_ROOT/edge/build_vai25/ket_qua_hien_tai/week10/phien_dang_dung.txt")" || return
  export P10="$REPO_ROOT/.cache/jupyter_week5/venv/bin/python"
  export BOARD='root@192.168.0.134'
  test -d "$W10/logs" && test -x "$P10"
}
w10_board() {
  export W10="$(cat /home/root/asi_week10_phien_dang_dung.txt)" || return
  export DEPLOY="$(cat /home/root/asi_week5_phien_dang_dung.txt)" || return
  export CPU_OPS="$(cat /home/root/asi_week5_cpu_ops_dang_dung.txt)" || return
  export W8="$(cat /home/root/asi_week8_phien_dang_dung.txt)" || return
  export P10="$W8/venv_ble/bin/python"
  if [ ! -x "$P10" ] && [ -s /home/root/asi_week9_phien_dang_dung.txt ]; then
    export P10="$(cat /home/root/asi_week9_phien_dang_dung.txt)/venv/bin/python"
  fi
  export PATH="/usr/sbin:/sbin:$PATH"
  test -d "$W10/logs" && test -x "$P10" && test -d "$DEPLOY" && test -d "$CPU_OPS"
}
