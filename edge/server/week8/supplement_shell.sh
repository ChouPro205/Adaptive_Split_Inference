# Source on BOARD only. Keep original W8 model/runtime pointers unchanged.
supp_board() {
  export W8_BASE="$(cat /home/root/asi_week8_phien_dang_dung.txt)"
  source "$W8_BASE/source/edge/server/week8/week8_shell.sh" || return
  w8_board || return
  export SUPP="$(cat "$W8_BASE/bo_sung_link_dang_dung.txt")"
  [[ "$SUPP" =~ ^/home/root/asi_week8(_lan_[0-9]+)?/bo_sung_link(_lan_[0-9]+)?$ ]] || return 2
  test -d "$SUPP/logs" && test -d "$SUPP/source"
}
supp_step() {
  # A function-local W8 directs logs to the supplemental run only.
  local W8="$SUPP"
  export W8
  w8_step "$@"
}
