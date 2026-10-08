#!/usr/bin/env bash
set -euo pipefail
task_venv_bin="$HOME/asi-week3-review-v2-fixtures/wrong-python/venv/bin"
mkdir -p "$task_venv_bin"
test ! -e "$task_venv_bin/python"
ln -s /usr/bin/python3 "$task_venv_bin/python"
