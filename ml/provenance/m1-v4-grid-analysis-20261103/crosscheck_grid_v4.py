"""Independent re-derivation of the M1 v4 grid selection from slot files; no v4 code import, no arrays, no model, no DS2."""
import argparse
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parents[3]
PROTOCOL='ml/configs/mitdb_m1_baseline_protocol_v4.json'
PLAN='ml/manifests/mitdb-baseline-grid-v4/plan-manifest.json'
RESULTS='ml/data/runs/mitdb-baseline-v4-20261103'
ANALYZE='ml/provenance/m1-v4-grid-analysis-20261103/logs/analyze-normal.stdout.json'
K=4  # N,S,V,F; Q excluded from the fixed macro-F1


def need(ok,message):
    if not ok: raise SystemExit('CROSSCHECK_FAIL: '+message)


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))


def r4(x):return Decimal(str(x)).quantize(Decimal('0.0001'),rounding=ROUND_HALF_UP)


def macro_f1(c):
    f=[]
    for k in range(K):
        tp=c[k][k];sup=sum(c[k]);pred=sum(row[k] for row in c)
        f.append(Fraction(2*tp,sup+pred) if sup+pred else Fraction(0))
    return sum(f)/K


def gates(c):
    n=sum(map(sum,c));sup=[sum(r) for r in c];pred=[sum(r[k] for r in c) for k in range(5)]
    se=lambda k:Fraction(c[k][k],sup[k]) if sup[k] else None
    pp=lambda k:Fraction(c[k][k],pred[k]) if pred[k] else None
    ok=lambda v,t:v is not None and v>=t
    return {'N':Fraction(pred[0],n)<=Fraction(sup[0],n)+Fraction(1,10),
            'V':ok(se(2),Fraction(1,2)) and ok(pp(2),Fraction(1,2)),
            'S':ok(se(1),Fraction(1,5)) and ok(pp(1),Fraction(1,10))}


def slot(results,entry,support):
    ledger=read(results/entry['slot_id']/'slot-result.json')
    # The ledger row is the plan slot entry copied verbatim plus status/attempts.
    need({k:v for k,v in ledger.items() if k not in ('status','attempts')}==entry,'Ledger is not plan entry + status/attempts: '+entry['slot_id'])
    need(ledger['status']=='COMPLETED' and len(ledger['attempts'])==1 and ledger['attempts'][0]['exit_code']==0,'Not a single clean attempt: '+entry['slot_id'])
    target=results/ledger['attempts'][0]['path']
    for log in ('stdout.txt','stderr.txt'):need(target.joinpath(log).stat().st_size==0,'Non-empty '+log+': '+entry['slot_id'])
    summary=read(target/'summary.json');history=read(target/'history.json');ident=read(target/'attempt-identity.json')
    need(ident['DS2_arrays_opened'] is False and summary['DS2_evaluated'] is False,'DS2 flag set: '+entry['slot_id'])
    need(ident['seed']==entry['seed'] and ident['config_sha256']==summary['config_sha256']==entry['sha256'],'Identity differs: '+entry['slot_id'])
    need(sha(target/'history.json')==summary['history_sha256'],'History hash differs: '+entry['slot_id'])
    need([e['epoch'] for e in history]==list(range(1,len(history)+1)),'Epoch order differs: '+entry['slot_id'])
    for e in history:
        cm=e['validation']['confusion_matrix'];need([sum(r) for r in cm]==support,'Validation support differs')
        need(math.isclose(float(macro_f1(cm)),e['score'],rel_tol=0,abs_tol=1e-12),'Epoch score differs: '+entry['slot_id'])
        need(read(target/f"epoch-{e['epoch']:03d}.json")['score']==e['score'],'Epoch file differs from history: '+entry['slot_id'])
    best=max(history,key=lambda e:(r4(e['score']),-e['epoch']))
    need(best['epoch']==summary['selected_epoch'] and summary['checkpoint']==f"checkpoint-epoch-{best['epoch']:03d}.pt",'Selected epoch differs: '+entry['slot_id'])
    need(summary['validation']==best['validation'] and summary['reload_confusion_exact'] is True,'Reload validation differs: '+entry['slot_id'])
    ckpt=target/summary['checkpoint'];digest=sha(ckpt);need(digest==summary['checkpoint_sha256'],'Checkpoint hash differs: '+entry['slot_id'])
    v=summary['validation'];cm=v['confusion_matrix']
    return {'slot_id':entry['slot_id'],'configuration':entry['configuration'],'seed':entry['seed'],
            'epochs_run':len(history),'selected_epoch':best['epoch'],'score':best['score'],'score_r4':str(r4(best['score'])),
            'gates':gates(cm),'SeS':v['recall'][1],'PS':v['precision'][1],'SeV':v['recall'][2],'PV':v['precision'][2],
            'predN_minus_trueN_fraction':(sum(r[0] for r in cm)-sum(cm[0]))/sum(map(sum,cm)),
            'checkpoint':ckpt.relative_to(ROOT).as_posix(),'checkpoint_bytes':ckpt.stat().st_size,'checkpoint_sha256':digest}


