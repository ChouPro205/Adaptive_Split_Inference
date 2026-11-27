# Writes the package A Release publication receipt once (open 'x') from the saved gh release view, the anonymous
# download check and the verify of the package extracted from the downloaded zip. Hashes local files only.
# Run from the worktree root: python -B <this file>
import hashlib
import json
from pathlib import Path

R = Path('ml/provenance/m1-v4-package-a-release-20261112'); L = R/'logs'
DELIVERY = Path('ml/provenance/m1-v4-package-a-delivery-20261112/delivery.json')
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
view = json.loads((L/'release-view.json').read_text(encoding='utf-8'))
check = (L/'download-check.txt').read_text(encoding='utf-8')
verify = json.loads((L/'downloaded-verify-normal.txt').read_text(encoding='utf-8'))
delivery = json.loads(DELIVERY.read_text(encoding='utf-8'))
expected = {'SV3_M1_V4_PACKAGE_A_20261105.zip': delivery['archive']['sha256']}
assets = []
for a in view['assets']:
    line = next(x for x in check.splitlines() if x.startswith(a['name'] + ' '))
    downloaded = dict(kv.split('=', 1) for kv in line.split()[1:])
    if not (downloaded['http'] == '200' and downloaded['matches_local'] == 'true' and a['digest'] == 'sha256:' + downloaded['sha256']
            and int(downloaded['bytes']) == a['size'] and expected.get(a['name'], downloaded['sha256']) == downloaded['sha256']):
        raise SystemExit(f"Asset check differs: {a['name']}")
    assets.append({'name': a['name'], 'url': a['url'], 'size_bytes': a['size'], 'sha256': downloaded['sha256'],
                   'github_digest': a['digest'], 'anonymous_download_http': 200, 'downloaded_bytes_match_local': True})
if 'SV3_M1_V4_PACKAGE_A_20261105.zip: OK' not in check:
    raise SystemExit('sha256sum -c of the downloaded zip did not pass')
if verify['manifest_sha256'] != delivery['package']['manifest_sha256'] or (L/'downloaded-verify-normal.txt').read_bytes() != (L/'downloaded-verify-optimized.txt').read_bytes():
    raise SystemExit('Verify of the downloaded package differs')
receipt = {
    'schema': 'm1-v4-package-a-release-publication/1', 'status': 'PUBLISHED_AND_DOWNLOADED_BYTES_VERIFIED',
    'release_url': view['url'], 'release_id': view['databaseId'], 'tag': view['tagName'], 'target_commitish': view['targetCommitish'],
    'title': view['name'], 'published_at': view['publishedAt'], 'publisher': view['author']['login'],
    'draft': view['isDraft'], 'prerelease': view['isPrerelease'],
    'request': 'SV1 2026-11-12: deliver package A to SV2 with SV1 in cc after SV2 confirmed the calibration; SV3 chose a GitHub Release',
    'delivery_record': {'path': DELIVERY.as_posix(), 'sha256': sha(DELIVERY)},
    'notes': {'path': (R/'release-notes.md').as_posix(), 'sha256': sha(R/'release-notes.md')},
    'assets': assets,
    'downloaded_package_verify': {'command': 'python -B [-O] ml/scripts/package_m1_v4_a.py verify --package <extracted top folder>',
                                  'manifest_sha256': verify['manifest_sha256'], 'files': verify['files'], 'exit_code': 0,
                                  'normal_and_optimized_identical': True,
                                  'status_note': 'The CANDIDATE_PENDING status string comes from the package manifest written on 2026-11-05; the delivery record resolves it'},
    'logs_sha256': {p.as_posix(): sha(p) for p in sorted(L.iterdir())},
    'scope': {'DS2_opened': False}}
with (R/'release-publication.json').open('x', encoding='utf-8', newline='\n') as f:
    f.write(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
print('release-publication', sha(R/'release-publication.json'))
