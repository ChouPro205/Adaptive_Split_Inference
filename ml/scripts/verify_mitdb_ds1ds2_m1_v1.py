"""Independently rebuild M1 windows/statistics from authenticated raw ECG."""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
from pathlib import Path

import numpy as np
import wfdb

from mitdb_ds1ds2_m1_v1 import (ROOT, DS1, DS2, PACED, CLASSES, MAPPING, SCHEMA, SOURCE_PATHS,
    check_raw, digest, need, read_json, validate_config, split_records,
    norm_binding, validate_calibration)


def independent_record(raw, record):
    base = str(raw/record)
    header = wfdb.rdheader(base)
    need(header.fs == 360 and header.sig_name.count('MLII') == 1, 'Raw lead/fs differs')
    channel = header.sig_name.index('MLII')
    # Read both channels, independently of producer's channel-selective loader.
    signal = wfdb.rdrecord(base).p_signal[:,channel]
    ann = wfdb.rdann(base,'atr')
    valid = [(int(p),s) for p,s in zip(ann.sample,ann.symbol)
             if s in MAPPING and 180 <= p <= len(signal)-180]
    peaks = np.asarray([p for p,s in valid])
    x = signal[peaks[:,None]+np.arange(-180,180)[None,:]]
    y = np.asarray([CLASSES.index(MAPPING[s]) for p,s in valid],dtype='<i8')
    pid = 'P201_202' if record in ['201','202'] else 'P'+record
    meta = [dict(zip(SCHEMA,map(str,[pid,record,p,s,MAPPING[s],CLASSES.index(MAPPING[s]),'MLII',channel])))
            for p,s in valid]
    mapped = [sum(s in MAPPING and MAPPING[s]==k for s in ann.symbol) for k in CLASSES]
    audit = {'record_id':record,'patient_id':pid,'signal_names':header.sig_name,'lead_index':channel,
             'fs':header.fs,'signal_samples':header.sig_len,'annotations':len(ann.sample),
             'ignored_annotations':len(ann.sample)-sum(mapped),'mapped_counts':mapped,
             'boundary_dropped_counts':(np.asarray(mapped)-np.bincount(y,minlength=5)).tolist(),
             'accepted_counts':np.bincount(y,minlength=5).tolist()}
    return x,y,meta,audit


def independent_validation(c, data):
    # Independent rank generation and threshold arithmetic (no producer chooser).
    counts = {r:np.bincount(data[r][1],minlength=5) for r in DS1}
    total = np.sum(list(counts.values()),axis=0)
    feasible = [(hashlib.sha256(f"{c['validation']['seed']}:{','.join(combo)}".encode('ascii')).hexdigest(),combo)
                for combo in itertools.combinations(sorted(DS1),5)
                if all(sum(int(counts[r][k]) for r in combo)*10 >= total[k] for k in (1,2))]
    need(bool(feasible),'No independent feasible split')
    key,records = sorted(feasible)[0]
    return list(records),len(feasible),key


