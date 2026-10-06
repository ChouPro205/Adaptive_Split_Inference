#!/usr/bin/env bash
# Read reviewed checkout source; authenticate immutable v1; log setup and gates.
set -euo pipefail
task_root="${ASI_LINUX_ENV_ROOT:-$HOME/asi-week3-sv2-linux}"
log_root="${ASI_LINUX_LOG_ROOT:-$task_root/logs/$(date -u +%Y%m%dT%H%M%S%NZ)}"
case "$log_root" in /*) ;; *) log_root="$PWD/$log_root" ;; esac
# Bootstrap the new log directory before any repository/environment preparation.
if [[ -e "$log_root" ]]; then
    printf 'Log directory already exists; choose a new run directory: %s\n' "$log_root" >&2
    exit 2
fi
mkdir -p "$log_root"
completed=0
finish() {
    local code=$?
    trap - EXIT
    if [[ "$code" == 0 && "$completed" != 1 ]]; then code=1; fi
    printf '%s\n' "$code" > "$log_root/recipe.exit_code.txt"
    if [[ "$code" == 0 ]]; then
        printf 'PASS policy=portable-fp32-v2; author machine only. Logs: %s\n' "$log_root" | tee "$log_root/summary.txt"
    else
        printf 'FAIL exit=%s; receipt not issued. Logs: %s\n' "$code" "$log_root" | tee "$log_root/summary.txt" >&2
    fi
    exit "$code"
}
trap finish EXIT
run() {
    local name="$1" code
    shift
    printf '%q ' "$@" > "$log_root/$name.command.txt"
    printf '\n' >> "$log_root/$name.command.txt"
    printf '%s\0' "$@" > "$log_root/$name.argv.bin"
    printf '%s\n' "$PWD" > "$log_root/$name.cwd.txt"
    date -u +%Y-%m-%dT%H:%M:%SZ > "$log_root/$name.started_utc.txt"
    if "$@" > "$log_root/$name.stdout.txt" 2> "$log_root/$name.stderr.txt"; then code=0; else code=$?; fi
    printf '%s\n' "$code" > "$log_root/$name.exit_code.txt"
    date -u +%Y-%m-%dT%H:%M:%SZ > "$log_root/$name.finished_utc.txt"
    cat "$log_root/$name.stdout.txt"
    cat "$log_root/$name.stderr.txt" >&2
    return "$code"
}
run locate_script realpath -- "${BASH_SOURCE[0]}"
script_path="$(cat "$log_root/locate_script.stdout.txt")"
run discover_repo git -C "${script_path%/*}" rev-parse --show-toplevel
repo_root="$(cat "$log_root/discover_repo.stdout.txt")"
run enter_repo cd "$repo_root"
run base_commit git rev-parse HEAD
run working_tree git status --short
run kernel uname -a
run os cat /etc/os-release
run cpu lscpu
run source_hashes sha256sum -- "${script_path#"$repo_root"/}" \
    ml/scripts/authenticate_week3_sv2_package.py ml/scripts/record_week3_sv2_recipe.py \
    ml/scripts/diagnose_week3_sv2.py ml/scripts/verify_week3_sv2.py \
    ml/scripts/test_week3_sv2.py ml/scripts/test_week3_sv2_cache.py \
    ml/scripts/test_week3_sv2_policy.py ml/scripts/export_week3_sv2.py \
    ml/scripts/week3_common.py ml/scripts/week3_sv2_common.py ml/requirements-week3-onnx.txt
run prepare_environment_root mkdir -p "$task_root"
python="$task_root/venv/bin/python"
probe_python() {
    run venv_python "$python" -I -c 'import json, os, platform, sys
actual = platform.python_version()
print(json.dumps({"python": actual, "executable": sys.executable, "resolved_executable": os.path.realpath(sys.executable), "platform": sys.platform, "prefix": sys.prefix}))
if actual != "3.11.9" or sys.platform != "linux":
    print("Pinned venv requires native Linux Python 3.11.9; actual=" + actual + " platform=" + sys.platform, file=sys.stderr)
    sys.exit(2)'
}
if [[ -e "$task_root/venv" || -L "$task_root/venv" ]]; then probe_python; fi
if [[ ! -x "$task_root/bin/uv" ]]; then
    run download_uv curl -LsSf https://astral.sh/uv/install.sh -o "$task_root/uv-installer.sh"
    run uv_installer_hash sha256sum -- "$task_root/uv-installer.sh"
    run install_uv env UV_INSTALL_DIR="$task_root/bin" UV_NO_MODIFY_PATH=1 sh "$task_root/uv-installer.sh"
fi
uv="$task_root/bin/uv"
run uv_version "$uv" --version
if [[ ! -e "$task_root/venv" && ! -L "$task_root/venv" ]]; then
    run python_install "$uv" python install 3.11.9
    run create_venv "$uv" venv --python 3.11.9 "$task_root/venv"
    probe_python
fi
run install_torch "$uv" pip install --python "$python" 'torch==2.14.0+cu130' --index-url https://download.pytorch.org/whl/cu130
run install_onnx_numpy "$uv" pip install --python "$python" -r ml/requirements-week3-onnx.txt 'numpy==2.4.6'
run dependency_freeze "$uv" pip freeze --python "$python"
package="ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1"
anchor="a6d16809036c035936825b0e0cdc178e0bdf9f53ca81a132ece0522911d3d2a6"
run authenticate_before "$python" -B ml/scripts/authenticate_week3_sv2_package.py --package "$package"
run diagnostic "$python" -B ml/scripts/diagnose_week3_sv2.py --package "$package" --expected-manifest-sha256 "$anchor"
run verifier "$python" -B ml/scripts/verify_week3_sv2.py --package "$package" --expected-manifest-sha256 "$anchor" --recomputation-policy portable-fp32-v2
run tamper "$python" -B ml/scripts/test_week3_sv2.py --package "$package" --expected-manifest-sha256 "$anchor" --recomputation-policy portable-fp32-v2
run cache "$python" -B ml/scripts/test_week3_sv2_cache.py --recomputation-policy portable-fp32-v2
run policy "$python" -B ml/scripts/test_week3_sv2_policy.py
run authenticate_after "$python" -B ml/scripts/authenticate_week3_sv2_package.py --package "$package"
run receipt "$python" -B ml/scripts/record_week3_sv2_recipe.py --repo-root "$repo_root" --log-root "$log_root"
completed=1
