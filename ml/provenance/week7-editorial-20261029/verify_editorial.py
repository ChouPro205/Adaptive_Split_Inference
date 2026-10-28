"""Check an exact editorial allowlist without changing historical evidence gates."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = 'bed2dfcf86a5d5e323575def5bbbb562f7ee6b51'
FINAL = ROOT / '.cache/week7-host-final-20261028'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_new(path, data):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def aggregate(paths):
    paths = sorted(paths)
    rows = [(p.relative_to(ROOT).as_posix(), sha(p.read_bytes())) for p in paths]
    return {'count': len(rows), 'path_and_raw_sha256_digest': sha(
        json.dumps(rows, ensure_ascii=True, separators=(',', ':')).encode())}


def preservation(changed):
    names = git('ls-tree', '-r', '--name-only', BASE).decode().splitlines()
    kept = [ROOT / n for n in names if n not in changed]
    artifacts = set()
    for scope in ('ml/data', 'ml/artifacts', '.cache/week7-reconcile'):
        artifacts.update(p for p in (ROOT / scope).rglob('*') if p.is_file() and
                         p.suffix.lower() in ('.npy', '.npz', '.pt', '.pth', '.onnx', '.zip'))
    return {'all_reviewed_tracked_except_allowlist': aggregate(kept),
            'ml_source_scripts_configs_manifests': aggregate(
                p for p in kept if any(p.is_relative_to(ROOT / s) for s in
                ('ml/src', 'ml/scripts', 'ml/configs', 'ml/manifests'))),
            'historical_tracked_provenance_except_readme': aggregate(
                p for p in kept if p.is_relative_to(ROOT / 'ml/provenance')),
            'local_baseline_reference_weights_archives': aggregate(artifacts),
            'bed2dfc_final_local_receipts_and_logs': aggregate(
                p for p in FINAL.rglob('*') if p.is_file())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-before', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    allow = read(HERE / 'allowlist.json')
    need(allow['reviewed_head'] == BASE and len(allow['edits']) == 11, 'Allowlist revision/count')
    paths = {e['path'] for e in allow['edits']}
    need(len(paths) == 8, 'Expected exactly eight edited documents')
    if args.capture_before:
        need(git('rev-parse', 'HEAD').decode().strip() == BASE, 'Capture requires reviewed HEAD')
        need(not git('diff', BASE, '--', *paths), 'Capture must precede prose edits')
        write_new(args.output, {'reviewed_head': BASE, 'preservation': preservation(paths)})
        print('CAPTURED_RAW_PRESERVATION')
        return
    expected = {}
    for path in paths:
        raw = git('show', BASE + ':' + path)
        lines = raw.decode('utf-8').splitlines(keepends=True)
        for e in [e for e in allow['edits'] if e['path'] == path]:
            need(lines[e['line'] - 1] == e['before'] + '\n', 'Original line differs: ' + path)
            lines[e['line'] - 1] = e['after'] + '\n'
        current = (ROOT / path).read_bytes()
        need(current == ''.join(lines).encode('utf-8'), 'Non-allowlisted edit: ' + path)
        need(b'\r' not in current and not current.startswith(b'\xef\xbb\xbf'), 'Expected UTF-8/LF')
        expected[path] = sha(current)
    prefix = HERE.relative_to(ROOT).as_posix() + '/'
    changed = git('diff', '--name-only', BASE).decode().splitlines()
    need(set(changed) - paths <= {n for n in changed if n.startswith(prefix)}, 'Other tracked changes')
    additions = git('ls-files', '--others', '--exclude-standard').decode().splitlines()
    need(all(n.startswith(prefix) for n in additions), 'Unexpected untracked additions')
    before = read(HERE / 'preservation-before.json')
    current = preservation(paths)
    need(before['reviewed_head'] == BASE and before['preservation'] == current, 'Raw preservation differs')
    receipts = {}
    summary = read(FINAL / 'final-summary.json')
    for name in ('nopeek-normal', 'nopeek-O', 'reconcile-normal', 'reconcile-O', 'demo', 'reference', 'verification'):
        path = FINAL / (name + '.command.json')
        record = read(path)
        need(record['git_commit'] == BASE and record['exit_code'] == 0 and
             record['sources_unchanged_during_command'], 'Historical receipt pin/status')
        need(sha(path.read_bytes()) == summary['commands'][name]['receipt_sha256'], 'Receipt SHA differs')
        for suffix, digest in record['logs_sha256'].items():
            need(sha((FINAL / (name + '.' + suffix)).read_bytes()) == digest, 'Log SHA differs')
        for source, digest in record['source_sha256'].items():
            need(sha((ROOT / source).read_bytes().replace(b'\r\n', b'\n')) == digest, 'Current source binding differs')
            need(sha(git('show', BASE + ':' + source).replace(b'\r\n', b'\n')) == digest, 'Tested source binding differs')
        if name.startswith(('nopeek-', 'reconcile-')):
            count = 19 if name.startswith('nopeek-') else 18
            need(re.search(rf'Ran {count} tests in .*\n\nOK\s*$',
                           (FINAL / (name + '.stderr.txt')).read_text('utf-8')), 'Historical test result differs')
        receipts[name] = {'tested_commit': BASE, 'receipt_sha256': sha(path.read_bytes()),
                          'source_files_bound': len(record['source_sha256']), 'execution': 'REUSED_NOT_RERUN'}
    checked = []
    for name in sorted(paths | {p.relative_to(ROOT).as_posix() for p in HERE.glob('*.md')}):
        path = ROOT / name
        raw = path.read_bytes()
        text = raw.decode('utf-8')
        need(b'\r' not in raw and not raw.startswith(b'\xef\xbb\xbf'), 'Document encoding differs')
        for link in re.findall(r'\[[^\]]*\]\(([^)\n]+)\)', text):
            if link.startswith(('https:', 'http:', 'mailto:')):
                continue
            target, _, anchor = unquote(link).partition('#')
            dest = (path.parent / target).resolve() if target else path
            need(dest.exists() or dest == args.output.resolve(), 'Missing link: ' + name + ' -> ' + link)
            rel = dest.relative_to(ROOT).as_posix()
            need(bool(git('ls-files', '--', rel).strip()) or dest.is_relative_to(HERE), 'Link target untracked')
            if anchor and dest.suffix == '.md':
                headings = re.findall(r'^#+\s+(.+)$', dest.read_text('utf-8'), re.M)
                slugs = [re.sub(r'[^\w\- ]', '', h.lower()).replace(' ', '-') for h in headings]
                need(anchor in slugs, 'Missing anchor: ' + name + ' -> ' + link)
            checked.append(name + ' -> ' + link)
    for path in HERE.iterdir():
        if path.suffix in ('.py', '.json', '.md'):
            raw = path.read_bytes()
            raw.decode('utf-8')
            need(b'\r' not in raw and not raw.startswith(b'\xef\xbb\xbf'), 'New artifact encoding differs')
    for arguments in (('diff', '--check', BASE), ('diff', '--cached', '--check'),
                      ('diff', '--check', 'origin/main...HEAD')):
        git(*arguments)
    result = {'status': 'PASS_EDITORIAL_ONLY', 'checked_utc': datetime.now(timezone.utc).isoformat(),
              'checked_head': git('rev-parse', 'HEAD').decode().strip(),
              'binding': 'Exact document SHA values below bind this working-tree editorial candidate; no new ML execution.',
              'reviewed_head': BASE, 'allowlisted_lines': 11, 'edited_document_sha256': expected,
              'verifier_sha256': sha(Path(__file__).read_bytes()),
              'allowlist_sha256': sha((HERE / 'allowlist.json').read_bytes()),
              'preservation': current, 'reused_receipts': receipts,
              'documentation_links_checked': len(checked), 'links': checked,
              'historical_gate': 'verify_host.py and old receipts unchanged; certify their original snapshots only. Its BASE4e027b2 prefix gate is not relabeled as PASS for this editorial revision.',
              'DPU_acceptance': 'INCOMPLETE_NO_ACCEPTANCE', 'personal_confirmation': 'NOT_ATTESTED'}
    write_new(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in
                      ('links', 'reused_receipts', 'edited_document_sha256')}, indent=2))


if __name__ == '__main__':
    main()
