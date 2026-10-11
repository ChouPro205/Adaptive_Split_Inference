"""Raw-byte delivery scope, independent of the author's workspace inventory."""
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
SCOPE = ROOT / 'ml/manifests/week5_delivery_scope_v2.json'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def safe_path(root, name):
    parts = PurePosixPath(name).parts
    need(parts and not name.startswith('/') and '\\' not in name and ':' not in name
         and all(p not in ('', '.', '..') for p in name.split('/')), f'Unsafe path: {name}')
    path = (root / name).resolve()
    need(path.is_relative_to(root.resolve()), f'Path escapes delivery: {name}')
    return path


def inventory(root=ROOT, scope=None):
    scope = read(SCOPE) if scope is None else scope
    need(scope['schema'] == 'week5-portable-delivery/2', 'Wrong scope version')
    names = [r['path'] for r in scope['files']]
    need(len(names) == len(set(names)) and names, 'Empty/duplicate scope')
    result = {}
    for entry in scope['files']:
        path = safe_path(root, entry['path'])
        need(path.is_file(), f'Missing required delivery dependency: {entry["path"]}')
        value = {'sha256': sha(path), 'size_bytes': path.stat().st_size}
        need(value == {k: entry[k] for k in value}, f'Delivery dependency changed: {entry["path"]}')
        result[entry['path']] = value
    return result


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')
