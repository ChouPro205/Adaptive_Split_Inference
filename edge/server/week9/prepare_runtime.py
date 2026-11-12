"""Prepare an isolated Week 9 runtime bundle; no network or model execution."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import zipfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(repo, output, reference, profile=None):
    repo = Path(repo).resolve()
    output = Path(output).resolve()
    reference = Path(reference).resolve()
    profile_path = Path(profile) if profile else repo / 'experiments/configs/sv2_edge_week9.json'
    config = json.loads(profile_path.read_text())
    if sha(reference) != config['reference_npz_sha256']:
        raise ValueError('Reference checksum differs; recover the verified integration package')
    if output.exists():
        raise FileExistsError(output)
    if config['mqtt']['clock_host_port'] != 1906:
        raise ValueError('The pinned native receiver preflight uses clock port 1906')
    output.mkdir(parents=True)
    for name in ('logs', 'runs', 'clock_runs', 'inputs', 'windows'):
        (output / name).mkdir()
    for relative in ('contracts', 'edge/server/week8', 'edge/server/week9'):
        shutil.copytree(repo / relative, output / 'source' / relative,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copyfile(reference, output / 'inputs/reference_s2.npz')
    templates = repo / 'experiments/configs/sv2_edge_week9'
    shutil.copyfile(templates / 'expected_backend.json', output / 'expected_backend.json')
    shutil.copyfile(templates / 'broker.conf', output / 'broker.conf')
    for kind in ('idle', 'varying'):
        shutil.copyfile(templates / ('scenario_' + kind + '.csv'),
                        output / ('scenario_' + kind + '.csv'))
        runtime = dict(schema_version=1, scenario_csv='scenario_' + kind + '.csv',
                       reference_npz='inputs/reference_s2.npz',
                       seed=config['queue']['seed'],
                       max_background=config['queue']['max_pending_background_jobs'],
                       mqtt_enabled=True, broker_host='127.0.0.1',
                       broker_port=config['mqtt']['broker_board_port'],
                       receiver_id=config['receiver']['id'],
                       rate_origin='Versioned experimental scenario, not an acceptance threshold')
        (output / ('config_' + kind + '.json')).write_text(
            json.dumps(runtime, indent=2) + '\n')
    implementation = repo / 'edge/server/week9'
    shutil.copyfile(implementation / 'oneway.py', output / 'oneway.py')
    for name in ('oneway.py', 'native_receiver.py', 'README.md'):
        shutil.copyfile(implementation / name, output / 'windows' / name)
    native = dict(receiver_id=config['receiver']['id'], role=config['receiver']['role'],
                  network_label=config['receiver']['network_label'],
                  broker_local_port=config['mqtt']['broker_host_port'],
                  clock_local_port=config['mqtt']['clock_host_port'])
    (output / 'windows/windows_config.json').write_text(json.dumps(native, indent=2) + '\n')
    windows = output / 'windows'
    (windows / 'sha256sum_windows.txt').write_text(''.join(
        sha(p) + '  ' + p.name + '\n' for p in sorted(windows.iterdir())))
    source_hashes = {p.relative_to(output / 'source').as_posix(): sha(p)
                     for p in sorted((output / 'source').rglob('*')) if p.is_file()}
    receipt = dict(status='PREPARED_NOT_EXECUTED', source_sha256=source_hashes,
                   reference_npz_sha256=sha(reference), profile_sha256=sha(profile_path),
                   scope='Preparation only; no radio, model execution, key or group acceptance')
    (output / 'preparation.json').write_text(json.dumps(receipt, indent=2) + '\n')
    (output / 'sha256sum_prepare.txt').write_text(''.join(
        sha(p) + '  ' + p.relative_to(output).as_posix() + '\n'
        for p in sorted(output.rglob('*')) if p.is_file()))
    archive = output / 'deploy_week9.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        for path in sorted(output.iterdir()):
            if path.name != archive.name:
                tar.add(path, arcname=path.name)
    (output / (archive.name + '.sha256.txt')).write_text(sha(archive) + '  ' + archive.name + '\n')
    archive = output / 'windows_receiver.zip'
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(windows.iterdir()):
            z.write(path, path.name)
    (output / (archive.name + '.sha256.txt')).write_text(sha(archive) + '  ' + archive.name + '\n')
    print('WEEK9_PREPARED_NOT_EXECUTED', output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--profile', type=Path)
    args = parser.parse_args()
    prepare(args.repo, args.output, args.reference, args.profile)


if __name__ == '__main__':
    main()
