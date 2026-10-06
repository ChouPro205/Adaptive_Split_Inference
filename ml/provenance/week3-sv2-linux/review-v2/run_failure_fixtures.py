"""Run negative recipe fixtures on WSL; never modify the real v1 package."""
import json
import os
from pathlib import Path
import subprocess
import sys
from review_validation import REV, save, digest

root = Path(__file__).resolve().parents[4]
out = Path(__file__).resolve().parent
wrapper = out / "run_logged_v2.py"
fixture = root / "exports/week3-sv2-review-v2-20261006/authentication_fixture"
fixture.parent.mkdir(parents=True, exist_ok=True)
if not fixture.exists():
    subprocess.run(["git", "clone", "--no-hardlinks", "--quiet", str(root), str(fixture)], check=True)
else:
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=fixture).decode().strip() == "415d53431c81c465784dc08be42b568827a39cff"
source_files = [p.relative_to(root) for p in (root / "ml/scripts").glob("*week3*") if p.is_file()]
source_files.append(Path("ml/requirements-week3-onnx.txt"))
for relative in source_files:
    target = fixture / relative; target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((root / relative).read_bytes())
bad = fixture / "ml/artifacts/week3/mitdb-week3-sv2-fp32-20261001-v1/manifest.json"
bad.parent.mkdir(parents=True, exist_ok=True); bad.write_bytes(b"{}\n")
subprocess.run(["wsl", "-d", "Ubuntu-24.04", "--", "bash", "ml/provenance/week3-sv2-linux/review-v2/prepare_failure_fixture.sh"], cwd=root, check=True)
linux_root = "/mnt/c/Users/Admin/Adaptive_Split_Inference"
results = {}
for name, cwd_source, environment in (
    ("recipe_wrong_python", linux_root, "/home/kyanh/asi-week3-review-v2-fixtures/wrong-python"),
    ("recipe_bad_manifest", linux_root + "/" + fixture.relative_to(root).as_posix(), "/home/kyanh/asi-week3-review-v2-clean-env")):
    logs = linux_root + "/" + REV + "/" + name
    script = cwd_source + "/ml/scripts/reproduce_week3_sv2_linux.sh"
    argv = [sys.executable, "-B", str(wrapper), name, "wsl", "-d", "Ubuntu-24.04", "--", "env",
            "ASI_LINUX_ENV_ROOT=" + environment, "ASI_LINUX_LOG_ROOT=" + logs, "bash", script]
    result = subprocess.run(argv, cwd=root, capture_output=True)
    expected = 2 if name == "recipe_wrong_python" else 1
    assert result.returncode == expected, result.stdout.decode(errors="replace") + result.stderr.decode(errors="replace")
    run_logs = out / name
    assert (run_logs / "recipe.exit_code.txt").read_text().strip() == str(expected)
    assert not (run_logs / "receipt.json").exists()
    assert "PASS" not in (out / f"{name}.stdout.txt").read_text()
    step = "venv_python" if name == "recipe_wrong_python" else "authenticate_before"
    error = (run_logs / f"{step}.stderr.txt").read_text()
    assert ("actual=3.12.3" if name == "recipe_wrong_python" else "Manifest anchor mismatch") in error
    assert not (run_logs / "diagnostic.exit_code.txt").exists()
    for extension in ("command.txt", "argv.bin", "cwd.txt", "stdout.txt", "stderr.txt", "exit_code.txt"):
        assert (run_logs / f"{step}.{extension}").exists()
    results[name] = {"status": "PASS_EXPECTED_REJECTION", "recipe_exit_code": expected,
                     "failed_step": step, "failure_logged": True, "no_success_output_or_receipt": True,
                     "diagnostic_not_started": True, "error": error.strip()}
save(out / "failure_fixtures.json", {"source": "Current recipe review-v2", "fixture_repo": fixture.relative_to(root).as_posix(),
     "bad_fixture_manifest_sha256": digest(bad.read_bytes()), "results": results,
     "real_package_mutated": False})
print(json.dumps(results, indent=2))
