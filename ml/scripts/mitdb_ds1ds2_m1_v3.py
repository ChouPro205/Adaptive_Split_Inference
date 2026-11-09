"""Versioned M1 candidate data pipeline. No training, predictions or publication."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import subprocess

import numpy as np
import wfdb
from m1_validation_policy_v3 import enumerate_combinations, choose, write_table
from m1_metrics_v3 import freeze_validation_policy

ROOT = Path(__file__).resolve().parents[2]
DS1 = '101 106 108 109 112 114 115 116 118 119 122 124 201 203 205 207 208 209 215 220 223 230'.split()
DS2 = '100 103 105 111 113 117 121 123 200 210 212 213 214 219 221 222 228 231 232 233 234'.split()
PACED = ['102', '104', '107', '217']
CLASSES = ['N', 'S', 'V', 'F', 'Q']
MAPPING = dict(zip(['N','L','R','e','j','A','a','J','S','V','E','F','/','f','Q'],
                   ['N']*5 + ['S']*4 + ['V']*2 + ['F'] + ['Q']*3))
SCHEMA = ['patient_id','record_id','r_peak_sample','original_symbol','aami_class','class_index','lead_name','lead_index']
SOURCE_PATHS = ['ml/scripts/mitdb_ds1ds2_m1_v3.py','ml/scripts/verify_mitdb_ds1ds2_m1_v3.py',
                'ml/scripts/test_mitdb_ds1ds2_m1_v3.py',
                'ml/scripts/m1_validation_policy_v3.py','ml/scripts/m1_metrics_v3.py',
                'ml/src/mitdb_common.py','ml/src/mitdb_baseline_model.py','ml/configs/mitdb_week1_config.json',
                'ml/configs/week3_model_freeze.json','contracts/sv3_week5_approved_registry_v2.json']


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path, text=False):
    data = Path(path).read_bytes()
    if text:
        data = data.decode('utf-8').replace('\r\n','\n').replace('\r','\n').encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def write_csv(path, rows, fields):
    with Path(path).open('x', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def patient(record):
    return 'P201_202' if record in ('201', '202') else 'P'+record


def validate_config(c):
    need(c['schema_version']==3 and c['candidate_id']=='mitdb-ds1ds2-m1-v3' and
         c['dataset_version']=='1.0.0' and c['physionet_checksum_manifest_sha256']==
         'b61158a96d5f2ca80edfb354a9a66a6324836c390a84e1966dcee2b907d6be43', 'Dataset/checksum pin differs')
    need(c['ds1'] == DS1 and c['ds2_main'] == DS2 and c['auxiliary_only'] == ['202']
         and c['excluded_paced'] == PACED, 'Canonical record inventory differs')
    need(c['shared_patient_groups'] == [['201','202']], 'Patient identity grouping differs')
    need(c['classes'] == CLASSES and c['aami_mapping'] == MAPPING, 'Class mapping differs')
    need(c['lead'] == 'MLII' and c['sampling_rate_hz'] == 360 and c['window'] ==
         {'size':360,'left':180,'right':180,'boundary_policy':'drop'} and
         c['filtering'] is False and c['rr_features'] is False, 'Input/preprocessing contract differs')
    v=c['validation']
    need(v['preferred_records']==4 and v['fallback_records']==5 and type(v['seed']) is int and v['seed']>=0 and
         v['policy']=='F_floor' and v['random_domain']=='m1-validation-v2' and
         v['F_preferred_floor']==20 and v['F_fallback_floor']==10 and v['minimum_four_record_combinations']==50 and
         v['status']=='RULE_CONFIRMED_ARTIFACT_NOT_REVIEWED', 'Validation policy differs')
    need(c['metric_policy']['prediction_space']==CLASSES and c['metric_policy']['zero_division']==0 and
         c['metric_policy']['ds2_metrics']==['macro_f1_NSVF_fixed4','macro_f1_NSVFQ_fixed5'], 'Metric policy differs')
    need(c['normalization'] == {'method':'global_z_score','fit_split':'train',
         'population_variance':True,'accumulator_dtype':'float64','output_dtype':'float32'}, 'Normalization policy differs')
    need(c['status'] == 'CANDIDATE_NOT_LOCKED_NOT_REVIEWED', 'Unreviewed candidate cannot claim lock')
    need(c['approval']['m1_lock']=='NOT_LOCKED' and c['approval']['artifact_review']=='NOT_REVIEWED' and
         c['approval']['training_permission'] is False, 'Candidate approval claim differs')


def check_raw(raw, c):
    raw = Path(raw)
    sums = raw/'SHA256SUMS.txt'
    need(digest(sums) == c['physionet_checksum_manifest_sha256'], 'Official checksum manifest differs')
    expected = sorted(DS1+DS2+['202']+PACED)
    need(sorted(p.stem for p in raw.glob('*.hea')) == expected, 'Raw header inventory differs')
    official = {line.split()[1].lstrip('*'):line.split()[0] for line in sums.read_text().splitlines() if line.strip()}
    hashes = {}
    for r in expected:
        for ext in ['hea','atr','dat']:
            name = r+'.'+ext
            hashes[name] = digest(raw/name)
            need(hashes[name] == official.get(name), 'Raw checksum mismatch: '+name)
    return hashes


def load_record(raw, r):
    base = str(Path(raw)/r)
    h = wfdb.rdheader(base)
    need(h.fs == 360 and 'MLII' in h.sig_name, 'Missing MLII or wrong sampling rate: '+r)
    lead = h.sig_name.index('MLII')
    signal = wfdb.rdrecord(base, channels=[lead]).p_signal[:,0]
    a = wfdb.rdann(base, 'atr')
    beats, labels, rows = [], [], []
    counts, mapped, dropped = [0]*5, [0]*5, [0]*5
    for peak, symbol in zip(a.sample, a.symbol):
        if symbol not in MAPPING:
            continue
        k = CLASSES.index(MAPPING[symbol])
        mapped[k] += 1
        start, end = int(peak)-180, int(peak)+180
        if start < 0 or end > len(signal):
            dropped[k] += 1
            continue
        beat = signal[start:end]
        need(np.isfinite(beat).all(), 'Non-finite raw signal: '+r)
        beats.append(beat)
        labels.append(k)
        counts[k] += 1
        rows.append(dict(zip(SCHEMA, [patient(r),r,int(peak),symbol,CLASSES[k],k,'MLII',lead])))
    x = np.asarray(beats, dtype=np.float64)
    need(x.ndim == 2 and x.shape[1] == 360 and len(x)>0, 'Empty/invalid record '+r)
    audit = {'record_id':r,'patient_id':patient(r),'signal_names':h.sig_name,'lead_index':lead,
             'fs':h.fs,'signal_samples':h.sig_len,'annotations':len(a.sample),
             'ignored_annotations':len(a.sample)-sum(mapped),'mapped_counts':mapped,
             'boundary_dropped_counts':dropped,'accepted_counts':counts}
    return x, np.asarray(labels,dtype='<i8'), rows, audit


def choose_validation(c, counts):
    rows,summary=enumerate_combinations(counts,DS1)
    selected,draw=choose(rows,c['validation']['policy'],c['validation']['seed'])
    return selected,{'draw':draw,'enumeration':summary},rows


def split_records(rows):
    need(len(rows)==48 and len({r['record_id'] for r in rows})==48, 'Duplicate/missing manifest records')
    need({r['record_id'] for r in rows} == set(DS1+DS2+['202']+PACED), 'Manifest record inventory differs')
    groups = {s:[] for s in ['train','val','test_main','auxiliary_only','excluded']}
    for row in rows:
        r, s = row['record_id'], row['split']
        need(row['patient_id'] == patient(r), 'Canonical patient identity mismatch: '+r)
        need(s in groups, 'Unknown split')
        groups[s].append(r)
    need(set(groups['train']+groups['val'])==set(DS1) and len(groups['val']) in (4,5),
         'DS1 train/validation inventory differs')
    need(groups['test_main']==DS2 and groups['auxiliary_only']==['202'] and groups['excluded']==PACED,
         'DS2/202/paced assignment differs')
    patient_sets = {s:{patient(r) for r in groups[s]} for s in ['train','val','test_main']}
    for a,b in itertools.combinations(patient_sets,2):
        need(not patient_sets[a]&patient_sets[b], 'Patient overlap: '+a+'/'+b)
    return groups


def validate_calibration(records, groups):
    need(set(records) <= set(groups['train']) and '202' not in records,
         'Forbidden calibration record')


def norm_binding(norm, groups):
    need(norm['fit_split']=='train' and norm['fit_records']==groups['train'], 'Normalization fit records differ')
    need(norm['fit_patient_ids']==[patient(r) for r in groups['train']], 'Normalization fit patients differ')
    need(np.isfinite([norm['mean'],norm['std']]).all() and norm['std']>0, 'Invalid normalization values')


def build(config, raw, output, artifacts):
    c = read_json(config)
    validate_config(c)
    need(all((ROOT/p).is_file() for p in SOURCE_PATHS),'Missing frozen/source dependency before build')
    need(not output.exists() and not artifacts.exists(), 'Output exists; use a new revision, never overwrite')
    need(artifacts.resolve().is_relative_to(ROOT/'ml/data'), 'Large artifacts must stay in ignored ml/data')
    ignored = subprocess.run(['git','-C',str(ROOT),'check-ignore','-q',str(artifacts.resolve()/'train_X.npy')])
    need(ignored.returncode==0, 'Large artifact destination must be Git-ignored')
    hashes = check_raw(raw,c)
    output.mkdir(parents=True)
    artifacts.mkdir(parents=True)
    # DS1 is loaded and split first. DS2 metadata cannot influence the rule.
    data = {r:load_record(raw,r) for r in DS1}
    val, selection, combinations = choose_validation(c, {r:data[r][3]['accepted_counts'] for r in DS1})
    write_table(output/'validation-combinations.csv.gz',combinations)
    write_json(output/'validation-feasibility.json',selection['enumeration'])
    rows = [{'record_id':r,'patient_id':patient(r),'split':
             ('val' if r in val else 'train') if r in DS1 else
             'test_main' if r in DS2 else 'auxiliary_only' if r=='202' else 'excluded'}
            for r in sorted(DS1+DS2+['202']+PACED)]
    write_csv(output/'split.csv', rows, ['record_id','patient_id','split'])
    groups = split_records(rows)
    sums = [float(data[r][0].sum(dtype=np.float64)) for r in groups['train']]
    squares = [float(np.square(data[r][0]).sum(dtype=np.float64)) for r in groups['train']]
    n = sum(data[r][0].size for r in groups['train'])
    mean = sum(sums)/n
    std = float(np.sqrt(sum(squares)/n - mean*mean))
    norm = {'schema_version':3,'status':c['status'],'fit_split':'train','fit_records':groups['train'],
            'fit_patient_ids':[patient(r) for r in groups['train']], 'num_values':n,'num_train_beats':n//360,
            'mean':mean,'std':std,'config_sha256':digest(config,True),
            'split_sha256':digest(output/'split.csv',True), 'definition':'population variance; overlapping accepted train windows count separately'}
    norm_binding(norm,groups)
    write_json(output/'normalization.json',norm)
    val_y=np.concatenate([data[r][1] for r in groups['val']])
    metric_policy=freeze_validation_policy(val_y)
    write_json(output/'metric-policy.json',metric_policy)
    data.update({r:load_record(raw,r) for r in DS2+['202']})
    audit = [data[r][3] for r in sorted(data)]
    for r in PACED:
        h = wfdb.rdheader(str(Path(raw)/r))
        audit.append({'record_id':r,'patient_id':patient(r),'signal_names':h.sig_name,
                      'lead_index':h.sig_name.index('MLII') if 'MLII' in h.sig_name else None,
                      'fs':h.fs,'excluded_reason':'paced_record'})
    write_json(output/'record-audit.json',sorted(audit,key=lambda a:a['record_id']))
    summary, files = {}, {}
    sets = {s:groups[s] for s in ['train','val','test_main']}
    sets['test_aux22'] = sorted(DS2+['202'])
    for s, records in sets.items():
        x = np.concatenate([((data[r][0]-mean)/std).astype('<f4') for r in records])
        y = np.concatenate([data[r][1] for r in records])
        meta = list(itertools.chain.from_iterable(data[r][2] for r in records))
        np.save(artifacts/(s+'_X.npy'),x,allow_pickle=False)
        np.save(artifacts/(s+'_y.npy'),y,allow_pickle=False)
        write_csv(artifacts/(s+'_metadata.csv'),meta,SCHEMA)
        summary[s] = {'records':records,'patients':sorted({patient(r) for r in records}),
                      'samples':len(y),'counts':np.bincount(y,minlength=5).tolist()}
        for suffix in ['X.npy','y.npy','metadata.csv']:
            name = s+'_'+suffix
            files[name] = {'sha256':digest(artifacts/name),'bytes':(artifacts/name).stat().st_size}
    manifest = {'schema_version':3,'candidate_id':c['candidate_id'],'status':c['status'],
                'source_head':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
                'config_sha256':digest(config,True),'split_sha256':digest(output/'split.csv',True),
                'normalization_sha256':digest(output/'normalization.json',True),
                'record_audit_sha256':digest(output/'record-audit.json',True),
                'metric_policy_sha256':digest(output/'metric-policy.json',True),
                'feasibility_sha256':digest(output/'validation-feasibility.json',True),
                'combinations_gzip_sha256':digest(output/'validation-combinations.csv.gz'),
                'combinations_csv_sha256':hashlib.sha256(gzip.decompress((output/'validation-combinations.csv.gz').read_bytes())).hexdigest(),
                'decision_status':c['approval'],
                'sources_sha256':{p:digest(ROOT/p,True) for p in SOURCE_PATHS},
                'raw_sha256':hashes,'selection':selection,'splits':summary,'artifacts':files,
                'test_aux22_warning':'Contains patient P201_202 also in DS1; supplementary literature comparison only, never selection/calibration.',
                'model_predictions_performed':False,'training_performed':False,'review':'NOT_REVIEWED',
                'hash_policy':c['hash_policy']}
    write_json(output/'processed-manifest.json',manifest)
    print(json.dumps({'status':'BUILT_CANDIDATE_NOT_LOCKED','validation':val,'normalization':norm,
                      'splits':summary},indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--raw-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--artifacts',type=Path,required=True)
    a = p.parse_args()
    build(a.config,a.raw_dir,a.output,a.artifacts)


if __name__=='__main__':
    main()
