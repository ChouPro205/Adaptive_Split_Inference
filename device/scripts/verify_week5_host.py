"""Layer A: exact SV3 bytes. Layer B: actual head C against Python quantization."""
import argparse
import ctypes as ct
from pathlib import Path
import subprocess
import sys
import numpy as np
from week5_common import (ROOT, PACKAGE, R3, Quantizer, FP, need, sha, write_json, authenticate,
                         generate, source_hashes, quantize_per_channel, to_ncl)
from verify_week4_host import Result

def verify(output, compiler):
    need(not output.exists(), 'Choose a new host evidence directory')
    manifest, proof, history = authenticate()
    _, splits, _, inputs, ids = generate(ROOT, generated_dir=output / 'generated')
    for name in ('week4_inputs.h', 'week4_graph.h'):
        need(sha(output / 'generated' / name) == sha(ROOT / 'device/generated' / name), 'Accepted generated header differs')
    quant = Quantizer(output, compiler)
    library = output / ('head.dll' if sys.platform == 'win32' else 'head.so')
    command = [compiler, '-std=c99', '-O2', '-ffp-contract=off', '-fno-fast-math', '-Wall', '-Wextra', '-Werror',
               '-shared', *([] if sys.platform == 'win32' else ['-fPIC']),
               '-I', str(ROOT / 'device/src'), '-I', str(output / 'generated'), '-I', str(ROOT / R3 / 'firmware'),
               str(ROOT / 'device/src/week4_head.c'), '-o', str(library)]
    subprocess.run(command, check=True)
    head = ct.CDLL(str(library))
    head.week4_run_head.argtypes = [ct.c_uint, FP, ct.POINTER(Result)]
    head.week4_run_head.restype = ct.c_int
    goldens = [np.load(ROOT / PACKAGE / s['golden_path'], allow_pickle=False) for s in splits['splits']]
    entries = {(e['sample_index'], e['split_point_s']): e for e in manifest['entries']}
    need(set(entries) == {(n, s) for n in range(20) for s in range(11)}, 'Reference ID matrix differs')
    cases = [(n, s) for n in range(20) for s in range(11)]
    rows, differences = [], []
    actuals = [np.empty_like(g) for g in goldens]
    cached = {}
    for phase, order in [('forward', cases), ('reverse', list(reversed(cases))), ('repeat', cases)]:
        for n, s in order:
            entry = entries[n, s]
            need(entry['sample_id'] == ids[n] and entry['shape_original'] == list(goldens[s][n:n+1].shape), 'Reference shape/ID mismatch')
            golden = goldens[s][n:n+1].copy()
            qg, sg = quant.quantize(to_ncl(golden, s))
            base = ROOT / 'ml/artifacts/week5/quantization20'
            need(qg.tobytes() == (base / entry['int8_path']).read_bytes(), f'Layer A INT8 mismatch n{n}s{s}')
            need(sg.tobytes() == (base / entry['scale_path']).read_bytes(), f'Layer A FP16 mismatch n{n}s{s}')
            need(sha(base / entry['int8_path']) == entry['int8_sha256'] and sha(base / entry['scale_path']) == entry['scale_sha256'], 'Reference hashes differ')
            before = inputs[n].tobytes()
            result = Result()
            need(head.week4_run_head(s, inputs[n].ctypes.data_as(FP), ct.byref(result)) == 0, 'Head C rejected valid case')
            shape = tuple(result.shape.dims[:result.shape.rank])
            need(shape == golden.shape and result.shape.count == golden.size, 'Head C shape differs')
            # The borrowed head buffer dies on the next call. Copy immediately.
            actual = np.ctypeslib.as_array(result.values, shape=(result.shape.count,)).copy().reshape(shape)
            need(np.isfinite(actual).all() and inputs[n].tobytes() == before, 'Head invalid or input mutated')
            error = float(np.max(np.abs(actual.astype(np.float64) - golden.astype(np.float64))))
            need(error < 1e-3, f'Head strict FP32 gate failed n{n}s{s}: {error}')
            if s == 0:
                need(actual.tobytes() == golden.tobytes(), 's0 identity bits differ')
            qc, sc = quant.quantize(to_ncl(actual, s))
            qo, so = quantize_per_channel(to_ncl(actual, s))
            need(qc.tobytes() == qo.tobytes() and sc.tobytes() == so.tobytes(), f'Layer B C quantizer differs from actual-activation oracle n{n}s{s}')
            need(actual.tobytes() == np.ctypeslib.as_array(result.values, shape=(result.shape.count,)).tobytes(), 'Quantization mutated head workspace')
            current = (actual.tobytes(), qc.tobytes(), sc.tobytes())
            if phase != 'forward':
                need(current == cached[n, s], 'Order/repeat retained stale state')
                continue
            cached[n, s] = current
            actuals[s][n:n+1] = actual
            qi = np.flatnonzero(qc.ravel() != qg.ravel())
            si = np.flatnonzero(sc.view('<u2').ravel() != sg.view('<u2').ravel())
            row = {'sample_index': n, 'sample_id': ids[n], 'split': s, 'max_abs_error': error,
                   'golden_int8_differences': len(qi), 'golden_scale_differences': len(si), 'oracle_exact': True}
            rows.append(row)
            if len(qi) or len(si):
                zn = to_ncl(actual, s).reshape(-1)
                zg = to_ncl(golden, s).reshape(-1)
                length = to_ncl(actual, s).shape[-1]
                details = []
                for i in qi:
                    ch = int(i) // length
                    rc = np.float32(zn[i] / np.float32(sc.ravel()[ch]))
                    rg = np.float32(zg[i] / np.float32(sg.ravel()[ch]))
                    details.append({'offset': int(i), 'channel': ch, 'golden_fp32': float(zg[i]), 'head_c_fp32': float(zn[i]),
                        'golden_fp32_bits': int(zg.view('<u4')[i]), 'head_c_fp32_bits': int(zn.view('<u4')[i]),
                        'golden_ratio_fp32': float(rg), 'head_c_ratio_fp32': float(rc),
                        'golden_q': int(qg.ravel()[i]), 'head_c_q': int(qc.ravel()[i]),
                        'golden_scale_bits': int(sg.view('<u2').ravel()[ch]), 'head_c_scale_bits': int(sc.view('<u2').ravel()[ch])})
                scale_details = []
                for ch in si:
                    nc, ng = to_ncl(actual, s)[0, ch], to_ncl(golden, s)[0, ch]
                    midpoint = float((np.float32(sc.ravel()[ch])+np.float32(sg.ravel()[ch])) * np.float32(.5))
                    scale_details.append({'channel': int(ch), 'head_c_raw_scale_fp32': float(np.max(np.abs(nc))/np.float32(127)),
                        'golden_raw_scale_fp32': float(np.max(np.abs(ng))/np.float32(127)),
                        'fp16_rounding_midpoint': midpoint,
                        'golden_scale_bits': int(sg.view('<u2').ravel()[ch]), 'head_c_scale_bits': int(sc.view('<u2').ravel()[ch])})
                differences.append({**row, 'explanation': 'FP32 head accumulation changes quantization rounding; C exactly matches Python applied to actual C activation',
                                    'int8_details': details, 'scale_details': scale_details})
    for s, values in enumerate(actuals):
        np.save(output / f'head_c_s{s}.npy', values, allow_pickle=False)
    report = {'status': 'PASS', 'scope': 'HOST_C_ONLY', 'layer_a_exact_cases': 220, 'layer_b_oracle_exact_cases': 220,
              'forward_reverse_repeat_cases_per_layer': 660, 'threshold_strict': 1e-3,
              'max_head_abs_error': max(r['max_abs_error'] for r in rows), 'rows': rows,
              'golden_differing_cases': len(differences), 'unexplained_mismatches': 0,
              'difference_analysis': differences, 'commands': [quant.command, command],
              'source_sha256': source_hashes(), 'handoff_authentication': proof, 'accepted_r3_provenance': history,
              'mcu_validation': 'PENDING', 'optimized_python': bool(sys.flags.optimize)}
    write_json(output / 'week5_host.json', report)
    print(f'HOST_C PASS: Layer A 220 byte-exact; Layer B 220 oracle-exact; reverse/repeat PASS; explained golden differences={len(differences)}; max FP32 error={report["max_head_abs_error"]}', flush=True)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--compiler', default='gcc')
    a = p.parse_args()
    verify(a.output, a.compiler)
