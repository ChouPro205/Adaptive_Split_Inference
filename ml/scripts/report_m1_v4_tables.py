"""Render M1 v4 review tables from record-audit, manifests, protocol and diff index; no arrays, model or DS2 inference."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
PROTOCOL='ml/configs/mitdb_m1_baseline_protocol_v4.json'
DIFF_INDEX='ml/provenance/m1-v4-20261103/diff-index.json'
V3_SUMS='ml/provenance/m1-v3-20261030/SHA256SUMS.txt'
CLASSES=['N','S','V','F','Q']
# Published counts quoted by v1.2 section 4.1 (arXiv 2503.07276, table 3).
PUBLISHED={'DS1_total':51021,'DS2_full_total':49712,'DS2_full_counts':[44259,1837,3221,388,7]}
# Existing v3 evidence cited for the section 4.1 checks; hashes are re-read and matched to v3 SHA256SUMS.
EVIDENCE=[('data-verify-normal.txt','Verifier v3: raw checksum, kênh, nhãn, split, normalization'),
          ('data-unit-tests-normal.txt','43 unit test dữ liệu v3'),
          ('data-ds2-in-train-normal.txt','Negative: đưa bản ghi DS2 vào train bị từ chối'),
          ('data-202-in-val-normal.txt','Negative: đưa 202 vào validation bị từ chối'),
          ('data-patient-forgery-normal.txt','Negative: giả patient ID của 202 bị từ chối'),
          ('data-metadata-lead-normal.txt','Negative: sửa lead trong metadata bị từ chối'),
          ('data-missing-record-normal.txt','Negative: thiếu bản ghi trong manifest bị từ chối')]
BEGIN='<!-- BEGIN GENERATED: ml/scripts/report_m1_v4_tables.py -->'
END='<!-- END GENERATED -->'


def need(ok,message):
    if not ok: raise ValueError(message)


def sha(p):return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()


def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))


def n(v):return f'{v:,}'.replace(',','.')


def pct(a,b):return f'{100*a/b:.1f}'.replace('.',',')+' %'


def short(h):return f'`{h[:12]}…{h[-8:]}`' if h else '—'


def table(head,rows):
    out=['| '+' | '.join(head)+' |','|'+'|'.join('---:' if h.startswith('#') else '---' for h in head)+'|']
    out+=['| '+' | '.join(str(c) for c in r)+' |' for r in rows]
    return '\n'.join(out).replace('| #','| ')


def load():
    p=read(PROTOCOL);d=p['data']
    for key in ['config','manifest']:need(sha(d[key])==d['sha256_bindings'][key],'Protocol data binding differs: '+key)
    m=read(d['manifest']);audit_path=Path(d['manifest']).parent/'record-audit.json'
    need(sha(audit_path)==m['record_audit_sha256'],'Record audit hash differs from manifest')
    audit={r['record_id']:r for r in read(audit_path)}
    for split,s in m['splits'].items():
        acc=[sum(audit[r]['accepted_counts'][c] for r in s['records']) for c in range(5)]
        need(acc==s['counts'] and sum(acc)==s['samples'],'Audit/manifest counts differ: '+split)
    return p,read(d['config']),m,audit,audit_path.as_posix()


def total(audit,records,key):return [sum(audit[r][key][c] for r in records) for c in range(5)]


def render(diff_index=DIFF_INDEX):
    p,config,m,audit,audit_path=load();sp=m['splits']
    ds1=sp['train']['records']+sp['val']['records'];full=sp['test_aux22']['records'];main=sp['test_main']['records']
    out=[f'Nguồn: `{PROTOCOL}` {short(sha(PROTOCOL))}; `{p["data"]["manifest"]}` {short(sha(p["data"]["manifest"]))}; '
         f'`{audit_path}` {short(sha(audit_path))}; `{p["data"]["config"]}` {short(sha(p["data"]["config"]))}.','']

    out+=['### G1. Diff v3 → v4','']
    rows=[]
    for x in read(diff_index):
        rows.append([f'`{x["before"]}`' if x['before'] else '(mới)',f'`{x["after"]}`',short(x['before_raw_sha256']),
                     short(x['after_raw_sha256']),'trùng byte' if x['identical'] else f'`{x["diff"]}`'])
    out+=[table(['Trước (v3)','Sau (v4)','SHA trước','SHA sau','Diff'],rows),'']

    out+=['### G2. Số nhịp theo tập','']
    named=[('Train (DS1 trừ validation)','train'),('Validation','val'),('DS2 chính (bỏ 202)','test_main'),('DS2 đủ 22','test_aux22')]
    rows=[[label,len(sp[k]['records'])]+[n(v) for v in sp[k]['counts']]+[n(sp[k]['samples'])] for label,k in named]
    c1=total(audit,ds1,'accepted_counts')
    rows.insert(2,['DS1 = train + validation',len(ds1)]+[n(v) for v in c1]+[n(sum(c1))])
    out+=[table(['Tập','#Bản ghi']+['#'+c for c in CLASSES]+['#Tổng'],rows),'']

    out+=['### G3. Đối chiếu số đã công bố','']
    drop1=total(audit,ds1,'boundary_dropped_counts');dropf=total(audit,full,'boundary_dropped_counts')
    accf=sp['test_aux22']['counts'];diff=[a-b for a,b in zip(PUBLISHED['DS2_full_counts'],accf)]
    need(sum(c1)+sum(drop1)==PUBLISHED['DS1_total'] and sum(accf)+sum(dropf)==PUBLISHED['DS2_full_total'],'Boundary drops do not explain totals')
    need(diff==dropf,'DS2 per-class gap is not the boundary drop')
    rows=[['DS1 tổng',n(sum(c1)),n(PUBLISHED['DS1_total']),n(PUBLISHED['DS1_total']-sum(c1)),
           ', '.join(f'{v} {c}' for c,v in zip(CLASSES,drop1) if v)]]
    rows+=[[f'DS2 đủ 22 — {c}',n(a),n(b),n(b-a),f'{v} {c}' if v else '0'] for c,a,b,v in zip(CLASSES,accf,PUBLISHED['DS2_full_counts'],dropf)]
    rows.append(['DS2 đủ 22 tổng',n(sum(accf)),n(PUBLISHED['DS2_full_total']),n(PUBLISHED['DS2_full_total']-sum(accf)),
                 ', '.join(f'{v} {c}' for c,v in zip(CLASSES,dropf) if v)])
    out+=[table(['Mục','#Dự án','#Công bố','#Thiếu','Nhịp bỏ ở biên (không đủ cửa sổ 360)'],rows),'',
          'Kiểm bằng code: số dự án + số nhịp bỏ ở biên = số công bố cho DS1 tổng, DS2 đủ tổng và từng lớp của DS2 đủ.','']

    out+=['### G4. Nhịp bỏ ở biên theo bản ghi','']
    rows=[[r,'DS1' if r in ds1 else 'DS2']+audit[r]['boundary_dropped_counts'] for r in sorted(set(ds1+full)) if any(audit[r]['boundary_dropped_counts'])]
    out+=[table(['Bản ghi','Tập']+['#'+c for c in CLASSES],rows),'']

    out+=['### G5. Nhịp S theo bản ghi DS2','']
    s_main=sp['test_main']['counts'][1];s_full=sp['test_aux22']['counts'][1]
    rows=[[r,n(audit[r]['accepted_counts'][1]),pct(audit[r]['accepted_counts'][1],s_main) if r in main else '— (chỉ dòng phụ)',
           pct(audit[r]['accepted_counts'][1],s_full)] for r in sorted(full,key=lambda r:(-audit[r]['accepted_counts'][1],r))
          if audit[r]['accepted_counts'][1]]
    rows.append(['Tổng',n(s_full),f'{n(s_main)} (DS2 chính)',f'{n(s_full)} (DS2 đủ)'])
    out+=[table(['Bản ghi','#S','% S của DS2 chính','% S của DS2 đủ'],rows),'']

    out+=['### G6. Kênh MLII','']
    used=sorted(set(ds1+full));chosen={r:audit[r]['signal_names'][audit[r]['lead_index']] for r in used}
    need(all(v==config['lead'] for v in chosen.values()),'A used record is not read from MLII')
    rows=[[r,', '.join(audit[r]['signal_names']),audit[r]['lead_index'],chosen[r]] for r in used if audit[r]['lead_index']!=0]
    out+=[f'{len(used)}/{len(used)} bản ghi dùng (DS1 + DS2 đủ) lấy kênh tên `{config["lead"]}`. Bản ghi có MLII không ở kênh 0:','',
          table(['Bản ghi','Thứ tự kênh trong header','lead_index','Kênh đã lấy'],rows),'']

    out+=['### G7. Ánh xạ nhãn AAMI dùng trong pipeline','']
    rows=[[c,', '.join(f'`{s}`' for s,t in config['aami_mapping'].items() if t==c)] for c in CLASSES]
    ignored=sum(audit[r]['ignored_annotations'] for r in used)
    out+=[table(['Lớp','Ký hiệu MIT-BIH'],rows),'',
          f'Annotation có ký hiệu nằm ngoài ánh xạ (trường `ignored_annotations` = số annotation trừ số đã ánh xạ) bị bỏ và được đếm: '
          f'{n(ignored)} trên {len(used)} bản ghi dùng.','']

    out+=['### G8. Gán bản ghi và bệnh nhân','']
    groups={k:set(sp[k]['records']) for k in ['train','val','test_main','test_aux22']}
    patients={k:{audit[r]['patient_id'] for r in v} for k,v in groups.items()}
    rows=[[a,b,len(groups[a]&groups[b]),len(patients[a]&patients[b])] for a in ['train','val'] for b in ['test_main','test_aux22']]
    rows.append(['train','val',len(groups['train']&groups['val']),len(patients['train']&patients['val'])])
    out+=[table(['Tập A','Tập B','#Bản ghi chung','#Bệnh nhân chung'],rows),'']
    rows=[[r,audit[r]['patient_id'],', '.join(k for k in groups if r in groups[k]) or '—'] for r in ['201','202']]
    rows+=[[r,audit[r]['patient_id'] if r in audit else '—','bỏ (máy tạo nhịp)'] for r in config['excluded_paced']]
    out+=[table(['Bản ghi','Patient ID','Có trong tập'],rows),'']

    out+=['### G9. Bằng chứng v3 được dẫn (không chạy lại)','']
    sums=dict(reversed(line.split('  ',1)) for line in (ROOT/V3_SUMS).read_text(encoding='utf-8').splitlines() if line)
    rows=[]
    for name,what in EVIDENCE:
        path=f'ml/provenance/m1-v3-20261030/logs/{name}';value=sha(path)
        need(sums.get(path)==value,'v3 evidence hash differs: '+path)
        rows.append([f'`{path}`',short(value),what,(ROOT/path).read_text(encoding='utf-8').strip().splitlines()[-1][:90].replace('|','/')])
    out+=[table(['Log','SHA-256','Nội dung','Dòng cuối'],rows),'']
    return '\n'.join(out)+'\n'


def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--check',type=Path)
    a.add_argument('--diff-index',default=DIFF_INDEX);args=a.parse_args()
    text=render(args.diff_index)
    if args.check is None:sys.stdout.buffer.write(text.encode('utf-8'));return
    doc=args.check.read_text(encoding='utf-8')
    need(doc.count(BEGIN)==1 and doc.count(END)==1,'Generated block markers missing')
    block=doc.split(BEGIN,1)[1].split(END,1)[0]
    need(block.strip('\n')==text.strip('\n'),'Report tables differ from generated tables')
    print('PASS_REPORT_TABLES_MATCH_GENERATED')


if __name__=='__main__':main()
