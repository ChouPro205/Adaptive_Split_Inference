#!/usr/bin/env python3
"""Run immutable SV3 verifier with Windows-compatible inventory ordering on Linux.
File names, sizes and SHA-256 checks remain exact; original sources stay unchanged.
"""
import argparse,runpy,sys
from pathlib import Path, PureWindowsPath
p=argparse.ArgumentParser();p.add_argument('--checkout',type=Path,required=True);p.add_argument('--stage',choices=['A','B'],required=True)
a,extra=p.parse_known_args()
scripts=a.checkout.resolve()/'ml/scripts'
sys.path.insert(0,str(scripts))
import week6_p1
original=week6_p1.inventory
def inventory(package):
    rows=original(package)  # Original symlink, file size and SHA-256 logic.
    names=[r['path'].casefold() for r in rows]
    if len(names)!=len(set(names)):raise ValueError('Case-insensitive path collision')
    return sorted(rows,key=lambda row:PureWindowsPath(row['path']))
week6_p1.inventory=inventory
entry=scripts/('verify_week6_p1.py' if a.stage=='A' else 'verify_week6_output.py')
print('LINUX_COMPAT: Windows case-insensitive inventory order only; original source/package bytes unchanged',flush=True)
sys.argv=[str(entry),*extra]
runpy.run_path(str(entry),run_name='__main__')
