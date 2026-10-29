#!/usr/bin/env python3
"""Prepare a new local Week 8 session with immutable input and a transferable source snapshot."""
import argparse,csv,json,shutil,subprocess,tarfile
from pathlib import Path
from common import ROOT,load_reference,REFERENCE_SHA,file_sha,save

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--reference',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    data=load_reference(a.reference);a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'logs').mkdir();(a.output/'inputs').mkdir();source=a.output/'source';source.mkdir()
    shutil.copyfile(a.reference,a.output/'inputs/reference_s2.npz')
    with (a.output/'inputs/samples_from_npz.csv').open('x',newline='') as f:
        w=csv.writer(f);w.writerow(['sample_index','sample_id','test_index','label_ref_int8'])
        w.writerows((i,str(data['sample_id'][i]),int(data['test_index'][i]),int(data['label_ref'][i])) for i in range(100))
    paths=[ROOT/'edge/server/week8',ROOT/'edge/runtime/persistent',ROOT/'edge/runtime/single_input/tail_io.hpp',
           ROOT/'edge/runtime/check_cpu_libraries.py',ROOT/'contracts/i1v2_ref',ROOT/'contracts/i2_ref',
           ROOT/'contracts/sv3_week5_approved_registry_v2.json']
    for path in paths:
        dest=source/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True)
        if path.is_dir():shutil.copytree(path,dest,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        else:shutil.copyfile(path,dest)
    hashes={p.relative_to(source).as_posix():file_sha(p) for p in sorted(source.rglob('*')) if p.is_file()}
    (source/'sha256sum_source.txt').write_text(''.join(h+'  '+p+'\n' for p,h in hashes.items()))
    save(a.output/'session.json',{'reference_sha256':REFERENCE_SHA,'reference_origin':'user supplied Windows Downloads; independent sender checksum pending',
        'source_commit':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
        'source_files':hashes,'scope':'SV2 week8 G2 preparation, not executed','board':'root@192.168.0.134',
        'true_class_sampling':'requires sender samples.csv; label_ref is offline prediction'})
    with tarfile.open(a.output/'source.tar.gz','w:gz') as tar:tar.add(source,arcname='source')
    print('REFERENCE_VALID_100; SOURCE_SHA256='+file_sha(a.output/'source.tar.gz'))
if __name__=='__main__':main()