def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--out',type=Path,required=True);o=a.parse_args()
    need(not o.out.exists(),'Output exists; use a new name')
    plan=read(ROOT/PLAN);results=ROOT/RESULTS;grid=read(results/'grid-result.json')
    need(grid['protocol_sha256']==sha(ROOT/PROTOCOL)==plan['binding']['protocol_sha256'] and grid['plan_sha256']==sha(ROOT/PLAN),'Grid binding differs')
    need(grid['status']=='ALL18_SLOTS_TERMINAL_NOT_MODEL_LOCK' and grid['attempted_slots']==18,'Grid not terminal')
    need(sorted(p.name for p in results.iterdir())==sorted([s['slot_id'] for s in plan['slots']]+['grid-result.json']),'Unexpected run directory entries')
    support=read(ROOT/plan['binding']['metric_policy'])['validation_support']
    rows=[slot(results,e,support) for e in plan['slots']]
    configs=[]
    for c in [x['id'] for x in read(ROOT/PROTOCOL)['baseline']['configuration_order']]:
        g=[r for r in rows if r['configuration']==c];scores=np.array([r['score'] for r in g])
        best=max(g,key=lambda r:(r4(r['score']),-r['seed']))
        configs.append({'configuration':c,'mean':float(scores.mean()),'sd_ddof1':float(scores.std(ddof=1)),
                        'best_seed':best['seed'],'best_gates':best['gates']})
    nv=[c for c in configs if c['best_gates']['N'] and c['best_gates']['V']]
    pool=[c for c in nv if c['best_gates']['S']] or nv;need(bool(pool),'No N/V configuration')
    chosen=max(pool,key=lambda c:(r4(c['mean']),-int(c['configuration'][1:])))
    ranked=sorted(pool,key=lambda c:(r4(c['mean']),-int(c['configuration'][1:])),reverse=True)
    # Compare with the official analyze output.
    an=read(ROOT/ANALYZE);need(an['status']=='SELECTED_FOR_OWNER_REVIEW_NOT_MODEL_LOCK','Analyze status differs')
    need(an['selected']['configuration']==chosen['configuration'] and an['selected']['seed']==chosen['best_seed'],'Selection differs from analyze')
    for c,ac in zip(configs,an['configurations']):
        need(ac['configuration']==c['configuration'] and ac['best_seed']==c['best_seed'],'Best seed differs')
        need(math.isclose(ac['mean_macro_f1'],c['mean'],rel_tol=0,abs_tol=1e-12) and math.isclose(ac['sd_sample'],c['sd_ddof1'],rel_tol=0,abs_tol=1e-12),'Mean/SD differs')
        for s in ac['seeds']:
            r=next(x for x in rows if x['configuration']==c['configuration'] and x['seed']==s['seed'])
            need(s['gates']==r['gates'] and s['selected_epoch']==r['selected_epoch'] and s['checkpoint_sha256']==r['checkpoint_sha256'] and s['score']==r['score'],'Seed row differs')
    out={'status':'CROSSCHECK_MATCH_ANALYZE_NOT_MODEL_LOCK','grid_result_sha256':sha(results/'grid-result.json'),
         'analyze_stdout_sha256':sha(ROOT/ANALYZE),'protocol_sha256':grid['protocol_sha256'],'plan_sha256':grid['plan_sha256'],
         'selected':{'configuration':chosen['configuration'],'deployment_seed':chosen['best_seed'],'mean_r4':str(r4(chosen['mean']))},
         'margin_to_runner_up_r4':str(r4(ranked[0]['mean'])-r4(ranked[1]['mean'])) if len(ranked)>1 else None,
         'runner_up':ranked[1]['configuration'] if len(ranked)>1 else None,
         'configurations':configs,'slots':rows,'DS2_opened':False,'arrays_opened':False,'model_instantiated':False}
    o.out.parent.mkdir(parents=True,exist_ok=True)
    with o.out.open('x',encoding='utf-8',newline='\n') as f:f.write(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(out['status'],chosen['configuration'],chosen['best_seed'])


if __name__=='__main__':main()
