"""Package the existing frozen reference for SV2; never regenerate model inputs."""
from __future__ import annotations
import argparse
from pathlib import Path
import zipfile

from review_week7_sv2 import ROOT, need, sha, write
from week7_dpu_accuracy import validate_reference

ANCHOR = '612e5c3c29bf4d68f3ae4cdc3c9cd98481528f85dda0807b4e355150e5848c1c'


def package(reference, output):
    need(not output.exists(), 'Refuse to overwrite handoff directory')
    need(sha(reference/'manifest.json') == ANCHOR, 'Frozen manifest anchor differs')
    manifest = validate_reference(reference)
    template = ROOT/'ml/provenance/week7-reconcile-20261026/dpu-output.template.json'
    members = {name: reference/name for name in ['manifest.json', *manifest['files']]}
    members['dpu-output.template.json'] = template
    before = {name: sha(path) for name, path in members.items()}
    output.mkdir(parents=True)
    archive = output/'sv3-week7-frozen-reference.zip'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_STORED) as z:
        for name, path in members.items():
            z.write(path, name)
    with zipfile.ZipFile(archive) as z:
        import hashlib
        need(set(z.namelist()) == set(members), 'Archive inventory differs')
        for name, digest in before.items():
            with z.open(name) as stream:
                need(hashlib.file_digest(stream, 'sha256').hexdigest() == digest,
                     'Archive member differs: '+name)
    need(before == {name: sha(path) for name, path in members.items()}, 'Source changed during packaging')
    import subprocess
    receipt = {'status': 'READY_FOR_TRANSFER_NOT_SENT',
               'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'reference_generation_commit': manifest['source_commit'],
               'reference_manifest_sha256': ANCHOR, 'reference_regenerated': False,
               'archive_path': str(archive.relative_to(ROOT)), 'archive_sha256': sha(archive),
               'archive_size_bytes': archive.stat().st_size, 'members_sha256': before,
               'archive_members_verified': True, 'source_members_unchanged': True,
               'expected_samples_per_split': 8544, 'splits': manifest['split_points'],
               'output_rows_expected': 25632, 'DPU_acceptance': 'INCOMPLETE_NO_ACCEPTANCE'}
    write(output/'handoff-receipt.json', receipt)
    print(receipt)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, default=ROOT/'.cache/week7-reconcile/accuracy-8544-delivery')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    package(args.reference, args.output)
