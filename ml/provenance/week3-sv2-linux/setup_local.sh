#!/usr/bin/env bash
set -euo pipefail
task_root="$HOME/asi-week3-sv2-linux"
mkdir -p "$task_root"
curl -LsSf https://astral.sh/uv/install.sh -o "$task_root/uv-installer.sh"
UV_INSTALL_DIR="$task_root/bin" UV_NO_MODIFY_PATH=1 sh "$task_root/uv-installer.sh"
"$task_root/bin/uv" python install 3.11.9
"$task_root/bin/uv" venv --python 3.11.9 "$task_root/venv"
"$task_root/bin/uv" pip install --python "$task_root/venv/bin/python" 'torch==2.14.0+cu130' --index-url https://download.pytorch.org/whl/cu130
"$task_root/bin/uv" pip install --python "$task_root/venv/bin/python" -r ml/requirements-week3-onnx.txt 'numpy==2.4.6' 'matplotlib==3.11.2'
"$task_root/venv/bin/python" -V
