#!/usr/bin/env python3
"""Verify saved offline/radio evidence. Device reception and team acceptance stay separate."""
import argparse,json
from pathlib import Path
import numpy as np
from common import load_reference,file_sha,sha,save,seal

def verify(folder):
    folder=Path(folder).resolve()
    for line in (folder/'sha256sum_results.txt').read_text().splitlines():
        digest,name=line.split(maxsplit=1);path=(folder/name.lstrip('* ')).resolve()
        if folder not in path.parents or file_sha(path)!=digest:raise ValueError('Evidence checksum differs: '+name)
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['reference','offline','radio','output']:ap.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args();data=load_reference(a.reference);verify(a.offline);verify(a.radio)
    offline=[json.loads(x) for x in (a.offline/'predictions.jsonl').read_text().splitlines()]
    if len(offline)!=100 or sorted(r['sample_index'] for r in offline)!=list(range(100)):raise ValueError('Offline sample set incomplete')
    by_index={r['sample_index']:r for r in offline}
    mapping={}
    for i in range(100):
        key=(sha(data['q'][i].astype('i1').tobytes()),sha(data['scale_f16'][i].astype('<f4').tobytes()))
        if key in mapping:raise ValueError('Ambiguous q/scale mapping; use sender request mapping')
        mapping[key]=i
    rows=[json.loads(x) for x in (a.radio/'peer.jsonl').read_text().splitlines()]
    counts={};compared=[];failures=[]
    for r in rows:
        i=mapping.get((r.get('q_sha256'),r.get('scale_sha256')))
        rho=r.get('rho')
        if i is None or rho not in ['P0','P1'] or r.get('result')!='OK' or not r.get('response_sent'):
            failures.append({'request_id':r.get('request_id'),'reason':'unmatched/error/unsent','result':r.get('result')});continue
        counts[(i,rho)]=counts.get((i,rho),0)+1
        compared.append({'sample_index':i,'sample_id':str(data['sample_id'][i]),'rho':rho,'request_id':r['request_id'],
            'label':r['label'],'label_ref':int(data['label_ref'][i]),'class_match':r['label']==int(data['label_ref'][i]),
            'label_matches_board_offline':r['label']==by_index[i]['label'],
            'logits_match_board_offline':r['logits_hex_le']==by_index[i]['logits_hex_le']})
    missing=[{'sample_index':i,'rho':rho,'count':counts.get((i,rho),0)} for i in range(100) for rho in ['P0','P1'] if counts.get((i,rho),0)!=1]
    paired_order=(len(compared)==200 and all(
        compared[2*i]['sample_index']==compared[2*i+1]['sample_index']==i
        and {compared[2*i]['rho'],compared[2*i+1]['rho']}=={'P0','P1'}
        for i in range(100)))
    a.output.mkdir(parents=True,exist_ok=False)
    summary={'scope':'EDGE_EVIDENCE_ONLY_DEVICE_RECEPTION_NOT_PROVEN','radio_rows':len(rows),
        'exact_100_pairs':len(rows)==200 and not missing and not failures and paired_order,
        'paired_order':paired_order,'missing_or_duplicate':missing,'failures':failures,
        'reference_label_matches':{rho:sum(r['class_match'] for r in compared if r['rho']==rho) for rho in ['P0','P1']},
        'offline_label_matches':sum(r['label_matches_board_offline'] for r in compared),
        'offline_logits_bit_matches':sum(r['logits_match_board_offline'] for r in compared),
        'device_checker':'PENDING_SV1_CHECKER_AND_CDC_LOG','numeric_review':'PENDING_IF_ANY_LABEL_DIFFERS',
        'g2_acceptance':'PENDING_DEVICE_LOG_LINK_CONFIG_AND_TEAM_REVIEW',
        'sources':{'reference':file_sha(a.reference),'offline':file_sha(a.offline/'sha256sum_results.txt'),'radio':file_sha(a.radio/'sha256sum_results.txt')}}
    save(a.output/'summary.json',summary);save(a.output/'comparison.json',compared);seal(a.output)
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
