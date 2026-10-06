#!/usr/bin/env bash
set -euo pipefail
pwd
git rev-parse HEAD
git branch --show-current
cat /etc/os-release
uname -a
lscpu
printf '\nNative interpreter:\n'
readlink -f "$HOME/asi-week3-sv2-linux/venv/bin/python"
"$HOME/asi-week3-sv2-linux/venv/bin/python" -V
"$HOME/asi-week3-sv2-linux/bin/uv" pip freeze --python "$HOME/asi-week3-sv2-linux/venv/bin/python"
