# Writes the M1 v4 Release receipt once (open 'x') from the saved gh release view and the anonymous
# download check. Hashes local files only. Run from the worktree root.
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path.cwd();D='ml/provenance/m1-v4-release-20261105';L=f'{D}/logs'
LOCK='ml/provenance/m1-v4-checkpoint-lock-20261105/m1_baseline_v4_checkpoint_lock.json'
sha=lambda p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
view=json.loads((ROOT/L/'release-view.json').read_text(encoding='utf-8'))
checks={}
for line in (ROOT/L/'download-check.txt').read_text(encoding='utf-8').splitlines():
    if ' http=' in line:
        name,*fields=line.split(' ');checks[name]=dict(f.split('=',1) for f in fields)
tag=subprocess.check_output(['git','ls-remote','--tags','origin',view['tagName']],text=True).split()[0]
assets=[]
for a in view['assets']:
    c=checks[a['name']];local=f"../{a['name']}"
    assets.append({'name':a['name'],'asset_id':int(a['apiUrl'].rsplit('/',1)[1]),'url':a['url'],'size_bytes':a['size'],
        'sha256':sha(local),'github_digest':a['digest'],'download_http_status':int(c['http']),'download_sha256':c['sha256'],
        'download_matches':c['matches_local']=='true' and c['sha256']==sha(local) and a['digest']=='sha256:'+sha(local)})
r={'schema':'m1-v4-release-publication/1',
   'status':'PUBLISHED_AND_DOWNLOADED_BYTES_VERIFIED' if all(a['download_matches'] and a['download_http_status']==200 for a in assets) else 'MISMATCH',
   'release_url':view['url'],'release_id':view['databaseId'],'tag':view['tagName'],'tag_commit':tag,
   'target_commitish':view['targetCommitish'],'title':view['name'],'published_at':view['publishedAt'],'publisher':view['author']['login'],
   'draft':view['isDraft'],'prerelease':view['isPrerelease'],
   'notes':{'path':f'{D}/release-notes.md','sha256':sha(f'{D}/release-notes.md')},
   'checkpoint_lock':{'path':LOCK,'sha256':sha(LOCK)},
   'request':'SV1 review of M1 v4 grid, section 2d: put the 18 selected checkpoints, grid result and manifest on a GitHub Release',
   'assets':assets,
   'download_check':'Anonymous HTTPS download of each asset URL; bytes compared with the local file and the GitHub asset digest',
   'reconstruction_check':{'commands':f'{L}/reconstruct-commands.txt',
       'outputs_sha256':{p:sha(p) for p in [f'{L}/reconstruct-package-sha256sum-c.txt',f'{L}/reconstruct-verify-normal.txt',f'{L}/reconstruct-verify-optimized.txt']},
       'result':'git archive ea04abf plus the ZIP: PACKAGE_SHA256SUMS 564/564 OK; verify_checkpoint_lock.py exit 0 in normal and -O mode'},
   'scope':{'DS2_opened':False,'arrays_in_assets':False,'intermediate_checkpoints_in_assets':False}}
with (ROOT/D/'release-publication.json').open('x',encoding='utf-8',newline='\n') as f:f.write(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print(r['status'],'receipt',sha(f'{D}/release-publication.json'))
