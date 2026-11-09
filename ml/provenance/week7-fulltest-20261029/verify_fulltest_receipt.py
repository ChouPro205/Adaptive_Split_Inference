"""Read-only review of delivered saved runtime evidence; writes a separate review."""
import argparse
import collections
import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path, required=True)
args = parser.parse_args()
OUT = args.output_dir.resolve()
if OUT.exists():
    raise ValueError('Use a new output directory; preserve existing receipts')
OUT.mkdir(parents=True)
REF = REPO / '.cache/week7-reconcile/accuracy-8544-delivery'
DOWNLOADS = REPO / '.cache/week7-fulltest-received-20261029'
ARCHIVE = DOWNLOADS / 'gui_sv3_fulltest.zip'
PIN = '612e5c3c29bf4d68f3ae4cdc3c9cd98481528f85dda0807b4e355150e5848c1c'
CHECKPOINT = '9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90'
checks = collections.Counter()
issues = []


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def save(name, data):
    with (OUT / name).open('x', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def git(*args):
    return subprocess.check_output(['git', '-c', 'safe.directory=' + REPO.as_posix(),
                                    '-C', str(REPO), '--no-optional-locks', *args])


def parse_checksums(raw):
    result = {}
    for line in raw.decode('utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64}) [ *](.+)', line)
        need(bool(match), 'Malformed checksum line')
        h, name = match.groups()
        need(name not in result, 'Duplicate checksum entry: ' + name)
        result[name] = h
    return result


def aggregate_paths(paths):
    rows = [(p.relative_to(REPO).as_posix(), digest(p.read_bytes()))
            for p in sorted(paths, key=lambda p: p.relative_to(REPO).as_posix())]
    return {'count': len(rows), 'path_and_raw_sha256_digest':
            digest(json.dumps(rows, ensure_ascii=True, separators=(',', ':')).encode())}


def verify_preservation():
    from urllib.parse import unquote
    before = read_json((HERE / 'preservation-before.json').read_bytes())
    base = before['base_commit']
    edited = before['edited_documents']
    for name, item in edited.items():
        original = git('show', base + ':' + name)
        need(digest(original) == item['base_sha256'], 'Original document differs')
        first, rest = original.split(b'\n\n', 1)
        expected = first + b'\n\n' + item['insertion_after_first_blank_line'].encode('utf-8') + rest
        need((REPO / name).read_bytes() == expected and digest(expected) == item['candidate_sha256'],
             'Non-allowlisted document edit: ' + name)
    tracked = git('ls-tree', '-r', '--name-only', base).decode().splitlines()
    kept = [REPO / n for n in tracked if n not in edited]
    assets = set()
    for scope in ['ml/data', 'ml/artifacts', '.cache/week7-reconcile']:
        assets.update(p for p in (REPO / scope).rglob('*') if p.is_file() and
                      p.suffix.lower() in ['.npy', '.npz', '.pt', '.pth', '.onnx', '.zip'])
    groups = {
        'all_preexisting_tracked_except_two_documents': aggregate_paths(kept),
        'ml_source_scripts_configs_manifests': aggregate_paths(p for p in kept if
            any(p.is_relative_to(REPO / s) for s in ['ml/src', 'ml/scripts', 'ml/configs', 'ml/manifests'])),
        'historical_tracked_provenance': aggregate_paths(p for p in kept if p.is_relative_to(REPO / 'ml/provenance')),
        'local_baseline_reference_weights_archives': aggregate_paths(assets),
        'bed2dfc_final_receipts_logs': aggregate_paths(p for p in (REPO / '.cache/week7-host-final-20261028').rglob('*') if p.is_file())
    }
    need(groups == before['groups'], 'Protected raw hashes differ')
    prefix = HERE.relative_to(REPO).as_posix() + '/'
    report = 'docs/sv3_week7_fulltest_review_20261029.md'
    allowed = set(edited) | {report}
    changed = git('diff', '--name-only', base).decode().splitlines()
    additions = git('ls-files', '--others', '--exclude-standard').decode().splitlines()
    need(all(n in allowed or n.startswith(prefix) for n in changed + additions), 'Change outside receipt/docs scope')
    need(git('branch', '--show-current').decode().strip() == 'dev/ml-sv3', 'Unexpected publication branch')
    for commit in [base, '08e4b4259a2757be7b663b88cc1c98607602d266',
                   '0545b470ebccb577baa8e11c1fff1c502f716b17',
                   '18e74ab198bd444e6cc0ae5eedaa9969132bd935',
                   '4e027b22b936f628e60aa4215aebb7f0ff66cfc4']:
        git('merge-base', '--is-ancestor', commit, 'HEAD')
    receipts = {}
    final = REPO / '.cache/week7-host-final-20261028'
    summary = read_json((final / 'final-summary.json').read_bytes())
    for name in ['nopeek-normal', 'nopeek-O', 'reconcile-normal', 'reconcile-O', 'demo', 'reference', 'verification']:
        receipt = final / (name + '.command.json')
        record = read_json(receipt.read_bytes())
        need(record['git_commit'] == 'bed2dfcf86a5d5e323575def5bbbb562f7ee6b51' and
             record['exit_code'] == 0 and record['sources_unchanged_during_command'], 'Historical command pin differs')
        need(sha(receipt) == summary['commands'][name]['receipt_sha256'], 'Historical receipt hash differs')
        for suffix, h in record['logs_sha256'].items():
            need(sha(final / (name + '.' + suffix)) == h, 'Historical log hash differs')
        for source, h in record['source_sha256'].items():
            need(digest((REPO / source).read_bytes().replace(b'\r\n', b'\n')) == h and
                 digest(git('show', record['git_commit'] + ':' + source).replace(b'\r\n', b'\n')) == h,
                 'Reused host test source differs')
        if name.startswith(('nopeek-', 'reconcile-')):
            count = 19 if name.startswith('nopeek-') else 18
            need(re.search(rf'Ran {count} tests in .*\n\nOK\s*$',
                           (final / (name + '.stderr.txt')).read_text('utf-8')), 'Historical test result differs')
        receipts[name] = {'tested_commit': record['git_commit'], 'receipt_sha256': sha(receipt),
                          'execution': 'REUSED_NOT_RERUN'}
    links = []
    documents = [REPO / n for n in edited] + [REPO / report, HERE / 'README.md']
    for path in documents:
        raw = path.read_bytes()
        need(not raw.startswith(b'\xef\xbb\xbf') and b'\r' not in raw, 'Document must be UTF-8/LF')
        text = raw.decode('utf-8')
        for link in re.findall(r'\[[^\]]*\]\(([^)\n]+)\)', text):
            if link.startswith(('http:', 'https:', 'mailto:')):
                continue
            target, _, anchor = unquote(link).partition('#')
            dest = (path.parent / target).resolve() if target else path
            need(dest.exists() and dest.is_relative_to(REPO), 'Missing/outside documentation link: ' + link)
            rel = dest.relative_to(REPO).as_posix()
            need(bool(git('ls-files', '--', rel).strip()) or rel in allowed or rel.startswith(prefix),
                 'Documentation points to ignored evidence')
            if anchor and dest.suffix == '.md':
                headings = re.findall(r'^#+\s+(.+)$', dest.read_text('utf-8'), re.M)
                slugs = [re.sub(r'[^\w\- ]', '', h.lower()).replace(' ', '-') for h in headings]
                need(anchor in slugs, 'Missing anchor: ' + link)
            links.append(path.relative_to(REPO).as_posix() + ' -> ' + link)
    for path in HERE.iterdir():
        if path.suffix in ['.json', '.md', '.py']:
            raw = path.read_bytes()
            raw.decode('utf-8')
            need(not raw.startswith(b'\xef\xbb\xbf') and b'\r' not in raw, 'New artifact encoding differs')
    git('diff', '--check', base)
    git('diff', '--cached', '--check')
    return {'base_commit': base, 'groups': groups, 'edited_document_count': len(edited),
            'documentation_links_checked': len(links), 'links': links, 'reused_host_receipts': receipts,
            'historical_verifiers': 'UNCHANGED; their old document gates certify their original snapshots only',
            'personal_confirmation': 'NOT_ATTESTED', 'owner_GVHD_acceptance': 'NOT_RECORDED_BY_THIS_UPDATE'}


def main():
    preservation = verify_preservation()
    start_status = git('status', '--porcelain=v1', '-uall')
    start_head = git('rev-parse', 'HEAD').decode().strip()
    inputs_before = {name: sha(DOWNLOADS / name) for name in
                     ['gui_sv3_fulltest.zip', 'gui_sv3_fulltest.zip.sha256.txt', 'summary.json']}
    expected_zip_sha = (DOWNLOADS / 'gui_sv3_fulltest.zip.sha256.txt').read_text().split()[0]
    need(inputs_before['gui_sv3_fulltest.zip'] == expected_zip_sha, 'Archive SHA differs')
    manifest = read_json((REF / 'manifest.json').read_bytes())
    need(sha(REF / 'manifest.json') == PIN, 'Frozen manifest differs')
    reference_before = {name: sha(REF / name) for name in ['manifest.json', *manifest['files']]}
    for name, item in manifest['files'].items():
        need(reference_before[name] == item['sha256'] and
             (REF / name).stat().st_size == item['size_bytes'], 'Frozen reference differs: ' + name)
    samples = list(csv.DictReader((REF / 'samples.csv').open(encoding='utf-8')))
    need(len(samples) == len({r['sample_id'] for r in samples}) == 8544, 'Reference IDs differ')
    input_arrays = {s: np.load(REF / f'inputs_s{s}.npy', mmap_mode='r', allow_pickle=False)
                    for s in [2, 5, 8]}
    with zipfile.ZipFile(ARCHIVE) as z:
        names = z.namelist()
        need(len(names) == len(set(names)), 'Duplicate ZIP member')
        need(all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and
                 '\\' not in n and not z.getinfo(n).is_dir() for n in names), 'Unsafe ZIP member')
        expected = parse_checksums(z.read('SHA256SUMS.txt'))
        need(set(expected) == set(names) - {'SHA256SUMS.txt'}, 'Archive checksum inventory differs')
        summary = read_json(z.read('summary.json'))
        need(z.read('summary.json') == (DOWNLOADS / 'summary.json').read_bytes(),
             'Separate summary differs from archived summary')
        received = read_json(z.read('receive_receipt.json'))
        need(received['reference_manifest_sha256'] == PIN and received['archive_sha256'] ==
             '74775bf3ea3c6fde306e601315c32b8293d3db74fc12975515b503c406fd3429',
             'Received input package identity differs')
        output_bytes = z.read('runtime/full/sv2-output-real.json')
        data = read_json(output_bytes)
        rows = data['rows']
        keyed = {(r['split_point_s'], r['sample_index']): r for r in rows}
        need(data['execution_scope'] == 'FULL_25632' and len(rows) == len(keyed) == 25632,
             'Full-run count or unique row keys differ')
        need(set(keyed) == {(s, i) for s in [2, 5, 8] for i in range(8544)}, 'Missing row keys')
        for (s, i), row in keyed.items():
            need(row['sample_id'] == samples[i]['sample_id'], 'Wrong sample-ID mapping')
        all_hashes = {}
        nested = []
        tensor_metadata = {}
        for index, name in enumerate(names):
            raw = z.read(name)  # Reading checks CRC as well as the explicit SHA below.
            all_hashes[name] = digest(raw)
            if name != 'SHA256SUMS.txt':
                need(all_hashes[name] == expected[name], 'Archive member SHA differs: ' + name)
                checks['archive_member_sha256_and_crc'] += 1
            if name.endswith('/sha256sum_files.txt') or name.endswith('/sha256sum_row.txt'):
                nested.append((name, parse_checksums(raw)))
            match = re.fullmatch(r'runtime/full/s([258])/(\d{5})/(.+)', name)
            if not match:
                continue
            s, i, leaf = int(match[1]), int(match[2]), match[3]
            need((s, i) in keyed, 'Unexpected raw row member')
            row = keyed[s, i]
            if leaf == 'input_2.npy':
                array = np.load(io.BytesIO(raw), allow_pickle=False)
                frozen = input_arrays[s][i:i+1]
                need(array.shape == frozen.shape and array.dtype == frozen.dtype and
                     array.tobytes() == frozen.tobytes(), 'Input bytes differ from frozen sample')
                need(digest(raw) == row['input_sha256'], 'Row input digest differs')
                checks['raw_input_matches_frozen_sample_bit_exact'] += 1
            elif leaf == 'row.json':
                need(read_json(raw) == row, 'Aggregate row differs from raw row')
                checks['aggregate_equals_saved_row'] += 1
            elif leaf == 'attempt/runner.json':
                result = read_json(raw)
                need(result['execution'] == 'root_graph' and result['split'] == s and
                     len(result['samples']) == 1 and result['samples'][0]['logits'] == row['logits'],
                     'Native runner result differs')
                need(result['quantization_rounding'] == 'DPU_ROUND_HALF_TO_POSITIVE_INFINITY',
                     'Unknown native rounding')
                metadata = {k: result[k] for k in ['input_tensor', 'output_tensor']}
                tensor_metadata.setdefault(str(s), metadata)
                need(tensor_metadata[str(s)] == metadata, 'Tensor metadata changed within split')
                checks['native_runner_logits_match'] += 1
            elif leaf == 'attempt/runner.log':
                log = raw.decode('utf-8')
                final = re.findall(r'^FINAL_LOGITS=(.+)$', log, re.M)
                need(len(final) == 1 and read_json(final[0]) == row['logits'] and
                     f'STAGE=execute_root_graph split={s} sample=0' in log and
                     'FULL_TAIL_EXECUTED samples=1' in log, 'Raw execution log differs')
                checks['raw_runner_log_matches'] += 1
            elif leaf == 'attempt/command.json':
                command = read_json(raw)
                need(command['exit_code'] == 0 and command['status'] == 'OK', 'Runtime command failed')
                argv = command['argv']
                need(argv[argv.index('--split') + 1] == str(s) and
                     argv[argv.index('--model') + 1].endswith(f'/tail_s{s}.xmodel') and
                     argv[argv.index('--input') + 1].endswith(f'/s{s}/{i:05d}/input_2.npy'),
                     'Command does not address corresponding sample/model: ' + name)
                checks['runtime_commands_complete_successful'] += 1
            elif leaf not in ['attempt/sha256sum_files.txt', 'sha256sum_row.txt']:
                raise ValueError('Unexpected raw member: ' + name)
            if index % 40000 == 0:
                print('Verified archive members', index, flush=True)
        for name, inventory in nested:
            prefix = name.rsplit('/', 1)[0] + '/'
            for relative, h in inventory.items():
                target = prefix + relative
                need(target in all_hashes and all_hashes[target] == h, 'Nested inventory differs: ' + target)
                checks['nested_checksum_bindings'] += 1
        for key in ['raw_input_matches_frozen_sample_bit_exact', 'aggregate_equals_saved_row',
                    'native_runner_logits_match', 'raw_runner_log_matches', 'runtime_commands_complete_successful']:
            need(checks[key] == 25632, 'Incomplete raw evidence: ' + key)
        provenance = data['provenance']
        identity = read_json(z.read('runtime/full/identity.json'))
        source = read_json(z.read('source/source.json'))
        need(all_hashes['runtime/build/asi-tail-runner'] == provenance['runner_sha256'] == identity['runner_sha256'],
             'Runner binary identity differs')
        need(all_hashes['source/tools/run_fulltest.py'] == identity['driver_sha256'], 'Driver hash differs')
        need(source['runner_source_commit'] == provenance['source_commit'] == identity['runner_source_commit'],
             'Source commit identity differs')
        need(identity['cpu_plugins_sha256'] == provenance['cpu_plugins_sha256'], 'Plugin provenance differs')
        preflight = read_json(z.read('runtime/cpu_preflight.json'))
        need(preflight['all_loadable'], 'CPU plugin load failed')
        for library in preflight['libraries']:
            if 'sha256' in library:
                need(provenance['cpu_plugins_sha256'][PurePosixPath(library['library']).name] == library['sha256'],
                     'Preflight plugin digest differs')
        source_bound = []
        for n in names:
            if n.startswith('source/edge/'):
                repository_path = n.removeprefix('source/')
                original = git('show', source['runner_source_commit'] + ':' + repository_path)
                need(digest(original) == all_hashes[n], 'Runner source differs from declared commit')
                source_bound.append(repository_path)
        compile_manifest = read_json(z.read('artifacts/compile_manifest.json'))
        need(all_hashes['artifacts/arch.json'] == compile_manifest['arch_json_sha256'], 'DPU arch differs')
        calib = provenance['calibration']
        calibration_csv = z.read('artifacts/calibration_samples.csv')
        need(digest(calibration_csv) == manifest['expected_calibration']['samples_csv_sha256'] == calib['samples_csv_sha256'],
             'Calibration sample CSV differs')
        calibration_rows = list(csv.DictReader(io.StringIO(calibration_csv.decode('utf-8'))))
        need(len(calibration_rows) == 20 and all(r['split'] == 'val' for r in calibration_rows) and
             [r['sample_id'] for r in calibration_rows] == calib['sample_ids'] == manifest['expected_calibration']['sample_ids'],
             'Calibration membership differs')
        need(not {r['sample_id'] for r in calibration_rows} & {r['sample_id'] for r in samples}, 'Test calibration leakage')
        lineage_checks = []
        for s in [2, 5, 8]:
            model = provenance['models'][str(s)]
            original = next(item for item in compile_manifest['splits'] if item['split'] == s)
            quant = read_json(z.read(f'artifacts/quantize_s{s}.provenance.json'))
            need(original['quantization'] == quant, 'Compile and quantize records differ')
            need(all_hashes[f'artifacts/models/tail_s{s}.xmodel'] == model['xmodel_sha256'] ==
                 original['xmodel_sha256'] == manifest['expected_xmodel_sha256'][str(s)] == identity['models'][str(s)],
                 'Compiled deployment model differs')
            need(all_hashes[f'artifacts/s{s}/quant_info.json'] == model['quant_info_sha256'] and
                 all_hashes[f'artifacts/logs/s{s}/compiler.txt'] == model['compile_log_sha256'],
                 'Quantizer or compile log bytes differ')
            need(all_hashes[f'artifacts/s{s}/tail_{s}_int.xmodel'] == quant['xmodel_sha256'],
                 'Compiler input model differs')
            need(all_hashes[f'artifacts/golden/z_s{s}.npy'] == calib['golden_sha256'][str(s)] ==
                 quant['calibration']['sha256'] == manifest['expected_calibration']['golden_sha256'][str(s)],
                 'Calibration activation bytes differ')
            need(quant['checkpoint']['sha256'] == CHECKPOINT and quant['calibration']['declared_split'] == 'val' and
                 not quant['synthetic'] and not quant['dry_run'], 'Quantization source identity differs')
            need(f'tail_{s}_int.xmodel' in original['compiler_command'] and
                 all_hashes[f'artifacts/quantize_s{s}.provenance.json'] ==
                 calib['artifacts_sha256'][f'quantize_s{s}.provenance.json'], 'Compiler/quantizer lineage differs')
            lineage_checks.append(s)
        # Run only the checked-in acceptance evaluator, never programs from the delivered archive.
        raw_copy = OUT / 'sv2-output-real.json'
        with raw_copy.open('xb') as f:
            f.write(output_bytes)
        sys.path.insert(0, str(REPO / 'ml/scripts'))
        sys.path.insert(0, str(REPO / 'ml/src'))
        os.environ['GIT_CONFIG_COUNT'] = '1'
        os.environ['GIT_CONFIG_KEY_0'] = 'safe.directory'
        os.environ['GIT_CONFIG_VALUE_0'] = REPO.as_posix()
        import week7_dpu_accuracy as evaluator
        evaluation = evaluator.evaluate(REF, raw_copy)
        evaluator.ensure_result_coverage(evaluation)
        pinned_evaluation = read_json((HERE / 'evaluation.json').read_bytes())
        need({k: v for k, v in evaluation.items() if k != 'input_commit'} ==
             {k: v for k, v in pinned_evaluation.items() if k != 'input_commit'},
             'Recomputed evaluation differs from pinned review')
        save('evaluation-recomputed.json', evaluation)
        for result in evaluation['results']:
            s = result['split_point_s']
            declared = next(item for item in summary['splits'] if item['split'] == s)
            need(result['correct_dpu'] == declared['correct'] and
                 result['valid_output_metrics']['confusion_matrix_true_rows_predicted_columns'] ==
                 declared['confusion_true_rows_pred_columns'], 'Summary metrics differ from independent evaluation')
        for name, h in inputs_before.items():
            need(sha(DOWNLOADS / name) == h, 'Delivered input modified')
        for name, h in reference_before.items():
            need(sha(REF / name) == h, 'Frozen reference modified')
        need(git('status', '--porcelain=v1', '-uall') == start_status and
             git('rev-parse', 'HEAD').decode().strip() == start_head, 'Checkout state changed')
        result = {'scope': 'INDEPENDENT_SAVED_EVIDENCE_REVIEW_NO_NEW_BOARD_EXECUTION_OR_OWNER_SIGNATURE',
                  'review_source_commit': start_head,
                  'verdict': 'PASS_FROZEN_ACCURACY_GATE_ARTIFACTS_REVIEWED_OWNER_ACCEPTANCE_SEPARATE',
                  'archive_bytes': ARCHIVE.stat().st_size, 'delivered_file_sha256': inputs_before,
                  'zip_members': len(names), 'uncompressed_bytes': sum(i.file_size for i in z.infolist()),
                  'reference_manifest_sha256': PIN, 'checks': dict(checks),
                  'runner_source_files_bound_to_commit': source_bound,
                  'lineage_reviewed_splits': lineage_checks, 'native_tensor_metadata': tensor_metadata,
                  'result_summary_matches_delivered_summary': True,
                  'class_imbalance_note': 'S/F/Q recall is zero in all three splits and in frozen FP32 baseline; no new threshold imposed.',
                  'delivery_notices': {'outer_summary': summary['scope'], 'full_run': read_json(z.read('runtime/full/summary.json'))},
                  'unchanged': ['delivered files', 'frozen input/reference assets', 'checkout status and HEAD'],
                  'limitations': ['No new hardware run', 'No owner/GVHD signature',
                                  'CPU plugin library bytes are not included; hashes match identity/preflight/output provenance.',
                                  'Each sample starts a new runner process; not steady-state latency or energy evidence.'],
                  'results': evaluation['results'], 'issues': issues, 'preservation': preservation,
                  'binding': 'New saved-evidence check at checked_head; core host suites reused at bed2dfc.',
                  'checked_head': start_head, 'receipt_verifier_sha256': sha(Path(__file__))}
        save('verification.json', result)
        print(json.dumps({'verdict': result['verdict'], 'checks': dict(checks), 'results': [
            {k: r[k] for k in ['split_point_s', 'status', 'received', 'valid', 'correct_dpu',
                               'accuracy_all_8544_percent', 'accuracy_drop_pp']} for r in evaluation['results']]}, indent=2))


if __name__ == '__main__':
    main()
