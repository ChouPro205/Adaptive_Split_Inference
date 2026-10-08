#!/usr/bin/env bash
# Run from the reviewed source checkout; use delivered v1, never bundled scripts.
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
task_root="${ASI_LINUX_ENV_ROOT:-$HOME/asi-week3-sv2-linux}"
mkdir -p "$task_root"
if [[ ! -x "$task_root/bin/uv" ]]; then
    curl -LsSf https://astral.sh/uv/install.sh -o "$task_root/uv-installer.sh"
    UV_INSTALL_DIR="$task_root/bin" UV_NO_MODIFY_PATH=1 sh "$task_root/uv-installer.sh"
fi
uv="$task_root/bin/uv"
"$uv" python install 3.11.9
if [[ ! -x "$task_root/venv/bin/python" ]]; then
    "$uv" venv --python 3.11.9 "$task_root/venv"
fi
python="$task_root/venv/bin/python"
"$uv" pip install --python "$python" 'torch==2.14.0+cu130' --index-url https://download.pytorch.org/whl/cu130
"$uv" pip install --python "$python" -r ml/requirements-week3-onnx.txt 'numpy==2.4.6'

package="ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1"
anchor="a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6"
# The original ZIP, if supplied, is authenticated before any extraction.
"$python" -B - "$package" "$anchor" <<'PY'
import hashlib, json, sys, zipfile
from pathlib import Path
p = Path(sys.argv[1]); z = p.with_suffix('.zip')
digest = lambda f: hashlib.sha256(f.read_bytes()).hexdigest()
if z.exists():
    if digest(z) != 'b7f5b8d0bcd5ec27755f3e44541c0d24a6d23bdd27e199660a7b653bc30a71c7':
        raise SystemExit('Original ZIP checksum mismatch')
if not p.exists():
    if not z.is_file():
        raise SystemExit('Place the delivered original v1 ZIP or extracted package in ml/artifacts/week3; no dataset download required')
    # Extract only the authenticated project ZIP into a new package directory.
    with zipfile.ZipFile(z) as archive:
        for name in archive.namelist():
            target = (p.parent / name).resolve()
            if p.resolve() != target and p.resolve() not in target.parents:
                raise SystemExit('ZIP member escapes expected package directory')
        archive.extractall(p.parent)
if digest(p / 'manifest.json') != sys.argv[2]:
    raise SystemExit('Manifest anchor mismatch')
m = json.loads((p / 'manifest.json').read_bytes())
for row in m['files']:
    f = p / row['path']
    if not f.is_file() or f.stat().st_size != row['size_bytes'] or digest(f) != row['sha256']:
        raise SystemExit('Delivered hash/size mismatch: ' + row['path'])
print('Original package hashes and manifest anchor authenticated')
PY

log_root="${ASI_LINUX_LOG_ROOT:-$task_root/logs/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$log_root"
printf '%s\n' "$PWD" > "$log_root/cwd.txt"
git rev-parse HEAD > "$log_root/base_commit.txt"
git status --short > "$log_root/working_tree.txt"
sha256sum ml/scripts/*week3*.py > "$log_root/source_sha256.txt"
uname -a > "$log_root/kernel.txt"
cat /etc/os-release > "$log_root/os.txt"
"$uv" pip freeze --python "$python" > "$log_root/dependencies.txt"
run() {
    local name="$1" code
    shift
    printf '%q ' "$@" > "$log_root/$name.command.txt"
    printf '\n' >> "$log_root/$name.command.txt"
    if "$@" > "$log_root/$name.stdout.txt" 2> "$log_root/$name.stderr.txt"; then code=0; else code=$?; fi
    printf '%s\n' "$code" > "$log_root/$name.exit_code.txt"
    cat "$log_root/$name.stdout.txt"
    cat "$log_root/$name.stderr.txt" >&2
    return "$code"
}
run diagnostic "$python" -B ml/scripts/diagnose_week3_sv2.py --package "$package" --expected-manifest-sha256 "$anchor"
run verifier "$python" -B ml/scripts/verify_week3_sv2.py --package "$package" --expected-manifest-sha256 "$anchor" --recomputation-policy portable-fp32-v2
run tamper "$python" -B ml/scripts/test_week3_sv2.py --package "$package" --expected-manifest-sha256 "$anchor" --recomputation-policy portable-fp32-v2
run cache "$python" -B ml/scripts/test_week3_sv2_cache.py --recomputation-policy portable-fp32-v2
run policy "$python" -B ml/scripts/test_week3_sv2_policy.py
printf 'PASS policy=portable-fp32-v2; recipient acceptance still requires SV2 review. Logs: %s\n' "$log_root"
