"""Package authenticated data and generated comparisons outside regular Git."""
import argparse
import hashlib
from pathlib import Path
import zipfile

import torch
from week5_common import ROOT, PACKAGE, baseline, load_test, sha, write_json, need


def make_archive(path, files):
    need(not path.exists(), f'Archive already exists: {path}')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file in files:
            archive.write(file, file.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(path) as archive:
        need(archive.testzip() is None, 'ZIP CRC failure')
        for file in files:
            need(hashlib.sha256(archive.read(file.relative_to(ROOT).as_posix())).hexdigest() == sha(file), 'ZIP member differs')
    return {'name': path.name, 'repository_path': path.relative_to(ROOT).as_posix(),
            'size_bytes': path.stat().st_size, 'sha256': sha(path),
            'files': [{'path': f.relative_to(ROOT).as_posix(), 'size_bytes': f.stat().st_size, 'sha256': sha(f)} for f in files]}


def package():
    baseline()
    checkpoint = torch.load(PACKAGE / 'model/checkpoint.pt', map_location='cpu', weights_only=True)
    load_test(checkpoint)
    directory = ROOT / 'ml/artifacts/week5'
    directory.mkdir(parents=True, exist_ok=True)
    data_files = sorted((ROOT / 'ml/data/processed/mitdb').glob('*'))
    need(len(data_files) == 10 and all(f.is_file() for f in data_files), 'Expected the frozen 10 processed artifacts')
    data = make_archive(directory / 'mitdb-frozen-processed-week5-v1.zip', data_files)
    comparison_files = sorted(f for f in (directory / 'quantization20').rglob('*') if f.is_file())
    need(len(comparison_files) == 441, 'Expected 220 INT8, 220 FP16 and one manifest')
    comparison_files += [ROOT / 'ml/results/week5/predictions.csv']
    comparison = make_archive(directory / 'sv3-week5-quantization-reference-v1.zip', comparison_files)
    result = {'status': 'LOCAL_ARCHIVES_VERIFIED_NOT_YET_UPLOADED', 'assets': [data, comparison],
              'version': 'week5-v1', 'storage': 'Existing GitHub Releases repository; upload receipt required for actual URLs',
              'member_hash_policy': 'raw bytes (CSV raw hash may differ from loader LF-normalized hash)'}
    write_json(ROOT / 'ml/provenance/week5/local_archives.json', result)
    print([(a['name'], a['size_bytes'], a['sha256']) for a in result['assets']], flush=True)


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    package()
