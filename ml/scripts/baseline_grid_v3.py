"""Prepare/preflight/run/analyze an18-slot baseline grid; fit requires external authority."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np
from baseline_selection_v3 import CONFIGS,SEEDS,choose_epoch,execute_all_slots,need,summarize_grid
from m1_metrics_v3 import freeze_validation_policy

ROOT=Path(__file__).resolve().parents[2]
SOURCES=['ml/scripts/baseline_grid_v3.py','ml/scripts/baseline_selection_v3.py',
         'ml/scripts/train_mitdb_baseline_v3.py','ml/scripts/m1_metrics_v3.py',
         'ml/src/mitdb_baseline_model.py','ml/configs/mitdb_week2_baseline.json']


def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))


def write(p,value):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    with Path(p).open('x',encoding='utf-8',newline='\n') as f:
        f.write(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def runtime():
    return {'python':platform.python_version(),'platform':platform.system(),'packages':
        {name:importlib.metadata.version(name) for name in ['numpy','torch','wfdb']},
        'cuda_driver':'NOT_PROBED_PREFLIGHT','model_instantiated':False}


def source_bindings():return {n:sha(ROOT/n) for n in SOURCES}


def prepare(protocol,output):
    p=read(protocol);d=read(ROOT/p['data']['manifest']);counts=d['splits']['train']['counts'];total=sum(counts)
    need(not output.exists(),'Plan exists; use a new revision')
    output.mkdir(parents=True)
    base={'protocol_sha256':sha(protocol),'dataset_manifest_sha256':sha(ROOT/p['data']['manifest']),
          'data_config_sha256':sha(ROOT/p['data']['config']),'metric_policy_sha256':sha(ROOT/p['data']['metric_policy']),
          'sources_sha256':source_bindings(),'runtime':runtime(),
          'data_files':{n:d['artifacts'][n] for n in d['artifacts'] if n.startswith(('train_','val_'))},
          'dataset_manifest':p['data']['manifest'],'metric_policy':p['data']['metric_policy'],
          'data_config':p['data']['config'],'source_head':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()}
    slots=[]
    for name,mode,cap,lr in CONFIGS:
        for seed in SEEDS:
            ident=f'{name}-seed{seed}'
            weights=[min(cap,total/(5*n)) if n else 0 for n in counts] if mode=='weighted_ce' else None
            config={**base,'slot_id':ident,'configuration':name,'seed':seed,'mode':mode,'cap':cap,'lr':lr,
                'class_weights':weights,'train_counts':counts,'samples_per_epoch':total,
                'sampler_replacement':mode=='balanced_sampler','batch_size':256,'epochs':40,'patience':10,
                'optimizer':'AdamW','betas':[.9,.999],'eps':1e-8,'weight_decay':.0001,'dropout':.2,
                'scheduler':{'name':'ReduceLROnPlateau','mode':'max','factor':.5,'patience':4,
                             'threshold':.0001,'threshold_mode':'rel','min_lr':0,'eps':1e-8},
                'threads':4,'device':'auto','num_workers':0,'augmentation':'none','drop_last':False,
                'epoch_seed_rule':'seed+epoch-1 for data-generator; global model/dropout RNG seeded once per attempt',
                'selection':'decimal string ROUND_HALF_UP4 then earliest epoch; seed lower; configuration lower',
                'early_stop_monitor':'unrounded validation macro-F1 strict improvement, patience10; scheduler unrounded',
                'state':'NOT_STARTED','DS2_access':False}
            file=ident+'.json';write(output/file,config)
            slots.append({'slot_id':ident,'configuration':name,'seed':seed,'config':file,'sha256':sha(output/file),'state':'NOT_STARTED'})
    write(output/'plan-manifest.json',{'status':'PREPARED_NOT_STARTED_NOT_AUTHORIZED','binding':base,'slots':slots,
          'training_permission':False,'expected_slots':18,'retry_same_seed':1,'stop_on_first_gate_pass':False})
    print('PREPARED18_SLOTS_NO_FIT')


def load_train_validation(directory):
    # Deliberately no test/evaluation dataset path or wildcard np.load here.
    data={}
    for split in ('train','val'):
        x=np.load(directory/(split+'_X.npy'),allow_pickle=False,mmap_mode='r')
        y=np.load(directory/(split+'_y.npy'),allow_pickle=False)
        need(x.dtype==np.dtype('<f4') and y.dtype==np.dtype('<i8') and x.shape==(len(y),360), 'Array contract differs')
        need(bool(np.isfinite(x).all()),'Non-finite train/validation array')
        data[split]=(x,y)
    return data


def preflight(protocol,plan_path,arrays):
    p=read(protocol);plan=read(plan_path);b=plan['binding']
    need(plan['expected_slots']==18 and len(plan['slots'])==18 and plan['stop_on_first_gate_pass'] is False,'Grid must contain18 slots')
    need(sha(protocol)==b['protocol_sha256'],'Protocol hash differs')
    need(source_bindings()==b['sources_sha256'] and runtime()==b['runtime'],'Source/runtime binding differs')
    freeze=read(ROOT/'ml/configs/week3_model_freeze.json')
    need(sha(ROOT/'ml/src/mitdb_baseline_model.py')==freeze['model_source_sha256'],'Frozen CNN source differs')
    for key,name in [('dataset_manifest_sha256','dataset_manifest'),('data_config_sha256','data_config'),('metric_policy_sha256','metric_policy')]:
        need(sha(ROOT/b[name])==b[key],'Data binding differs: '+name)
    need(read(ROOT/b['data_config'])['calibration_policy'].startswith('TRAIN_ONLY'),'Calibration must be train-only')
    need(set(b['data_files'])=={s+'_'+ext for s in ['train','val'] for ext in ['X.npy','y.npy','metadata.csv']},'Only train/val files permitted')
    for n,v in b['data_files'].items():need(sha(arrays/n)==v['sha256'],'Train/val file hash differs: '+n)
    data=load_train_validation(arrays)
    counts=np.bincount(data['train'][1],minlength=5).tolist()
    need(freeze_validation_policy(data['val'][1])==read(ROOT/b['metric_policy']),'Fixed metric policy differs')
    expected=[(c[0],s) for c in CONFIGS for s in SEEDS]
    need([(s['configuration'],s['seed']) for s in plan['slots']]==expected,'Slot order/inventory differs')
    for slot in plan['slots']:
        file=plan_path.parent/slot['config'];need(file.parent==plan_path.parent,'Unsafe slot path')
        need(sha(file)==slot['sha256'],'Slot hash differs')
        c=read(file);spec=CONFIGS[int(slot['configuration'][1:])]
        need(all(c[k]==v for k,v in b.items()),'Slot binding differs')
        need((c['configuration'],c['mode'],c['cap'],c['lr'])==spec and c['seed']==slot['seed'] and c['train_counts']==counts,'Slot policy differs')
        weights=[min(c['cap'],sum(counts)/(5*n)) if n else 0 for n in counts] if c['mode']=='weighted_ce' else None
        need(c['class_weights']==weights and c['samples_per_epoch']==sum(counts) and
             c['sampler_replacement']==(c['mode']=='balanced_sampler'),'Weight/sampler policy differs or double balancing')
        need(c['epochs']==40 and c['patience']==10 and c['batch_size']==256 and c['DS2_access'] is False,'Training duration/scope differs')
        need(c['optimizer']=='AdamW' and c['weight_decay']==.0001 and c['dropout']==.2 and
             c['betas']==[.9,.999] and c['eps']==1e-8 and c['scheduler']['mode']=='max', 'Week2 optimizer/architecture policy differs')
    return {'status':'PASS_PREFLIGHT_NO_MODEL_NO_FIT_NO_DS2','slots':18,'train_counts':counts,
            'validation_counts':np.bincount(data['val'][1],minlength=5).tolist(),
            'protocol_sha256':sha(protocol),'plan_sha256':sha(plan_path),'runtime':runtime(),
            'fit_calls':0,'optimizer_steps':0,'DS2_arrays_opened':False}


def require_authorization(path,protocol,plan):
    need(path is not None and Path(path).is_file(),'External owner lock and train authorization required; candidate alone grants none')
    a=read(path)
    need(a.get('type')=='M1_BASELINE_LOCK_AND_TRAIN_AUTHORIZATION' and a.get('allow_training') is True and
         a.get('protocol_sha256')==sha(protocol) and a.get('plan_manifest_sha256')==sha(plan) and
         bool(a.get('approved_by')) and bool(a.get('review_evidence')),'Authorization does not bind reviewed protocol/plan')
    return a


def run_grid(protocol,plan_path,arrays,output,authorization):
    require_authorization(authorization,protocol,plan_path)  # Before data/model/optimizer or output mutation.
    preflight(protocol,plan_path,arrays);plan=read(plan_path)
    need(output.resolve().is_relative_to(ROOT/'ml/data') and not output.exists(),'Run output must be new ignored ml/data path')
    output.mkdir(parents=True)
    def executor(slot):
        attempts=[];status='FAILED_TECHNICAL'
        for attempt in [1,2]:
            target=output/slot['slot_id']/f'attempt-{attempt}';target.mkdir(parents=True)
            argv=[sys.executable,'-B',str(ROOT/'ml/scripts/train_mitdb_baseline_v3.py'),
                  '--protocol',str(protocol),'--plan',str(plan_path),'--arrays',str(arrays),
                  '--slot',slot['slot_id'],'--output',str(target),'--authorization',str(authorization)]
            r=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
            (target/'stdout.txt').write_text(r.stdout,encoding='utf-8',newline='\n')
            (target/'stderr.txt').write_text(r.stderr,encoding='utf-8',newline='\n')
            attempts.append({'attempt':attempt,'exit_code':r.returncode,'summary_exists':(target/'summary.json').is_file(),
                             'path':target.relative_to(output).as_posix(),
                             'config_sha256':slot['sha256'],'seed':slot['seed']})
            if r.returncode==0 and (target/'summary.json').is_file():status='COMPLETED';break
        row={**slot,'status':status,'attempts':attempts}
        write(output/slot['slot_id']/'slot-result.json',row)
        return row
    results=execute_all_slots(plan['slots'],executor)
    write(output/'grid-result.json',{'protocol_sha256':sha(protocol),'plan_sha256':sha(plan_path),'slots':results,
        'attempted_slots':18,'status':'ALL18_SLOTS_TERMINAL_NOT_MODEL_LOCK'})


def metric_from_matrix(matrix):
    c=np.asarray(matrix);need(c.shape==(5,5) and np.issubdtype(c.dtype,np.integer) and (c>=0).all(),'Invalid confusion')
    support=c.sum(1);pred=c.sum(0);tp=c.diagonal();n=int(c.sum());need(n>0,'Empty confusion')
    f1=np.divide(2*tp,support+pred,out=np.zeros(5,dtype=float),where=(support+pred)!=0)
    gates={'N':bool(10*(int(pred[0])-int(support[0]))<=n),
           'V':bool(support[2]>0 and pred[2]>0 and 2*tp[2]>=support[2] and 2*tp[2]>=pred[2]),
           'S':bool(support[1]>0 and pred[1]>0 and 5*tp[1]>=support[1] and 10*tp[1]>=pred[1])}
    return float(f1[:4].mean()),gates,support.tolist()


def analyze(protocol,plan_path,results):
    plan=read(plan_path);grid=read(results/'grid-result.json')
    need(grid['protocol_sha256']==sha(protocol) and grid['plan_sha256']==sha(plan_path),'Grid binding differs')
    need(len(grid['slots'])==18 and {r['slot_id'] for r in grid['slots']}=={r['slot_id'] for r in plan['slots']},'Incomplete grid')
    rows=[]
    support=read(ROOT/plan['binding']['metric_policy'])['validation_support']
    for expected in plan['slots']:
        r=read(results/expected['slot_id']/'slot-result.json')
        need(r==next(v for v in grid['slots'] if v['slot_id']==expected['slot_id']),'Slot ledger differs')
        need(r['sha256']==expected['sha256'] and len(r['attempts']) in (1,2),'Attempt binding differs')
        need(all(r[k]==expected[k] for k in ['slot_id','configuration','seed','config']),'Slot identity differs')
        need([a['attempt'] for a in r['attempts']]==list(range(1,len(r['attempts'])+1)),'Retry ordinal differs')
        if r['status']=='FAILED_TECHNICAL':need(len(r['attempts'])==2,'Failed slot must retain both attempts')
        else:need(r['attempts'][-1]['exit_code']==0 and r['attempts'][-1]['summary_exists'],'Successful attempt missing summary')
        for attempt in r['attempts']:
            need(attempt['seed']==expected['seed'] and attempt['config_sha256']==expected['sha256'],'Retry changed seed/config')
        row={'configuration':expected['configuration'],'seed':expected['seed'],'status':r['status']}
        if r['status']=='COMPLETED':
            target=(results/r['attempts'][-1]['path']).resolve();need(target.is_relative_to(results.resolve()),'Unsafe attempt path')
            summary=read(target/'summary.json');history=read(target/'history.json')
            need(summary['config_sha256']==expected['sha256'] and summary['protocol_sha256']==sha(protocol),'Summary binding differs')
            need(sha(target/'history.json')==summary['history_sha256'] and sha(target/summary['checkpoint'])==summary['checkpoint_sha256'],'History/checkpoint hash differs')
            need([e['epoch'] for e in history]==list(range(1,len(history)+1)) and 1<=len(history)<=40,'Epoch inventory differs')
            for e in history:
                score,_,s=metric_from_matrix(e['validation']['confusion_matrix'])
                need(s==support and math.isclose(score,e['score'],abs_tol=1e-12,rel_tol=0),'History metric differs')
            best=choose_epoch(history);score,gates,s=metric_from_matrix(summary['validation']['confusion_matrix'])
            need(best['epoch']==summary['selected_epoch'] and summary['validation']==best['validation'] and s==support,'Checkpoint selection differs')
            row.update(score=score,gates=gates,validation=summary['validation'],selected_epoch=best['epoch'],
                       checkpoint_sha256=summary['checkpoint_sha256'])
        rows.append(row)
    return summarize_grid(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['prepare','preflight','run','analyze'])
    p.add_argument('--protocol',type=Path,required=True);p.add_argument('--plan',type=Path)
    p.add_argument('--arrays',type=Path);p.add_argument('--output',type=Path)
    p.add_argument('--authorization',type=Path);p.add_argument('--results',type=Path)
    a=p.parse_args()
    if a.mode=='prepare':prepare(a.protocol,a.output)
    elif a.mode=='preflight':print(json.dumps(preflight(a.protocol,a.plan,a.arrays),indent=2))
    elif a.mode=='run':run_grid(a.protocol,a.plan,a.arrays,a.output,a.authorization)
    else:print(json.dumps(analyze(a.protocol,a.plan,a.results),indent=2))


if __name__=='__main__':main()