def verify(config, raw, output, artifacts):
    c = read_json(config)
    validate_config(c)
    m = read_json(output/'processed-manifest.json')
    need(m['status']==c['status'] and m['review']=='NOT_REVIEWED' and
         m['training_performed'] is False and m['model_predictions_performed'] is False,
         'Unexpected lock/training/prediction claim')
    need(m['config_sha256']==digest(config,True), 'Config binding differs')
    need(m['schema_version']==1 and m['candidate_id']==c['candidate_id'] and
         set(m['sources_sha256'])==set(SOURCE_PATHS) and
         set(m['splits'])=={'train','val','test_main','test_aux22'}, 'Manifest schema/inventory differs')
    for field,name in [('split_sha256','split.csv'),('normalization_sha256','normalization.json'),
                       ('record_audit_sha256','record-audit.json')]:
        need(m[field]==digest(output/name,True),'Binding differs: '+name)
    for name,h in m['sources_sha256'].items():
        need(digest(ROOT/name,True)==h,'Source binding differs: '+name)
    need(check_raw(raw,c)==m['raw_sha256'], 'Raw hash inventory differs')
    with (output/'split.csv').open(encoding='utf-8',newline='') as f:
        rows = list(csv.DictReader(f))
    groups = split_records(rows)
    norm = read_json(output/'normalization.json')
    norm_binding(norm,groups)
    need(norm['config_sha256']==m['config_sha256'] and norm['split_sha256']==m['split_sha256'],
         'Normalization provenance differs')
    validate_calibration(groups['train']+groups['val'],groups)
    data = {r:independent_record(raw,r) for r in DS1}
    val,count,key = independent_validation(c,data)
    need(val==groups['val'] and m['selection']['feasible_combinations']==count and
         m['selection']['chosen_rank_sha256']==key, 'Reproducible validation differs')
    # Independently sum each beat, unlike producer's per-record array reduction.
    total = sum(float(beat.sum(dtype=np.float64)) for r in groups['train'] for beat in data[r][0])
    total_sq = sum(float(np.dot(beat,beat)) for r in groups['train'] for beat in data[r][0])
    n = sum(data[r][0].size for r in groups['train'])
    mean = total/n
    std = float(np.sqrt(total_sq/n-mean**2))
    need(n==norm['num_values'] and n//360==norm['num_train_beats'] and
         abs(mean-norm['mean'])<1e-12 and abs(std-norm['std'])<1e-12,
         'Train-only normalization reconstruction differs')
    data.update({r:independent_record(raw,r) for r in DS2+['202']})
    actual_audit = read_json(output/'record-audit.json')
    need(len(actual_audit)==48 and len({r['record_id'] for r in actual_audit})==48,'Audit inventory differs')
    by_record = {r['record_id']:r for r in actual_audit}
    for r in data:
        need(by_record[r]==data[r][3], 'Raw record audit differs: '+r)
    for r in PACED:
        h = wfdb.rdheader(str(raw/r))
        expected = {'record_id':r,'patient_id':'P'+r,'signal_names':h.sig_name,
                    'lead_index':h.sig_name.index('MLII') if 'MLII' in h.sig_name else None,
                    'fs':h.fs,'excluded_reason':'paced_record'}
        need(by_record[r]==expected, 'Excluded channel audit differs: '+r)
    sets = {s:groups[s] for s in ['train','val','test_main']}
    sets['test_aux22'] = sorted(DS2+['202'])
    expected_files = {s+'_'+ext for s in sets for ext in ['X.npy','y.npy','metadata.csv']}
    need(set(m['artifacts'])==expected_files and {p.name for p in artifacts.iterdir()}==expected_files,
         'Processed artifact inventory differs')
    for name,entry in m['artifacts'].items():
        need(digest(artifacts/name)==entry['sha256'] and (artifacts/name).stat().st_size==entry['bytes'],
             'Processed hash differs: '+name)
    for s, records in sets.items():
        x = np.load(artifacts/(s+'_X.npy'),allow_pickle=False,mmap_mode='r')
        y = np.load(artifacts/(s+'_y.npy'),allow_pickle=False)
        with (artifacts/(s+'_metadata.csv')).open(encoding='utf-8',newline='') as f:
            reader = csv.DictReader(f)
            need(reader.fieldnames==SCHEMA,'Metadata schema differs')
            metadata = list(reader)
        expected_rows = sum(len(data[r][1]) for r in records)
        need(x.shape==(expected_rows,360) and x.dtype==np.dtype('<f4') and
             y.shape==(expected_rows,) and y.dtype==np.dtype('<i8'), 'Array shape/dtype differs: '+s)
        need(len(metadata)==expected_rows,'Metadata row count differs')
        start = 0
        for r in records:
            raw_x, expected_y, expected_meta, _ = data[r]
            end = start+len(expected_y)
            expected_x = ((raw_x-norm['mean'])/norm['std']).astype('<f4')
            need(np.array_equal(x[start:end],expected_x) and np.isfinite(x[start:end]).all(),
                 'Raw-to-normalized window mismatch: '+s+'/'+r)
            need(np.array_equal(y[start:end],expected_y) and metadata[start:end]==expected_meta,
                 'Raw label/identity/lead mismatch: '+s+'/'+r)
            start=end
        summary = m['splits'][s]
        expected_summary = {'records':records,'patients':sorted({row['patient_id'] for row in metadata}),
                            'samples':len(y),'counts':np.bincount(y,minlength=5).tolist()}
        need(summary==expected_summary,'Summary/count differs: '+s)
    print('PASS_M1_CANDIDATE_DATA_VERIFIED_NOT_LOCKED_NOT_REVIEWED')
    print('Raw files: 144; records/channel audit: 48; processed files: 12; no model predictions')
    print('Independent normalization mean/std:',mean,std)
    print('Independent validation:',','.join(val))
    return groups


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ['config','raw-dir','output','artifacts']:
        p.add_argument('--'+arg,type=Path,required=True)
    a=p.parse_args()
    verify(a.config,a.raw_dir,a.output,a.artifacts)


if __name__=='__main__':
    main()
