#!/usr/bin/env python3
"""Export small authenticated SV2 summaries; preserve raw/binaries outside Git."""
import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--week5', type=Path, required=True)
    ap.add_argument('--week6', type=Path, required=True)
    ap.add_argument('--transfer', type=Path, required=True)
    ap.add_argument('--expected-week5-inventory-sha256', required=True)
    ap.add_argument('--expected-week6-archive-sha256', required=True)
    ap.add_argument('--output-root', type=Path, required=True)
    a = ap.parse_args()
    destinations = [a.output_root / ('week%d' % w) / 'edge' for w in (5, 6)]
    if any(p.exists() for p in destinations):
        raise ValueError('Output exists; preserve historical results and select a new output root')
    if sha(a.week5 / 'sha256sum_results.txt') != a.expected_week5_inventory_sha256:
        raise ValueError('Week 5 independent inventory anchor mismatch')
    receipt = json.loads(a.transfer.read_text())
    archive = a.transfer.parent / 'ho_so.tar.gz'
    if receipt['sha256'] != a.expected_week6_archive_sha256 or sha(archive) != receipt['sha256']:
        raise ValueError('Week 6 independent archive anchor mismatch')
    if a.week6.resolve() != (a.transfer.parent / 'ho_so' / receipt['result_relative']).resolve():
        raise ValueError('Week 6 receipt points to a different result')
    for src in (a.week5, a.week6):
        subprocess.run(['sha256sum', '-c', 'sha256sum_results.txt'], cwd=src, check=True,
                       stdout=subprocess.DEVNULL)
    s5 = json.loads((a.week5 / 'summary.json').read_text())
    p6 = json.loads((a.week6 / 'profile_edge.json').read_text())
    if (len(s5) != 10 or sorted(r['split'] for r in s5) != list(range(10)) or
            any(r['execution'] != 'FULL_TAIL_EXECUTED' or r['samples'] != 20 for r in s5)):
        raise ValueError('Week 5 execution incomplete')
    if (not p6['full_10_tail_profiled'] or len(p6['splits']) != 10 or
            sorted(r['split'] for r in p6['splits']) != list(range(10)) or
            any(r['status'] != 'PROFILE_EXECUTED' for r in p6['splits'])):
        raise ValueError('Week 6 profiling incomplete')
    for week, src, dest in zip((5, 6), (a.week5, a.week6), destinations):
        dest.mkdir(parents=True)
        dump(dest / 'source_files.json', {
            'schema_version': 1, 'source_run_id': src.name,
            'processing_version': 1, 'exporter_sha256': sha(Path(__file__)),
            'source_files_sha256': {p.relative_to(src).as_posix(): sha(p)
                                    for p in sorted(src.rglob('*')) if p.is_file()},
            'source_anchor_sha256': a.expected_week5_inventory_sha256 if week == 5 else receipt['sha256'],
            'raw_storage': 'Original local KV260 evidence archive; raw, binaries and models excluded from Git'})
        dump(dest / 'status.json', json.loads((src / 'status.json').read_text()))
        if week == 5:
            dump(dest / 'summary.json', s5)
            run = json.loads((src / 'run.json').read_text())
            dump(dest / 'provenance.json', {k: run[k] for k in
                 ('created_utc', 'machine', 'runner_sha256', 'driver_sha256',
                  'reference_sha256', 'samples_csv_sha256', 'scope')})
        else:
            keys = ['schema_version', 'created_utc', 'scope', 'units', 'load_scope', 'configuration',
                    'week5_status', 'week5_status_sha256', 'bundle_inventory_sha256', 'runner_sha256',
                    'driver_sha256', 'source_hashes', 'environment_before', 'environment_after',
                    'splits', 'full_10_tail_profiled', 'status', 'numeric_acceptance',
                    'independent_test_accuracy', 'dpu_only_timing', 's10']
            portable = {k: p6[k] for k in keys}
            portable['cpu_plugins'] = {k: {'sha256': v['sha256']} for k,v in p6['cpu_plugins'].items()}
            portable['source_profile_sha256'] = sha(src / 'profile_edge.json')
            portable['processing_version'] = 1
            dump(dest / 'profile_edge.json', portable)
            with (dest / 'timing.csv').open('x', newline='') as f:
                fields = ['split_point_s', 'samples_count', 'load_mean_ms', 'first_mean_ms',
                          'execute_wait_mean_ms', 'tail_mean_ms', 'tail_std_ms', 'tail_p95_ms']
                w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
                for r in p6['splits']:
                    t = r['steady']['tail_total_ms']
                    w.writerow(dict(split_point_s=r['split'], samples_count=t['n'],
                       load_mean_ms=r['loading']['model_load_ms']['mean_ms'],
                       first_mean_ms=r['first_inference']['tail_total_ms']['mean_ms'],
                       execute_wait_mean_ms=r['steady']['execute_wait_ms']['mean_ms'],
                       tail_mean_ms=t['mean_ms'], tail_std_ms=t['std_ms'], tail_p95_ms=t['p95_ms']))
        files = sorted(p for p in dest.iterdir() if p.is_file())
        (dest / 'sha256sum_export.txt').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in files))
        print('EXPORTED', dest)


if __name__ == '__main__':
    main()
