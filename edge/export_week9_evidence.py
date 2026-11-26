"""Verify saved Week 9 evidence and export portable tables, without inference."""
import argparse
import contextlib
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import zipfile

ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = ROOT / 'edge/server/week9'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def anchor(path):
    path = Path(path)
    return dict(name=path.name, bytes=path.stat().st_size, sha256=sha(path))


def inside(root, path):
    path = Path(path).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError('Input pointer escapes the acquisition session')
    return path


def verify_prepared(root):
    for line in (root / 'sha256sum_prepare.txt').read_text().splitlines():
        digest, name = line.split('  ', 1)
        path = inside(root, root / name)
        if path.is_symlink() or sha(path) != digest:
            raise ValueError('Prepared source checksum differs: ' + name)


def csv_file(path, rows):
    if not rows:
        raise ValueError('Cannot publish an empty table')
    with Path(path).open('x', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def verify_review_zip(session, analysis):
    matches = []
    for path in sorted(session.glob('gui_review_windows*.zip')):
        receipt = path.with_name(path.name + '.sha256.txt')
        if not receipt.is_file():
            continue
        digest, name = receipt.read_text().strip().split('  ', 1)
        if name != path.name or sha(path) != digest:
            raise ValueError('W10 ZIP checksum mismatch')
        with zipfile.ZipFile(path) as z:
            if z.testzip():
                raise ValueError('W10 ZIP CRC mismatch')
            if z.read('analysis/review.json') != (analysis / 'review.json').read_bytes():
                continue
            for kind in ('idle', 'varying'):
                for name in ('summary.json', 'oneway_samples.jsonl', 'sha256sum_results.txt'):
                    if z.read('analysis/' + kind + '/' + name) != (analysis / kind / name).read_bytes():
                        raise ValueError('W10 ZIP differs from the selected analysis')
            roots = dict(board=inside(session, (session / 'received_board.txt').read_text().strip()),
                         receiver=inside(session, (session / 'received_windows.txt').read_text().strip()))
            for entry in z.infolist():
                if entry.is_dir():
                    continue
                parts = entry.filename.split('/', 1)
                if len(parts) == 2 and parts[0] in roots:
                    local = inside(roots[parts[0]], roots[parts[0]] / parts[1])
                    if z.read(entry) != local.read_bytes():
                        raise ValueError('W10 raw archive differs from received evidence')
        matches.append(path)
    if not matches:
        raise ValueError('No verified W10 archive matches the current analysis')
    return anchor(matches[0])


def calibrated_runs(session, analysis, measurement):
    result = {}
    inputs = {}
    samples = []
    intervals = []
    source_files = {}
    with tempfile.TemporaryDirectory(prefix='asi_week9_verify_') as tmp:
        for kind in ('idle', 'varying'):
            folder = analysis / kind
            measurement.verify(folder)
            paths = read(folder / 'source_paths.json')
            run = inside(session, paths['run'])
            receiver = inside(session, paths['receiver'])
            server = inside(session, paths['clock_server'])
            if paths['analyzer_sha256'] != sha(IMPLEMENTATION / 'oneway.py'):
                raise ValueError('Published analyzer is not the recorded analyzer')
            for path in (run, receiver, server):
                measurement.verify(path)
            measurement.verify(run.parent)
            recv = read(receiver / 'receiver.json')
            if (recv.get('platform') != 'Windows' or recv['receiver_id'] != 'GW_TRUNG'
                    or recv.get('role') != 'gateway'):
                raise ValueError('Expected native Windows GW_TRUNG gateway evidence')
            with contextlib.redirect_stdout(io.StringIO()):
                recomputed = measurement.analyze(SimpleNamespace(
                    run=run, receiver=receiver, clock_server=server,
                    output=Path(tmp) / kind))
            original = read(folder / 'summary.json')
            if json.loads(json.dumps(recomputed)) != original:
                raise ValueError('Saved statistics do not reproduce: ' + kind)
            calculated = measurement.rows(Path(tmp) / kind / 'oneway_samples.jsonl')
            if calculated != measurement.rows(folder / 'oneway_samples.jsonl'):
                raise ValueError('Saved per-message clock bounds do not reproduce')
            backend = read(session / 'expected_backend.json')
            if any(original['backend'].get(k) != v for k, v in backend.items()):
                raise ValueError('Measured backend differs from the prepared pins')
            meta = read(run / 'queue_run.json')
            sent = measurement.rows(run / 'mqtt_sent.jsonl')
            received = measurement.rows(receiver / 'received.jsonl')
            by_seq = {row['state']['seq_number']: row for row in received}
            for i, row in enumerate(sent):
                seq = row['seq_number']
                rec = by_seq.get(seq)
                prev_rec = by_seq.get(sent[i - 1]['seq_number']) if i else None
                intervals.append(dict(kind=kind, run_id=original['run_id'], seq_number=seq,
                    t_publish_interval_ms=None if not i else
                        (row['publisher_monotonic_ns'] - sent[i - 1]['publisher_monotonic_ns']) / 1e6,
                    t_receive_interval_ms=None if not rec or not prev_rec else
                        (rec['receive_perf_ns'] - prev_rec['receive_perf_ns']) / 1e6,
                    t_schedule_late_ms=row['schedule_late_ms'],
                    queue_length_jobs=row['queue_length_jobs'], status=row['status']))
            for row in calculated:
                samples.append(dict(kind=kind, run_id=row['run_id'], seq_number=row['seq_number'],
                    t_one_way_lower_ms=row['lower_ms'], t_one_way_midpoint_ms=row['estimate_ms'],
                    t_one_way_upper_ms=row['upper_ms'], classification=row['comparison']))
            value = {k: original[k] for k in (
                'run_id', 'status', 'matching', 'one_way_ms', 'lower_ms', 'upper_ms',
                'interval_width_ms', 'threshold_20ms', 'publish_interval_ms',
                'receive_interval_ms', 'ack_rtt_diagnostic_ms', 'queue',
                'service_ms', 'background_queue_wait_ms', 'measurement_limitations')}
            calibration = original['calibration']
            value['calibration'] = dict(probes=calibration['probes'], errors=calibration['errors'],
                max_probe_gap_ms=calibration['max_probe_gap_ms'],
                receive_clock=calibration['receive_clock'],
                drift_ppm_interval=calibration['model']['drift_ppm_interval'],
                model='feasible affine relation, no equal forward/reverse path assumption')
            value['receiver'] = {k: original['receiver'][k] for k in ('id', 'role', 'network_label')}
            value['receiver']['platform'] = recv['platform']
            value['scenario'] = meta['scenario']
            value['seed'] = meta['config']['seed']
            value['warmup'] = read(run / 'warmup.json')
            times = [row['receive_perf_ns'] for row in received]
            value['receive_gaps_over_500ms'] = sum(b - a > 500_000_000 for a, b in zip(times, times[1:]))
            value['mean_upper_bound_lt_20ms'] = bool(original['matching']['complete']
                and original['matching']['publish_errors'] == 0 and original['upper_ms']['mean'] < 20)
            value['all_upper_bounds_lt_20ms'] = original['threshold_20ms']['below'] == len(sent)
            value['sample_std_ddof'] = 1
            result[kind] = value
            inputs[kind] = dict(run_id=original['run_id'],
                run_inventory=anchor(run / 'sha256sum_results.txt'),
                receiver_inventory=anchor(receiver / 'sha256sum_results.txt'),
                clock_inventory=anchor(server / 'sha256sum_results.txt'),
                sent_log=anchor(run / 'mqtt_sent.jsonl'), received_log=anchor(receiver / 'received.jsonl'),
                probes=anchor(receiver / 'clock_probes.jsonl'),
                jobs=anchor(run / 'jobs.jsonl'), analysis_inventory=anchor(folder / 'sha256sum_results.txt'))
            inputs[kind]['parent_inventory'] = anchor(run.parent / 'sha256sum_results.txt')
            inputs[kind]['worker_log'] = anchor(run.parent / 'worker.log')
    for name in sorted((session / 'source/edge/server/week9').iterdir()):
        if name.is_file():
            published = IMPLEMENTATION / name.name
            if not published.exists() or sha(published) != sha(name):
                raise ValueError('Published source differs from measured bytes: ' + name.name)
            source_files[published.relative_to(ROOT).as_posix()] = sha(name)
    for name, src in [('oneway.py', session / 'oneway.py'),
                      ('native_receiver.py', session / 'windows/native_receiver.py')]:
        if sha(IMPLEMENTATION / name) != sha(src):
            raise ValueError('Published measurement source differs: ' + name)
        source_files[(IMPLEMENTATION / name).relative_to(ROOT).as_posix()] = sha(src)
    return result, inputs, samples, intervals, source_files


def energy_context(session, device, measurement):
    session = Path(session).resolve()
    device = Path(device).resolve()
    manifest = read(device / 'manifest.json')
    for item in manifest['files']:
        path = inside(device, device / item['path'])
        if path.stat().st_size != item['bytes'] or sha(path) != item['sha256']:
            raise ValueError('Device Week 9 published manifest differs')
    offline = inside(session, (session / 'reference_host.txt').read_text().strip())
    measurement.verify(offline)
    source = ROOT / 'edge/server/week9_energy'
    adapter = load(ROOT / 'edge/server/week8/sv1_log.py', 'week9_log_adapter')
    output = {}
    with tempfile.TemporaryDirectory(prefix='asi_week9_b5_') as tmp:
        for phase, name in [('p1', 'energy_b5'), ('p2', 'energy_b5_lan_2'), ('p4', 'energy_b5_lan_4')]:
            raw = session / ('nhan_b5_' + phase) / 'raw' / name
            measurement.verify(raw)
            rows = measurement.rows(raw / 'peer.jsonl')
            numeric = measurement.rows(raw / 'requests.jsonl')
            if numeric != [adapter.sv1_row(row) for row in rows]:
                raise ValueError('B5 numeric log differs from original peer log')
            info = read(raw / 'run.json')
            if (info['service_sha256'] != sha(source / 'ble_energy.py')
                    or info['phy_sha256'] != sha(source / 'phy.py')):
                raise ValueError('B5 service source mismatch')
            for key, value in read(session / 'expected_backend.json').items():
                if info['backend'].get(key) != value:
                    raise ValueError('B5 backend mismatch')
            comparison = Path(tmp) / phase
            command = [sys.executable, '-B', str(ROOT / 'edge/server/week8/summarize.py'),
                '--reference', str(session / 'inputs/reference_s2.npz'),
                '--offline', str(offline), '--radio', str(raw), '--output', str(comparison)]
            checked = subprocess.run(command, capture_output=True, text=True)
            if checked.returncode:
                raise ValueError('B5 bit comparison failed: ' + checked.stderr)
            compared = read(comparison / 'summary.json')
            if not compared['exact_100_pairs'] or compared['offline_logits_bit_matches'] != 200:
                raise ValueError('B5 pairs or logits differ')
            receipt = device / ('b5_kv260_' + phase + '_edge_summary.json')
            checker = device / ('b5_kv260_' + phase + '_check_kv260.json')
            if not checker.exists():
                checker = device / ('b5_kv260_' + phase + '_check_kv260_FAIL.json')
            imported = read(receipt)
            accepted = read(checker)
            if imported['source_log_sha256'] != sha(raw / 'requests.jsonl'):
                raise ValueError('SV1 imported a different Edge request log')
            events = measurement.rows(raw / 'events.jsonl')
            phy = measurement.rows(raw / 'phy.jsonl')
            first_rx = min(row['t_rx_ms'] for row in rows)
            gates = [e for e in events if e['event'] == 'phy_gate_ok']
            if len(gates) != 1 or gates[0]['t_ms'] > first_rx:
                raise ValueError('B5 PHY gate timing differs')
            if not any(p['tx_phy'] == p['rx_phy'] == '2M' and p['hci_status'] == 0
                       and p['t_ms'] <= gates[0]['t_ms'] for p in phy):
                raise ValueError('B5 active Read PHY not found')
            summary = read(raw / 'summary.json')
            output[phase] = dict(edge=summary, exact_100_pairs=compared['exact_100_pairs'],
                offline_logits_bit_matches=compared['offline_logits_bit_matches'],
                request_log_sha256=sha(raw / 'requests.jsonl'),
                source_commit=info['source_commit'], service_sha256=info['service_sha256'],
                phy_sha256=info['phy_sha256'], backend=info['backend'],
                phy_gate_before_first_request=True, sv1_import_hash_matches=True,
                device_status=accepted['status'], device_checks=accepted['checks'],
                device_receipt=checker.relative_to(ROOT).as_posix(),
                device_receipt_sha256=sha(checker),
                limitation='Published Device checker receipt, not a new independent PPK2 execution')
    return dict(device_manifest_sha256=sha(device / 'manifest.json'),
                device_manifest_files_verified=len(manifest['files']), runs=output)


def figures(output, samples):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    target = output / 'figures'
    target.mkdir()
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.7), layout='constrained')
    for ax, kind in zip(axes, ('idle', 'varying')):
        values = sorted(row['t_one_way_midpoint_ms'] for row in samples if row['kind'] == kind)
        ax.plot(values, [(i + 1) / len(values) for i in range(len(values))], linewidth=1.5)
        ax.axvline(20, color='tab:red', linestyle='--', label='20 ms')
        ax.axhline(.95, color='grey', linestyle=':', label='p95')
        ax.set(xscale='log', xlabel='Application one-way midpoint (ms)', ylabel='Empirical CDF', title=kind)
        ax.grid(alpha=.25)
        ax.legend()
    fig.savefig(target / 'mqtt_latency_cdf.pdf')
    fig.savefig(target / 'mqtt_latency_cdf.png', dpi=200)
    plt.close(fig)


