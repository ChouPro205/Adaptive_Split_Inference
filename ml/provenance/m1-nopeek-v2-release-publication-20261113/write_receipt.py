# Writes the NoPeek v2 checkpoint Release publication receipt once (open 'x') from the saved gh release view, the remote
# tag listing, the anonymous download check, and the checks of the downloaded zip extracted onto a clean tree of the tag
# commit (sha256sum -c and verify_runs.py, normal and -O). Hashes local files only.
# Run from the worktree root: python -B <this file>
import hashlib
import json
from pathlib import Path

R = Path('ml/provenance/m1-nopeek-v2-release-publication-20261113'); L = R/'logs'
PREP = Path('ml/provenance/m1-nopeek-v2-release-20261113')
TAG = 'sv3-m1-nopeek-v2-checkpoints-20261113'
PREPARE_COMMIT = '000289686875fc9623a786620be7b34f6b626789'
ZIP = 'SV3_M1_NOPEEK_V2_CHECKPOINTS_20261112.zip'
EXPECTED = {ZIP: 'df34b13e4ce478353e52cf5bfb907f9f37c1b5884980b86b4f5f153645dae351',
            'PACKAGE_SHA256SUMS.txt': '5b58c9fe160b9dea173254561804fc3e6afc3c9b3408378b2dd494d4a5bb3dde'}
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def need(condition, message):
    if not condition:
        raise SystemExit(f'CHECK FAILED: {message}')


view = json.loads((L/'release-view.json').read_text(encoding='utf-8'))
remote = dict(line.split('\t')[::-1] for line in (L/'tag-ls-remote.txt').read_text(encoding='utf-8').splitlines() if line)
check = (L/'download-check.txt').read_text(encoding='utf-8')
verify_n, verify_o = (L/'downloaded-verify-normal.txt').read_bytes(), (L/'downloaded-verify-optimized.txt').read_bytes()
verify = json.loads(verify_n.decode('utf-8'))

need(view['tagName'] == TAG and not view['isDraft'] and not view['isPrerelease'], 'Release tag or state differs')
need(remote.get(f'refs/tags/{TAG}') == PREPARE_COMMIT, 'Remote tag does not point to the prepare commit')
assets = []
for a in sorted(view['assets'], key=lambda a: a['name']):
    line = next(x for x in check.splitlines() if x.startswith(a['name'] + ' '))
    got = dict(kv.split('=', 1) for kv in line.split()[1:])
    need(got['http'] == '200' and got['matches_local'] == 'true' and got['github_digest_matches'] == 'true'
         and int(got['bytes']) == a['size'] and a['digest'] == 'sha256:' + got['sha256']
         and EXPECTED.get(a['name'], got['sha256']) == got['sha256'], f"Asset check differs: {a['name']}")
    assets.append({'name': a['name'], 'url': a['url'], 'size_bytes': a['size'], 'sha256': got['sha256'], 'github_digest': a['digest'],
                   'anonymous_download_http': 200, 'downloaded_bytes_match_local': True})
need(len(assets) == 3, 'Expected three assets')
need(f'{ZIP}: OK' in check and 'PACKAGE_SHA256SUMS.txt asset equals the copy inside the downloaded zip: OK' in check, 'Zip or sums check did not pass')
need('exit 0, 1948 lines OK, 0 lines not OK' in (L/'downloaded-sha256sum-c.txt').read_text(encoding='utf-8'), 'sha256sum -c of the downloaded tree did not pass')
need(verify_n == verify_o, 'Downloaded verify differs between normal and -O')
need(verify['status'] == 'NOPEEK_V2_RUNS_HASH_CHECK_PASS' and verify.get('package_sums_file_checked') is True
     and verify['package_sums_sha256'] == EXPECTED['PACKAGE_SHA256SUMS.txt'], 'Downloaded verify did not pass')
need(verify_n == (PREP/'logs/extracted-verify-normal.txt').read_bytes(), 'Downloaded verify differs from the pre-release extracted verify')
need(all((L/n).read_bytes() == b'' for n in ('downloaded-verify-normal.stderr.txt', 'downloaded-verify-optimized.stderr.txt')), 'Verify wrote to stderr')

receipt = {
    'schema': 'm1-nopeek-v2-checkpoint-release-publication/1', 'status': 'PUBLISHED_AND_DOWNLOADED_BYTES_VERIFIED',
    'release_url': view['url'], 'release_id': view['databaseId'], 'tag': TAG, 'tag_commit': PREPARE_COMMIT,
    'target_commitish_reported_by_github': view['targetCommitish'], 'title': view['name'], 'published_at': view['publishedAt'],
    'publisher': view['author']['login'], 'draft': view['isDraft'], 'prerelease': view['isPrerelease'],
    'request': 'SV1 2026-11-13, section 4: put all NoPeek v2 checkpoints (81 runs x epochs 0-10) with SHA256SUMS on a Release before the attack runs, as for checkpoint C5',
    'request_evidence': {'path': (PREP/'sv1_evidence/tra_loi_Ky_Anh_NoPeek_v2_goiA_20261113.txt').as_posix(),
                         'sha256': sha(PREP/'sv1_evidence/tra_loi_Ky_Anh_NoPeek_v2_goiA_20261113.txt')},
    'prepare_record': {'path': PREP.as_posix(), 'SHA256SUMS_sha256': sha(PREP/'SHA256SUMS.txt')},
    'notes': {'path': (PREP/'release-notes.md').as_posix(), 'sha256': sha(PREP/'release-notes.md')},
    'assets': assets,
    'downloaded_package_checks': {
        'tree': 'git archive of the tag commit with the downloaded zip extracted at its root',
        'sha256sum_c_PACKAGE_SHA256SUMS': '1948/1948 OK',
        'verify_command': f'python -B [-O] {PREP.as_posix()}/verify_runs.py', 'exit_code': 0,
        'files': verify['files'], 'checkpoints': verify['checkpoints'], 'bytes': verify['bytes'],
        'normal_and_optimized_identical': True, 'equals_pre_release_extracted_verify': True},
    'logs_sha256': {p.as_posix(): sha(p) for p in sorted(L.iterdir())},
    'scope': {'arrays_read': False, 'DS2_opened': False, 'attack_run': False, 'model_quality_evidence': False}}
with (R/'release-publication.json').open('x', encoding='utf-8', newline='\n') as f:
    f.write(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
print('release-publication', sha(R/'release-publication.json'))
