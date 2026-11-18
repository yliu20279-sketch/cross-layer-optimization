"""Adjacent-layer nonnegative prediction; actual metadata remains authoritative.

Records require previous_counts/current_counts for the SAME token group.
Traffic-only TRANSPORT files do not supply these labels. They cannot train P.
"""
import argparse,json
from pathlib import Path
import numpy as np
def distribution(x):
    x=np.asarray(x,dtype=float)
    if x.ndim!=1 or np.any(~np.isfinite(x)) or np.any(x<0) or x.sum()<=0:
        raise ValueError('expert counts must be a finite, nonnegative, nonempty vector')
    return x/x.sum()
def simplex(x):
    """Euclidean projection of each column onto the probability simplex."""
    out=np.empty_like(x)
    for j in range(x.shape[1]):
        v=x[:,j];u=np.sort(v)[::-1];cs=np.cumsum(u)-1
        k=np.nonzero(u-cs/np.arange(1,len(v)+1)>0)[0][-1]
        out[:,j]=np.maximum(v-cs[k]/(k+1),0)
    return out
def fit(records,iterations=4000,decay=0.98):
    train=[r for r in records if r.get('split')=='train']
    if not train:raise ValueError('no explicitly marked training records')
    ids=[r['sample_id'] for r in train]
    if len(ids)!=len(set(ids)):raise ValueError('duplicate training groups')
    held={r['sample_id'] for r in records if r.get('split')=='heldout'}
    if held.intersection(ids):raise ValueError('training and held-out groups overlap')
    groups={}
    for r in train:groups.setdefault((r['mode'],int(r['layer'])),[]).append(r)
    models={}
    for key,rows in groups.items():
        X=np.stack([distribution(r['previous_counts']) for r in rows])
        Y=np.stack([distribution(r['current_counts']) for r in rows])
        weight=np.array([float(r['tokens'])*decay**(len(rows)-1-i) for i,r in enumerate(rows)])
        if np.any(weight<=0):raise ValueError('nonpositive token-group weight')
        weight/=weight.sum();prior=(Y*weight[:,None]).sum(axis=0)
        P=np.tile(prior[:,None],(1,X.shape[1]));step=1/(2*np.linalg.eigvalsh(X.T@(weight[:,None]*X))[-1]+1e-12)
        for _ in range(iterations):
            grad=2*((X@P.T-Y)*weight[:,None]).T@X
            nxt=simplex(P-step*grad)
            if np.max(np.abs(nxt-P))<1e-10:P=nxt;break
            P=nxt
        assert np.all(P>=0) and np.max(np.abs(P.sum(axis=0)-1))<1e-8
        models[f'{key[0]}:{key[1]}']=dict(P=P.tolist(),prior=prior.tolist(),training_groups=[r['sample_id'] for r in rows],
                                        status='FIT_FROM_PAIRED_EXPERT_COUNTS')
    return dict(models=models,training_sample_ids=ids)
def predict(model,mode,layer,previous_counts=None,historical=None):
    entry=model.get('models',{}).get(f'{mode}:{layer}') if model else None
    if entry and previous_counts is not None:
        x=distribution(previous_counts);P=np.array(entry['P']);return (P@x).tolist(),'adjacent_layer'
    if entry:return distribution(entry['prior']).tolist(),'historical_mean'
    if historical is not None:return distribution(historical).tolist(),'historical_mean'
    raise ValueError('cold-start prediction needs an explicit historical prior')
def selftest():
    rng=np.random.default_rng(113);P=rng.random((8,8));P/=P.sum(axis=0)
    rows=[]
    for i in range(512):
        x=rng.dirichlet(np.ones(8));y=P@x
        rows.append(dict(sample_id=str(i),split='train' if i<384 else 'heldout',mode='prefill',layer=5,
                         tokens=16,previous_counts=(x*16).tolist(),current_counts=(y*16).tolist()))
    model=fit(rows,decay=1)
    error=max(np.max(np.abs(np.array(predict(model,'prefill',5,r['previous_counts'])[0])-distribution(r['current_counts']))) for r in rows[384:])
    assert error<1e-6,error
    assert predict(None,'decode',5,historical=[1,3])[0]==[.25,.75]
    leaked=rows+[dict(rows[0],split='heldout')]
    try:fit(leaked)
    except ValueError:pass
    else:raise AssertionError('leakage was not rejected')
    print('PASS simplex constraints, held-out numerical fit, mode separation, historical fallback, leakage rejection; synthetic data only')
def main():
    p=argparse.ArgumentParser();p.add_argument('--selftest',action='store_true');p.add_argument('--records');p.add_argument('--output');a=p.parse_args()
    if a.selftest:selftest();return
    if not a.records or not a.output:p.error('--records and --output are required')
    data=json.loads(Path(a.records).read_text());Path(a.output).write_text(json.dumps(fit(data),indent=2))
if __name__=='__main__':main()
