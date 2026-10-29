"""Verify bounded public-prose changes and retain prior evidence pins."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def need(ok, message):
    if not ok:
        raise ValueError(message)


def git(*args):
    return subprocess.check_output(['git', '-c', 'safe.directory=' + ROOT.as_posix(),
                                    '-C', str(ROOT), '--no-optional-locks', *args])


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_text('utf-8'))


def aggregate(paths):
    rows = [(p.relative_to(ROOT).as_posix(), sha(p.read_bytes()))
            for p in sorted(paths, key=lambda p: p.relative_to(ROOT).as_posix())]
    return {'count': len(rows), 'path_and_raw_sha256_digest':
            sha(json.dumps(rows, ensure_ascii=True, separators=(',', ':')).encode())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    need(not args.output.exists(), 'Use a new receipt path')
    allow = read(HERE / 'allowlist.json')
    before = read(HERE / 'preservation-before.json')
    base = allow['base_commit']
    need(before['base_commit'] == base, 'Preservation base differs')
    paths = set(allow['documents'])
    for name in paths:
        original = git('show', base + ':' + name)
        need(sha(original) == allow['documents'][name]['base_sha256'], 'Original document SHA differs')
        edits = sorted([e for e in allow['edits'] if e['path'] == name], key=lambda e: e['start_byte'])
        need(all(edits[i]['start_byte'] + edits[i]['length_bytes'] <= edits[i+1]['start_byte']
                 for i in range(len(edits)-1)), 'Overlapping edits')
        candidate = original
        for e in reversed(edits):
            start, length = e['start_byte'], e['length_bytes']
            old = original[start:start+length]
            normalized = old.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
            need(sha(normalized) == e['before_sha256'] and
                 normalized.endswith(b'\n') == e['original_block_has_final_lf'], 'Original block differs')
            candidate = candidate[:start] + e['after'].encode('utf-8') + candidate[start+length:]
        need((ROOT / name).read_bytes() == candidate and
             sha(candidate) == allow['documents'][name]['candidate_sha256'], 'Non-allowlisted document edit')
    names = git('ls-tree', '-r', '--name-only', base).decode().splitlines()
    kept = [ROOT / name for name in names if name not in paths]
    assets = set()
    for scope in ['ml/data', 'ml/artifacts', '.cache/week7-reconcile']:
        assets.update(p for p in (ROOT / scope).rglob('*') if p.is_file() and
                      p.suffix.lower() in ['.npy', '.npz', '.pt', '.pth', '.onnx', '.zip'])
    groups = {
        'all_preexisting_tracked_except_allowlist': aggregate(kept),
        'ml_source_scripts_configs_manifests': aggregate(p for p in kept if any(
            p.is_relative_to(ROOT / scope) for scope in ['ml/src','ml/scripts','ml/configs','ml/manifests'])),
        'historical_provenance_except_public_readme': aggregate(p for p in kept if p.is_relative_to(ROOT/'ml/provenance')),
        'local_baseline_reference_weights_archives': aggregate(assets),
        'bed2dfc_final_receipts_logs': aggregate(p for p in (ROOT/'.cache/week7-host-final-20261028').rglob('*') if p.is_file())}
    need(groups == before['groups'], 'Protected raw hashes differ')
    prefix = HERE.relative_to(ROOT).as_posix() + '/'
    changed = git('diff', '--name-only', base).decode().splitlines()
    untracked = git('ls-files', '--others', '--exclude-standard').decode().splitlines()
    need(all(n in paths or n.startswith(prefix) for n in changed + untracked), 'Out-of-scope edit')
    need(git('branch', '--show-current').decode().strip() == 'dev/ml-sv3', 'Unexpected branch')
    git('merge-base', '--is-ancestor', base, 'HEAD')
    host = ROOT / '.cache/week7-host-final-20261028'
    host_summary = read(host / 'final-summary.json')
    bindings = set()
    reused = {}
    for name in ['nopeek-normal','nopeek-O','reconcile-normal','reconcile-O','demo','reference','verification']:
        p = host / (name + '.command.json')
        receipt = read(p)
        need(receipt['git_commit'] == 'bed2dfcf86a5d5e323575def5bbbb562f7ee6b51' and
             receipt['exit_code'] == 0 and receipt['sources_unchanged_during_command'], 'Historical receipt status differs')
        need(sha(p.read_bytes()) == host_summary['commands'][name]['receipt_sha256'], 'Historical receipt SHA differs')
        for suffix, h in receipt['logs_sha256'].items():
            need(sha((host / (name+'.'+suffix)).read_bytes()) == h, 'Historical log SHA differs')
        for source, h in receipt['source_sha256'].items():
            need(sha((ROOT/source).read_bytes().replace(b'\r\n',b'\n')) == h and
                 sha(git('show',receipt['git_commit']+':'+source).replace(b'\r\n',b'\n')) == h,
                 'Reused test source differs')
            bindings.add(source)
        if name.startswith(('nopeek-','reconcile-')):
            count = 19 if name.startswith('nopeek-') else 18
            need(re.search(rf'Ran {count} tests in .*\n\nOK\s*$',
                           (host / (name+'.stderr.txt')).read_text('utf-8')), 'Historical test result differs')
        reused[name] = {'tested_commit':receipt['git_commit'], 'receipt_sha256':sha(p.read_bytes()),
                        'execution':'REUSED_NOT_RERUN'}
    fulltest = ROOT / 'ml/provenance/week7-fulltest-20261029'
    evaluation = read(fulltest/'evaluation.json')
    receipt = read(fulltest/'verification.json')
    need(evaluation['input_commit'] == '9b363f023204ead01e43a8103d927dff41182c29' and
         len(evaluation['results']) == 3 and all(r['status']=='PASS_ACCURACY_GATE' and
         r['complete_coverage'] and not r['missing_ids'] and not r['failures'] for r in evaluation['results']),
         'Full-test receipt results differ')
    for name in ['ml/scripts/week7_dpu_accuracy.py','ml/scripts/review_week7_sv2.py','ml/scripts/evaluate_week5_v2.py']:
        need(git('show', evaluation['input_commit']+':'+name) == git('show',base+':'+name) and
             (ROOT/name).read_bytes().replace(b'\r\n',b'\n') == git('show',base+':'+name), 'DPU evaluator source differs')
    need(sha((ROOT/'ml/scripts/week7_dpu_accuracy.py').read_bytes().replace(b'\r\n',b'\n')) == evaluation['evaluator_sha256'],
         'DPU evaluator SHA differs')
    for name, h in receipt['delivered_file_sha256'].items():
        p = ROOT/'.cache/week7-fulltest-received-20261029'/name
        need(sha(p.read_bytes()) == h, 'Received archive/summary SHA differs')
    links = []
    for name in sorted(paths | {prefix+'README.md'}):
        p = ROOT/name
        raw = p.read_bytes()
        need(not raw.startswith(b'\xef\xbb\xbf') and b'\r' not in raw, 'Expected UTF-8/LF')
        for link in re.findall(r'\[[^\]]*\]\(([^)\n]+)\)', raw.decode('utf-8')):
            if link.startswith(('http:','https:','mailto:')):
                continue
            target, _, anchor = unquote(link).partition('#')
            dest = (p.parent/target).resolve() if target else p
            need(dest.exists() and dest.is_relative_to(ROOT), 'Missing/outside link: '+link)
            rel = dest.relative_to(ROOT).as_posix()
            need(git('ls-files','--',rel).strip() or rel.startswith(prefix), 'Untracked link target')
            if anchor and dest.suffix == '.md':
                headings = re.findall(r'^#+\s+(.+)$', dest.read_text('utf-8'),re.M)
                slugs = [re.sub(r'[^\w\- ]','',h.lower()).replace(' ','-') for h in headings]
                need(anchor in slugs,'Missing anchor: '+link)
            links.append(name+' -> '+link)
    for p in HERE.iterdir():
        if p.suffix in ['.py','.json','.md']:
            raw=p.read_bytes();raw.decode('utf-8')
            need(b'\r' not in raw and not raw.startswith(b'\xef\xbb\xbf'),'New artifact encoding differs')
    git('diff','--check',base)
    git('diff','--cached','--check')
    result = {'status':'PASS_NEUTRAL_WORDING_ONLY', 'checked_head':git('rev-parse','HEAD').decode().strip(),
              'base_commit':base, 'binding':'Exact candidate document SHA values; no new technical acceptance or execution.',
              'documents':allow['documents'], 'exact_edits':len(allow['edits']),
              'allowlist_sha256':sha((HERE/'allowlist.json').read_bytes()),
              'verifier_sha256':sha(Path(__file__).read_bytes()),'preservation':groups,
              'links_checked':len(links),'links':links,'reused_host_receipts':reused,
              'unique_host_source_bindings':len(bindings),
              'reused_fulltest':{'evaluated_source_commit':evaluation['input_commit'],
                                'evaluation_sha256':sha((fulltest/'evaluation.json').read_bytes()),
                                'verification_sha256':sha((fulltest/'verification.json').read_bytes()),
                                'execution':'REUSED_NOT_RERUN'},
              'historical_verifiers':'Unchanged; their old document gates certify their original snapshots only.'}
    with args.output.open('x',encoding='utf-8',newline='\n') as f:
        json.dump(result,f,indent=2,ensure_ascii=False);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['documents','links','reused_host_receipts']},indent=2))


if __name__ == '__main__':
    main()
