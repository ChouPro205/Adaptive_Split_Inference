"""Prepare or verify fixed validation dCor IDs and an unexecuted trial register."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

import baseline_sampler_v4 as sampler
from m1_metrics_v4 import S_SOFT_LABEL

ROOT=Path(__file__).resolve().parents[2]
CLASSES=['N','S','V','F','Q']


def need(ok,message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def csv_bytes(fields,rows):
    stream=io.StringIO(newline='')
    w=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n')
    w.writeheader()
    w.writerows(rows)
    return stream.getvalue().encode('utf-8')


def json_bytes(value):
    return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8')


def inputs(protocol,artifacts):
    p=read(protocol)
    need(p['status']=='CANDIDATE_RULES_CONFIRMED_ARTIFACT_NOT_REVIEWED' and
         p['authority']['locked'] is False and p['authority']['training_permitted'] is False and
         p['authority']['artifact_review']=='NOT_REVIEWED','Unreviewed protocol cannot claim lock/authority')
    need(not any(p['execution_in_this_round'].values()),'Execution scope differs')
    need(p['nopeek']['utility'].startswith('EVERY_SEED'),'NoPeek requires every seed utility')
    need(p['baseline']['balanced_sampler_policy_id']==sampler.POLICY_ID,'Protocol sampler policy differs')
    need(p['baseline']['gates']['S_soft_label']==S_SOFT_LABEL,'Protocol S soft-gate label differs')
    manifest=read(ROOT/p['data']['manifest'])
    for label,path in [('config',p['data']['config']),('manifest',p['data']['manifest']),
                       ('normalization',p['data']['normalization']),('metric_policy',p['data']['metric_policy'])]:
        need(sha(ROOT/path)==p['data']['sha256_bindings'][label], 'Protocol data hash differs: '+label)
    for name,entry in manifest['artifacts'].items():
        if name=='val_metadata.csv':
            need(sha(artifacts/name)==entry['sha256'],'Validation metadata binding differs')
    with (artifacts/'val_metadata.csv').open(encoding='utf-8',newline='') as f:
        metadata=list(csv.DictReader(f))
    need(len(metadata)==manifest['splits']['val']['samples'],'Validation row count differs')
    return p,manifest,metadata


def assets(protocol,artifacts):
    p,m,metadata=inputs(protocol,artifacts)
    policy=p['nopeek']['fixed_dcor_validation_subset']
    need(policy['count']==512 and policy['seed']==20261030 and policy['domain']=='dcor-validation-v2',
         'Subset policy differs')
    need(len(metadata)>=policy['count'],'Too few validation samples for fixed dCor subset')
    ranked=[]
    for i,row in enumerate(metadata):
        identity='|'.join([policy['domain'],str(policy['seed']),row['patient_id'],row['record_id'],
                           row['r_peak_sample'],row['original_symbol'],row['lead_name']])
        rank=hashlib.sha256(identity.encode('ascii')).hexdigest()
        ranked.append((rank,i,row))
    selected=sorted(ranked,key=lambda x:(x[0],x[1]))[:policy['count']]
    fields=['validation_row_index','patient_id','record_id','r_peak_sample','original_symbol','lead_name','rank_sha256']
    subset=[dict(zip(fields,[i,row['patient_id'],row['record_id'],row['r_peak_sample'],
                            row['original_symbol'],row['lead_name'],rank])) for rank,i,row in selected]
    train=m['splits']['train']
    trials=p['baseline']['configuration_order']
    seeds=p['baseline']['seeds']
    need(len(trials)==6 and len(seeds)==3,'Six configurations and three seeds required')
    weights={t['id']:({c:min(t['cap'],train['samples']/(5*n)) if n else 0
                        for c,n in zip(CLASSES,train['counts'])} if t['mode']=='weighted_ce' else None) for t in trials}
    samplers={t['id']:({'policy':sampler.POLICY_ID,'formula':p['baseline']['balanced_sampler'],
                        'expected_draws_per_epoch':dict(zip(CLASSES,map(str,sampler.expected_draws(train['counts'])))),
                        'per_class_sample_weight':dict(zip(CLASSES,sampler.per_class_sample_weight(train['counts'])))}
                       if t['mode']=='balanced_sampler' else None) for t in trials}
    ledger=[{'trial':t['id'],'seed':s,'cap':t['cap'],'learning_rate':t['lr'],
             'state':'PLANNED_NOT_STARTED','data_manifest_sha256':sha(ROOT/p['data']['manifest']),
             'protocol_sha256':sha(protocol)} for t in trials for s in seeds]
    return {'dcor-validation-subset.csv':csv_bytes(fields,subset),
            'class-weights-by-trial.json':json_bytes({'status':'PROPOSED_NOT_TRAINED','train_counts':train['counts'],
             'train_samples':train['samples'],'formula':p['baseline']['weight_formula'],
             'weights':weights,'balanced_samplers':samplers}),
            'baseline-trial-register.csv':csv_bytes(list(ledger[0]),ledger)}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['build','verify'])
    p.add_argument('--protocol',type=Path,required=True)
    p.add_argument('--artifacts',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    expected=assets(a.protocol,a.artifacts)
    source_path='ml/scripts/prepare_m1_protocol_assets_v4.py'
    identity={'status':'CANDIDATE_ASSETS_NOT_LOCKED_NOT_TRAINED',
              'protocol_sha256':sha(a.protocol),'generator_sha256':sha(ROOT/source_path),
              'artifacts':{n:hashlib.sha256(b).hexdigest() for n,b in expected.items()},
              'subset_samples':512,'planned_seed_fits':18,'executed_seed_fits':0,'model_predictions':False}
    if a.mode=='build':
        need(not a.output.exists(),'Output exists; create a new version')
        a.output.mkdir(parents=True)
        for name,content in expected.items():
            (a.output/name).write_bytes(content)
        (a.output/'assets-manifest.json').write_bytes(json_bytes(identity))
        print('BUILT_CANDIDATE_PROTOCOL_ASSETS_NO_TRAINING')
    else:
        need(set(x.name for x in a.output.iterdir())==set(expected)|{'assets-manifest.json'},'Asset inventory differs')
        need(read(a.output/'assets-manifest.json')==identity,'Protocol asset identity/hash binding differs')
        for name,content in expected.items():
            need((a.output/name).read_bytes()==content,'Protocol asset semantic reconstruction differs: '+name)
        print('PASS_PROTOCOL_CANDIDATE_AND_ASSETS_NOT_LOCKED_NOT_TRAINED')


if __name__=='__main__':
    main()
