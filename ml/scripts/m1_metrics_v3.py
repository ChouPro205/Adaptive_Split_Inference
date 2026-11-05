"""Five-output confusion metrics with pretraining, true-support-fixed validation K."""
import hashlib
import json
import numpy as np

CLASSES=['N','S','V','F','Q']


def need(ok,message):
    if not ok:
        raise ValueError(message)


def labels(values):
    a=np.asarray(values)
    need(a.ndim==1 and len(a)>0 and np.issubdtype(a.dtype,np.integer) and
         bool(((a>=0)&(a<5)).all()),'Expected nonempty five-class integer labels')
    return a


def freeze_validation_policy(y_true):
    y=labels(y_true)
    support=np.bincount(y,minlength=5).tolist()
    k=[0,1,2,3]
    need(all(support[i]>0 for i in k),'Fixed NSVF validation classes must have true support')
    identity={'classes':CLASSES,'validation_support':support,'K_indices':k,
              'K_names':[CLASSES[i] for i in k],'zero_division':0,
              'prediction_space':CLASSES,'q_samples_retained':True,
              'validation_labels_sha256':hashlib.sha256(y.astype('<i8').tobytes()).hexdigest()}
    identity['policy_sha256']=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return identity


def confusion(y_true,y_pred):
    y,p=labels(y_true),labels(y_pred)
    need(y.shape==p.shape,'Prediction/true label shape differs')
    return np.bincount(5*y+p,minlength=25).reshape(5,5)


def all_metrics(y_true,y_pred):
    c=confusion(y_true,y_pred)
    tp=c.diagonal()
    support=c.sum(axis=1)
    predicted=c.sum(axis=0)
    precision=np.divide(tp,predicted,out=np.zeros(5,dtype=float),where=predicted!=0)
    recall=np.divide(tp,support,out=np.zeros(5,dtype=float),where=support!=0)
    denom=support+predicted
    f1=np.divide(2*tp,denom,out=np.zeros(5,dtype=float),where=denom!=0)
    return {'confusion_matrix':c.tolist(),'samples':int(c.sum()),'support':support.tolist(),
            'predicted_counts':predicted.tolist(),'precision':precision.tolist(),
            'recall':recall.tolist(),'f1':f1.tolist(),'accuracy':float(tp.sum()/c.sum())}


def validation_metrics(y_true,y_pred,policy):
    need(policy==freeze_validation_policy(y_true),'Fixed validation K/support/labels policy changed')
    result=all_metrics(y_true,y_pred)
    result['validation_macro_f1_K_fixed']=float(np.mean([result['f1'][i] for i in policy['K_indices']]))
    result['validation_K']=policy['K_names']
    result['metric_policy_sha256']=policy['policy_sha256']
    return result


def ds2_reporting_metrics(y_true,y_pred):
    # Used only with synthetic fixtures in M1; no DS2 model inference is performed.
    result=all_metrics(y_true,y_pred)
    result['macro_f1_NSVF_fixed4']=float(np.mean(result['f1'][:4]))
    result['macro_f1_NSVFQ_fixed5']=float(np.mean(result['f1']))
    return result


def baseline_gates(y_true,y_pred):
    c=confusion(y_true,y_pred)
    support=c.sum(1)
    predicted=c.sum(0)
    tp=c.diagonal()
    n=int(c.sum())
    gates={'N':bool(10*(int(predicted[0])-int(support[0]))<=n),
           'V':bool(support[2]>0 and predicted[2]>0 and 2*tp[2]>=support[2] and 2*tp[2]>=predicted[2]),
           'S':bool(support[1]>0 and predicted[1]>0 and 5*tp[1]>=support[1] and 10*tp[1]>=predicted[1])}
    gates['package_A_gate']=('PASS' if all(gates.values()) else
        'S_ONLY_EXCEPTION_REQUIRES_RECORDED_AUTHORITY' if gates['N'] and gates['V'] else 'BLOCKED')
    return gates
