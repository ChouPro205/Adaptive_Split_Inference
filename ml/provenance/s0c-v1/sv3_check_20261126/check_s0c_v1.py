"""SV3 receipt check of the S0c v1 package received from SV1 on 2026-11-25.

Run from the repository root with the ML venv:
  ml/.venv/Scripts/python.exe -B -I ml/provenance/s0c-v1/sv3_check_20261126/check_s0c_v1.py <package A dir> <output json>

Checks: (1) every file listed in ml/provenance/s0c-v1/SHA256SUMS.txt has that SHA-256;
(2) x of the 20 golden beats equals golden/z_s0.npy[:, 0, :] of package A bit for bit;
(3) the bound reference s0c_v1_ref.py reproduces every golden array and Rice body.
Reads files only; no MITDB data, no training.
"""
import hashlib, importlib.util, json, sys
from pathlib import Path
import numpy as np

ROOT = Path('ml/provenance/s0c-v1')
pkg, out = Path(sys.argv[1]), Path(sys.argv[2])
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
sums = {}
for line in (ROOT / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
    if line.strip():
        h, name = line.split(maxsplit=1)
        sums[name.lstrip('*')] = (h, sha(ROOT / name.lstrip('*')))
z_path = pkg / 'golden' / 'z_s0.npy'
manifest_sha = sha(pkg / 'manifest.json')
z_sha = sha(z_path)
z_listed = z_sha in (pkg / 'manifest.json').read_text(encoding='utf-8')
z = np.load(z_path, allow_pickle=False)
d = np.load(ROOT / 's0c_v1_golden20.npz', allow_pickle=False)
x = d['x']
x_equal = x.dtype == z.dtype and x.shape == z[:, 0, :].shape and np.array_equal(x.view(np.uint32), z[:, 0, :].view(np.uint32))
spec = importlib.util.spec_from_file_location('s0c_v1_ref', ROOT / 's0c_v1_ref.py')
ref = importlib.util.module_from_spec(spec); spec.loader.exec_module(ref)
beats = json.loads((ROOT / 's0c_v1_golden20.json').read_text(encoding='utf-8'))['beats']
bits = lambda a: np.asarray(a, dtype=np.float32).view(np.uint32)
counts = dict.fromkeys(['reduced_v46', 'q', 'scale_fp16', 'rice_body_hex', 'dequantized_v46', 'reconstructed_x360', 'rice_roundtrip'], 0)
for i in range(x.shape[0]):
    body, scale, q = ref.encode(x[i])
    v, y = ref.decode(body, scale)
    counts['reduced_v46'] += bool(np.array_equal(bits(ref.reduce46(x[i])), bits(d['reduced_v46'][i])))
    counts['q'] += bool(np.array_equal(q, d['q'][i]))
    counts['scale_fp16'] += bool(np.float16(scale).view(np.uint16) == np.asarray(d['scale_fp16'][i], dtype=np.float16).view(np.uint16))
    counts['rice_body_hex'] += body.hex() == beats[i]['body_hex']
    counts['dequantized_v46'] += bool(np.array_equal(bits(v), bits(d['dequantized_v46'][i])))
    counts['reconstructed_x360'] += bool(np.array_equal(bits(y), bits(d['reconstructed_x360'][i])))
    counts['rice_roundtrip'] += bool(np.array_equal(ref.rice_decode(body), q))
result = {
    'type': 'SV3_RECEIPT_CHECK_S0C_V1', 'date': '2026-11-26', 'prepared_by': 'SV3',
    'files_sha256': {k: {'listed': v[0], 'computed': v[1], 'match': v[0] == v[1]} for k, v in sums.items()},
    'package_A': {'manifest_sha256': manifest_sha, 'golden_z_s0_sha256': z_sha, 'z_s0_listed_in_manifest': z_listed},
    'golden_x_equals_package_A_z_s0': {'beats': int(x.shape[0]), 'bit_equal': bool(x_equal)},
    'reference_reproduces_golden': {'beats': int(x.shape[0]), 'equal_counts': counts},
    'scope': 'Files of the S0c v1 package only; no MITDB array read, no model run',
}
out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
ok = all(v[0] == v[1] for v in sums.values()) and z_listed and x_equal and all(c == x.shape[0] for c in counts.values())
print('ALL_OK' if ok else 'MISMATCH', json.dumps(counts))
sys.exit(0 if ok else 1)
