"""Short read-only dCor/NoPeek demo; no optimizer, checkpoint output or privacy claim."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ml/src'))
import torch
from distance_correlation import distance_correlation
from nopeek import nopeek_loss
from nopeek_data import load_train_val
from week5_common_v2 import baseline, PACKAGE
from week3_sv2_common import wrappers
from review_week7_sv2 import need, write, sha, CHECKPOINT
from run_week7_nopeek import state_digest


def demo(package=PACKAGE):
    model,_=baseline(package)
    before=state_digest(model)
    torch.manual_seed(7)
    x=torch.randn(1024,1,dtype=torch.float64)
    y=torch.randn(1024,1,dtype=torch.float64)
    cases={'self':float(distance_correlation(x,x)),
           'independent_1d_n1024':float(distance_correlation(x,y)),
           'nonlinear_square':float(distance_correlation(x,x.square())),
           'constant':float(distance_correlation(x,torch.ones_like(x)))}
    need(abs(cases['self']-1)<1e-12 and cases['constant']==0,'Self/degenerate demo failed')
    checkpoint=torch.load(package/'model/checkpoint.pt',map_location='cpu',weights_only=True)
    _,_,arrays,metadata=load_train_val(checkpoint)
    inputs=torch.from_numpy(arrays['train'][0][:32].copy())
    labels=torch.from_numpy(arrays['train'][1][:32].copy())
    rows=[]
    def norm(gs):return float(torch.sqrt(sum((g*g).sum() for g in gs)))
    for s in (2,5,8):
        head,tail=wrappers(model,s)
        z=head(inputs)
        out=tail(z)
        zero,parts0=nopeek_loss(out,labels,inputs,z,0)
        loss,parts=nopeek_loss(out,labels,inputs,z,0.5)
        params=tuple(head.parameters())
        g_total=torch.autograd.grad(loss,params,retain_graph=True)
        g_ce=torch.autograd.grad(parts['ce'],params,retain_graph=True)
        g_dcor=torch.autograd.grad(parts['dcor'],params)
        maximum=max(float((a-b-0.5*c).abs().max()) for a,b,c in zip(g_total,g_ce,g_dcor))
        for a,b,c in zip(g_total,g_ce,g_dcor):
            torch.testing.assert_close(a-b,0.5*c,atol=1e-6,rtol=1e-4)
        need(z.shape[0]==32 and norm(g_dcor)>0 and torch.equal(zero,parts['ce']), 'Gradient/lambda0 failed')
        rows.append({'s':s,'CE':float(parts['ce'].detach()),'dCor':float(parts['dcor'].detach()),
                     'lambda':0.5,'total':float(loss.detach()), 'lambda0_is_CE_tensor':zero is parts0['ce'],
                     'CE_head_gradient_l2':norm(g_ce),'dCor_head_gradient_l2':norm(g_dcor),
                     'max_abs_gradient_identity_residual':maximum})
    need(before==state_digest(model),'Demo changed model weights')
    return {'status':'PASS_DEMO_COMMAND_ONLY','checkpoint_sha256':CHECKPOINT,
            'script_sha256':sha(__file__), 'dcor_cases':cases,'real_train_batch_samples':32,
            'sample_ids':metadata['train'].sample_id.iloc[:32].tolist(), 'splits':rows,
            'weights_unchanged':True, 'human_learning_or_GVHD_demo':'NOT_ATTESTED',
            'privacy':'NOT_EVALUATED; finite-batch biased dCor/wiring does not prove attack resistance'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-package',type=Path,default=PACKAGE)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    need(not a.output.exists(),'Refuse to overwrite demo evidence')
    result=demo(a.model_package)
    write(a.output,result)
    print(result['dcor_cases'])
    for row in result['splits']:print(row)
