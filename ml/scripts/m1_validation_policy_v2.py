"""DS1-only exhaustive validation policies and portable seeded one-draw selection."""
import csv
import gzip
import hashlib
import io
import itertools

CLASSES = ['N','S','V','F','Q']
POLICIES = ['A','B','C']


def need(ok,message):
    if not ok:
        raise ValueError(message)


def feasible(values,total,policy):
    need(policy in POLICIES,'Unknown validation interpretation')
    upper = all(10*values[k] <= 3*total[k] for k in range(4))
    lower = all(10*values[k] >= total[k] for k in (range(4) if policy=='A' else (1,2)))
    return upper and lower and (policy!='C' or values[3]>=1)


def enumerate_combinations(counts,records):
    # Ignore any non-DS1 entries supplied by callers.
    records=sorted(records)
    need(len(records)==len(set(records)),'Duplicate DS1 record')
    need(all(len(counts[r])==5 and all(type(v) is int and v>=0 for v in counts[r]) for r in records),
         'Invalid DS1 accepted counts')
    total=[sum(counts[r][k] for r in records) for k in range(5)]
    need(total[1]>0 and total[2]>0,'DS1 S/V support required')
    rows=[]
    for size in [4,5]:
        for combo in itertools.combinations(records,size):
            values=[sum(counts[r][k] for r in combo) for k in range(5)]
            rows.append({'size':size,'records':combo,'counts':values,
                         **{p:feasible(values,total,p) for p in POLICIES}})
    summary={'ds1_counts':total,'selection_inputs':'accepted DS1 labels only; no DS2 or model metric','sizes':{}}
    for size in [4,5]:
        current=[r for r in rows if r['size']==size]
        policies={}
        for policy in POLICIES:
            accepted=[r for r in current if r[policy]]
            policies[policy]={'feasible':len(accepted),
                'zero_F_combinations':sum(r['counts'][3]==0 for r in accepted),
                'validation_support_range':{name:[min(r['counts'][k] for r in accepted),max(r['counts'][k] for r in accepted)]
                    if accepted else None for k,name in enumerate(CLASSES)},
                'train_support_range':{name:[total[k]-max(r['counts'][k] for r in accepted),total[k]-min(r['counts'][k] for r in accepted)]
                    if accepted else None for k,name in enumerate(CLASSES)}}
        summary['sizes'][str(size)]={'total_combinations':len(current),'policies':policies}
    return rows,summary


def sample_index(size,seed):
    need(type(size) is int and size>0,'No feasible validation combination; no threshold relaxation')
    need(type(seed) is int and seed>=0,'Invalid split seed')
    limit=(1<<256)-((1<<256)%size)
    counter=0
    while True:
        digest=hashlib.sha256(f'm1-validation-v2|{seed}|{counter}'.encode('ascii')).hexdigest()
        value=int(digest,16)
        if value<limit:
            return value%size,{'draw_sha256':digest,'counter':counter,'feasible_count':size,
                              'selected_zero_based_index':value%size,'seed':seed}
        counter+=1


def choose(rows,policy,seed):
    need(policy in POLICIES,'Unknown validation interpretation')
    selected_size=None
    for size in [4,5]:
        accepted=[r for r in rows if r['size']==size and r[policy]]
        if accepted:
            selected_size=size
            break
    need(selected_size is not None,'No feasible validation combination; no threshold relaxation')
    index,draw=sample_index(len(accepted),seed)
    selected=accepted[index]
    return list(selected['records']),{'policy':policy,'records':selected_size,**draw,
        'validation_counts':selected['counts'],'algorithm':'SHA256-counter-rejection-lexicographic-index-v2'}


def table_bytes(rows):
    stream=io.StringIO(newline='')
    w=csv.writer(stream,lineterminator='\n')
    w.writerow(['records_count','records','N','S','V','F','Q','A','B','C'])
    for row in rows:
        w.writerow([row['size'],','.join(row['records']),*row['counts'],*[int(row[p]) for p in POLICIES]])
    return stream.getvalue().encode('utf-8')


def write_table(path,rows):
    # mtime=0 and blank filename make compressed bytes independent of time/path.
    with path.open('xb') as f:
        with gzip.GzipFile(filename='',mode='wb',fileobj=f,mtime=0) as g:
            g.write(table_bytes(rows))
