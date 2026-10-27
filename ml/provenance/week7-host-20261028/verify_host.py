"""Verify this delivery's receipts, preserved inputs and documentation links."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from capture_state import inventory, git
sys.path.insert(0, str(ROOT/'ml/scripts'))
from review_week7_sv2 import need, read, sha, write

BASE = '4e027b22b936f628e60aa4215aebb7f0ff66cfc4'
MAIN = '02ad8c83297d5bee9298342b2bd4e4ff406922ac'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory', type=Path, default=HERE)
    p.add_argument('--tested-commit', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    commands = {}
    for name in ('nopeek-normal', 'nopeek-O', 'reconcile-normal', 'reconcile-O',
                 'demo', 'reference', 'package'):
        path = a.directory/(name+'.command.json')
        r = read(path)
        need(r['git_commit'] == a.tested_commit and r['exit_code'] == 0 and
             r['sources_unchanged_during_command'], 'Command pin/status differs: '+name)
        for suffix, digest in r['logs_sha256'].items():
            need(sha(a.directory/(name+'.'+suffix)) == digest, 'Log differs: '+name)
        for source, digest in r['source_sha256'].items():
            need(hashlib.sha256((ROOT/source).read_bytes().replace(b'\r\n',b'\n')).hexdigest() == digest,
                 'Source differs: '+source)
            need(hashlib.sha256(git('show',a.tested_commit+':'+source).replace(b'\r\n',b'\n')).hexdigest() == digest,
                 'Source was not committed at tested revision: '+source)
        if name.startswith(('nopeek-', 'reconcile-')):
            log = (a.directory/(name+'.stderr.txt')).read_text('utf-8')
            expected = 19 if name.startswith('nopeek-') else 18
            need(re.search(rf'Ran {expected} tests in .*\n\nOK\s*$', log), 'Suite count/status differs: '+name)
        commands[name] = {'commit':r['git_commit'], 'receipt_sha256':sha(path), 'exit':r['exit_code']}
    demo = read(a.directory/'demo.json')
    need(demo['weights_unchanged'] and demo['human_learning_or_GVHD_demo']=='NOT_ATTESTED', 'Demo scope differs')
    handoff = read(HERE/'handoff-receipt.json')
    need(sha(ROOT/handoff['archive_path']) == handoff['archive_sha256'], 'Handoff ZIP differs')
    before, after = read(HERE/'preservation-before.json'), inventory()
    need(all(after.get(name)==entry for name,entry in before.items()), 'Existing ignored arrays/model artifacts changed')
    hydration = read(HERE/'hydration.json')
    need(not hydration['target_previously_existed'] and hydration['sha256']==
         '9b8be076356e8d42d1d8cb1a8b42fa33a3997f16a5b797e2541ee79392141f90', 'Hydration identity differs')
    need(set(after)-set(before)=={hydration['target']}, 'Unrecorded ignored artifact additions')
    need(after[hydration['target']]=={'sha256':hydration['sha256'],'size':hydration['size']}, 'Hydrated bytes differ')
    old = []
    for scope in ('ml/provenance/week7-reconcile-20261026','ml/provenance/week7-evaluator-fix-20261026'):
        for name in git('ls-tree','-r','--name-only',BASE,scope).decode().splitlines():
            need((ROOT/name).read_bytes()==git('show',BASE+':'+name), 'Historical evidence changed: '+name)
            old.append(name)
    for pin in ('08e4b42','0545b47','18e74ab','4e027b2',MAIN):
        subprocess.run(['git','merge-base','--is-ancestor',pin,'HEAD'],cwd=ROOT,check=True)
    need(not git('diff',BASE,'HEAD','--','ml/src','ml/configs','ml/manifests'), 'ML baseline source/config changed')
    need(not git('diff',MAIN,'HEAD','--','contracts','device','edge','results'), 'Owner-owned source differs from synced main')
    docs = ['docs/sv3_ml_week7_report.md','docs/sv3_week7_dependency_checklist.md',
            'docs/sv3_week7_reconciliation_20261026.md','docs/sv3_week7_demo_guide.md',
            'docs/sv3_week7_host_update_20261028.md','docs/sv3_week7_sv2_handoff_20261028.md',
            'ml/provenance/week7-host-20261028/README.md']
    checked = []
    for name in docs:
        path = ROOT/name
        text = path.read_text('utf-8')
        if name in docs[:4]:
            need(path.read_bytes().startswith(git('show',BASE+':'+name)), 'Historical document body was rewritten: '+name)
        for link in re.findall(r'\[[^\]]*\]\(([^)\n]+)\)', text):
            if link.startswith(('https:','http:','mailto:')):
                continue
            target, _, anchor = unquote(link).partition('#')
            dest = (path.parent/target).resolve() if target else path
            # The report being created is checked by successful exclusive write below.
            need(dest.exists() or dest==a.output.resolve(), 'Missing document link: '+name+' -> '+link)
            if anchor and dest.suffix=='.md':
                headings = re.findall(r'^#+\s+(.+)$',dest.read_text('utf-8'),re.M)
                slugs = [re.sub(r'[^\w\- ]','',h.lower()).replace(' ','-') for h in headings]
                need(anchor in slugs, 'Missing anchor: '+name+' -> '+link)
            checked.append(name+' -> '+link)
    for args in (('diff','--check',MAIN+'...HEAD'),('diff','--check'),('diff','--cached','--check')):
        git(*args)
    result = {'status':'PASS_HOST_SCOPE_ONLY', 'checked_head':git('rev-parse','HEAD').decode().strip(),
              'verifier_sha256':sha(Path(__file__)),
              'tested_commit':a.tested_commit, 'commands':commands,
              'historical_evidence_files_raw_unchanged':len(old),
              'ignored_artifact_files_hash_unchanged':len(read(HERE/'preservation-before.json')),
              'documentation_links_checked':len(checked), 'links':checked,
              'four_handoff_commits_preserved':True, 'synced_main_ancestor':MAIN,
              'DPU_acceptance':'INCOMPLETE_NO_ACCEPTANCE', 'human_confirmation':'NOT_ATTESTED'}
    write(a.output,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('commands','links')},indent=2))


if __name__ == '__main__':
    main()
