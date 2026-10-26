"""Read-only checks of final source/log pins and newly introduced local links."""
from pathlib import Path
import hashlib
import json
import re
import subprocess

ROOT=Path(__file__).resolve().parents[3]
DIRECTORY=Path(__file__).resolve().parent
IMPLEMENTATION='08e4b4259a2757be7b663b88cc1c98607602d266'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    commands=[]
    for p in sorted(DIRECTORY.glob('delivery-*.command.json')):
        data=json.loads(p.read_text('utf-8'))
        if data['git_commit']!=IMPLEMENTATION or data['exit_code']!=0 or not data['sources_unchanged_during_command']:
            raise ValueError('Command pin/status differs: '+p.name)
        for suffix,digest in data['logs_sha256'].items():
            if sha(p.with_name(p.name.replace('command.json',suffix)))!=digest:
                raise ValueError('Log bytes differ: '+p.name)
        for source,digest in data['source_sha256'].items():
            # log_week7_command uses the existing LF-normalized artifact hash policy.
            raw=(ROOT/source).read_bytes().replace(b'\r\n',b'\n')
            if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Source differs: '+source)
        commands.append(p.name)
    if len(commands)!=5:raise ValueError('Incomplete delivery commands')
    checked=[]
    names=['docs/README.md','docs/sv3_ml_week7_report.md','docs/sv3_week7_dependency_checklist.md',
           'docs/sv3_week7_reconciliation_20261026.md','docs/sv3_week7_ml_i1v2_confirmation_draft.md','docs/sv3_week7_demo_guide.md']
    existing=set(subprocess.check_output(['git','ls-tree','-r','--name-only',IMPLEMENTATION],cwd=ROOT,text=True).splitlines())
    for name in names:
        p=ROOT/name
        before=subprocess.check_output(['git','show',IMPLEMENTATION+':'+name],cwd=ROOT).decode() if name in existing else ''
        old=set(re.findall(r'\[[^\]]*\]\(([^)\n]+)\)',before))
        for link in re.findall(r'\[[^\]]*\]\(([^)\n]+)\)',p.read_text('utf-8')):
            if link in old or link.startswith(('http:','https:','#')):continue
            target=link.split('#')[0]
            if not (p.parent/target).exists():raise ValueError('Missing local link: '+name+' -> '+link)
            checked.append(name+' -> '+link)
    audit=json.loads((DIRECTORY/'delivery-audit.json').read_text())
    for name,digest in audit['inputs_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Audit input differs: '+name)
    manifest=json.loads((DIRECTORY/'prepared-reference-manifest.json').read_text())
    if manifest['source_commit']!=IMPLEMENTATION:raise ValueError('Prepared source commit differs')
    for source,digest in manifest['source_sha256'].items():
        if sha(ROOT/source)!=digest:raise ValueError('Prepared source differs: '+source)
    print(json.dumps({'status':'PASS','implementation_commit':IMPLEMENTATION,
                      'delivery_commands':commands,'new_local_links_checked':len(checked),
                      'audit_input_hashes_checked':len(audit['inputs_sha256']),
                      'prepared_source_hashes_checked':len(manifest['source_sha256'])},indent=2))


if __name__=='__main__':main()
