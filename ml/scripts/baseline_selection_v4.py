"""Pure baseline selection: rounded ties, unrounded gates, all six configurations."""
from decimal import Decimal, ROUND_HALF_UP
import math
import statistics

from m1_metrics_v4 import S_SOFT_LABEL

SEEDS=[20261030,20261031,20261101]
CONFIGS=[('C0','weighted_ce',10,.001),('C1','weighted_ce',10,.0003),
         ('C2','weighted_ce',50,.001),('C3','weighted_ce',50,.0003),
         ('C4','balanced_sampler',None,.001),('C5','balanced_sampler',None,.0003)]
MAX_ATTEMPTS=2
COMPLETE_STATUS='ALL18_SLOTS_TERMINAL_NOT_MODEL_LOCK'
HALT_STATUS='HALTED_PRE_VALIDATION_CODE_FAULT'


def need(ok,message):
    if not ok: raise ValueError(message)


def rounded(value):
    need(type(value) in (int,float) and math.isfinite(value) and 0<=value<=1,'Invalid selection metric')
    return Decimal(str(value)).quantize(Decimal('0.0001'),rounding=ROUND_HALF_UP)


def choose_epoch(history):
    need(bool(history),'Empty epoch history')
    need(len({r['epoch'] for r in history})==len(history),'Duplicate epoch')
    return max(history,key=lambda r:(rounded(r['score']),-r['epoch']))


def choose_seed(rows):
    need(len(rows)==3 and {r['seed'] for r in rows}==set(SEEDS),'Exactly three fixed seeds required')
    return max(rows,key=lambda r:(rounded(r['score']),-r['seed']))


def summarize_grid(rows):
    expected={(c[0],s) for c in CONFIGS for s in SEEDS}
    need(len(rows)==18 and {(r['configuration'],r['seed']) for r in rows}==expected,'All18 unique slots required; no early stop')
    need(all(r['status'] in ('COMPLETED','FAILED_TECHNICAL') for r in rows),'Grid contains unstarted slots')
    groups=[]
    for name,*_ in CONFIGS:
        group=[r for r in rows if r['configuration']==name]
        entry={'configuration':name,'seeds':group,'mean_macro_f1':None,'sd_sample':None,
               'best_seed':None,'NV':False,'S':False,'eligible':False}
        if all(r['status']=='COMPLETED' for r in group):
            scores=[r['score'] for r in group]
            best=choose_seed(group)
            entry.update(mean_macro_f1=math.fsum(scores)/3,sd_sample=statistics.stdev(scores),
                best_seed=best['seed'],NV=bool(best['gates']['N'] and best['gates']['V']),S=bool(best['gates']['S']))
            entry['eligible']=entry['NV']
        groups.append(entry)
    nv=[r for r in groups if r['NV']]
    pool=[r for r in nv if r['S']] or nv
    if not pool:
        return {'status':'NO_NV_CONFIGURATION_STOP_REPORT_NO_GRID_EXPANSION','configurations':groups,'selected':None}
    selected=max(pool,key=lambda r:(rounded(r['mean_macro_f1']),-int(r['configuration'][1:])))
    return {'status':'SELECTED_FOR_OWNER_REVIEW_NOT_MODEL_LOCK','configurations':groups,
            'selected':{'configuration':selected['configuration'],'seed':selected['best_seed'],
                        'mean_macro_f1':selected['mean_macro_f1'],'S_gate_pass':selected['S'],
                        'S_failure_disclosure_required':not selected['S'],
                        'package_A_gate':'PASS' if selected['S'] else S_SOFT_LABEL}}


def pre_validation_code_fault(row):
    # Retries exhausted and no attempt wrote epoch-001.json, so no validation result exists.
    return (row['status']=='FAILED_TECHNICAL' and len(row['attempts'])==MAX_ATTEMPTS and
            not any(a['validation_epoch_written'] for a in row['attempts']))


def execute_all_slots(slots,executor):
    # No performance gate can break this loop; only a first-slot pre-validation code fault halts it.
    results=[]
    for index,slot in enumerate(slots):
        row=executor(slot);results.append(row)
        if index==0 and pre_validation_code_fault(row):return results,HALT_STATUS
    return results,COMPLETE_STATUS
