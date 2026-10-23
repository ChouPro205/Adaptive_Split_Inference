#!/usr/bin/env python3
"""Load-check all required CPU operator libraries without creating a runner."""
import argparse
import ctypes
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def inspect(models, splits, cpu_op_dir, xir):
    needed = {}
    model_hashes = {}
    for split in splits:
        model = models / ('tail_s%d.xmodel' % split)
        model_hashes[str(split)] = hashlib.sha256(model.read_bytes()).hexdigest()
        graph = xir.Graph.deserialize(str(model))
        for subgraph in graph.get_root_subgraph().toposort_child_subgraph():
            if subgraph.has_attr('device') and str(subgraph.get_attr('device')).upper() == 'CPU':
                for op in subgraph.get_ops():
                    needed.setdefault(op.get_type(), set()).add(split)
    rows = []
    for kind, split_ids in sorted(needed.items()):
        name = 'libvart_op_imp_' + kind.translate(str.maketrans({':': '_', '/': '_', '\\': '_'})) + '.so'
        path = cpu_op_dir / name if cpu_op_dir and (cpu_op_dir / name).is_file() else Path(name)
        row = {'op_type': kind, 'splits': sorted(split_ids), 'library': str(path), 'status': 'NOT_CHECKED'}
        try:
            library = ctypes.CDLL(str(path))
            getattr(library, 'vart_init_op_imp')
            row['status'] = 'CPU_LIBRARY_LOAD_PASS'
            if path.is_file():
                row['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        except (OSError, AttributeError) as error:
            row.update(status='MISSING_OR_UNLOADABLE_CPU_LIBRARY', error=str(error))
        rows.append(row)
    return {'created_utc': datetime.now(timezone.utc).isoformat(),
            'scope': 'library load/symbol check only; no graph execution',
            'model_hashes': model_hashes, 'libraries': rows,
            'all_loadable': all(r['status'] == 'CPU_LIBRARY_LOAD_PASS' for r in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--cpu-op-dir', type=Path)
    parser.add_argument('--splits', nargs='+', type=int, choices=range(10), default=list(range(10)))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists: preserve it and choose a new file')
    import xir
    result = inspect(args.models, args.splits, args.cpu_op_dir.resolve() if args.cpu_op_dir else None, xir)
    with args.output.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    for row in result['libraries']:
        print('%s %s splits=%s %s' % (row['status'], row['op_type'], row['splits'], row.get('error', '')))
    print('CPU_LIBRARY_PREFLIGHT=' + ('PASS_NOT_INFERENCE' if result['all_loadable'] else 'BLOCKED'))
    return 0 if result['all_loadable'] else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, ImportError) as error:
        print('CPU_LIBRARY_PREFLIGHT_ERROR: ' + str(error), file=sys.stderr)
        sys.exit(1)