def export(session, output, publication_date, energy_session=None, device=None, make_figures=False):
    session = Path(session).resolve()
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    verify_prepared(session)
    measurement = load(IMPLEMENTATION / 'oneway.py', 'week9_export_measurement')
    analysis = inside(session, (session / 'analysis_hien_tai.txt').read_text().strip())
    measurement.verify(analysis)
    review_zip = verify_review_zip(session, analysis)
    runs, inputs, samples, intervals, sources = calibrated_runs(session, analysis, measurement)
    profile = read(ROOT / 'experiments/configs/sv2_edge_week9.json')
    backend = read(session / 'expected_backend.json')
    reference_sha = profile['reference_npz_sha256']
    parent = session.parent
    if sha(parent / 'inputs/reference_s2.npz') != reference_sha:
        raise ValueError('Reference NPZ checksum mismatch')
    b5 = energy_context(energy_session, device, measurement) if energy_session else None
    try:
        head = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    except subprocess.CalledProcessError:
        head = None
    commit = head
    for relative, digest in dict(sources, **{'edge/export_week9_evidence.py': sha(__file__)}).items():
        stored = subprocess.run(['git', '-C', str(ROOT), 'show', 'HEAD:' + relative], capture_output=True)
        if stored.returncode or hashlib.sha256(stored.stdout).hexdigest() != digest:
            commit = None
            break
    output.mkdir(parents=True)
    save(output / 'summary.json', dict(schema_version=1, publication_date=publication_date,
        scope='SV2 self-operated KV260 -> broker -> Windows GW_TRUNG gateway',
        status='MEAN_LATENCY_LT20_WITHIN_FEASIBLE_CLOCK_MODEL' if all(
            r['mean_upper_bound_lt_20ms'] for r in runs.values()) else 'MEAN_LATENCY_REVIEW_REQUIRED',
        criterion=profile['acceptance'], percentile_method='nearest rank', runs=runs,
        group_acceptance='REVIEW_REQUIRED; no automatic claim of SV1 receipt or every-message <20ms'))
    csv_file(output / 'latency_samples.csv', samples)
    csv_file(output / 'mqtt_intervals.csv', intervals)
    save(output / 'provenance.json', dict(schema_version=1, exporter_sha256=sha(__file__),
        published_source_commit=commit, repository_head_at_export=head, publication_date=publication_date,
        profile_sha256=sha(ROOT / 'experiments/configs/sv2_edge_week9.json'),
        archive=review_zip, analysis_inventory=anchor(analysis / 'sha256sum_results.txt'),
        prepared_inventory=anchor(session / 'sha256sum_prepare.txt'), raw_inputs=inputs,
        reference_npz_sha256=reference_sha, backend=backend,
        verification='SHA inventories, W10 CRC/analysis bytes, full payload/clock/source checks; exact recomputation of saved JSON and per-message bounds',
        raw_storage='Original session and W10 ZIP retained outside Git; request through project artifact handoff'))
    save(output / 'source_versions.json', dict(schema_version=1,
        published_source_commit=commit, measured_files_sha256=sources,
        source_identity='Published measured files are byte-exact; publication commit is later than acquisition',
        helper_sha256=sha(__file__)))
    if b5:
        save(output / 'b5_review.json', b5)
    if make_figures:
        figures(output, samples)
    (output / 'sha256sum_export.txt').write_text(''.join(
        sha(p) + '  ' + p.relative_to(output).as_posix() + '\n'
        for p in sorted(output.rglob('*')) if p.is_file()))
    print('WEEK9_EXPORT_VERIFIED', output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--publication-date', default=datetime.now(timezone(timedelta(hours=7))).date().isoformat())
    parser.add_argument('--energy-session', type=Path)
    parser.add_argument('--device-evidence', type=Path, default=ROOT / 'results/week9/device')
    parser.add_argument('--figures', action='store_true')
    args = parser.parse_args()
    export(args.session, args.output, args.publication_date, args.energy_session,
           args.device_evidence, args.figures)


if __name__ == '__main__':
    main()
