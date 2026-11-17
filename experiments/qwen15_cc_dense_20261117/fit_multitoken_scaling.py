"""Extrapolate the wall time and target layer time from measured prefixes."""

import json
from pathlib import Path
import sys


def predict(a,b,x,y,z):
    return b+(z-y)*(b-a)/(y-x)


def fit(folder,seed,small,large,target):
    runs = [folder/f'fit{tokens}_{seed}' for tokens in (small,large)]
    short,long = [json.loads((run/'RESULT.json').read_text()) for run in runs]
    assert short['status']==long['status']=='PASS_MULTITOKEN_FIT_SAMPLE'
    assert short['tokens']==small and long['tokens']==large and short['seed']==long['seed']==seed
    assert short['binary_sha256']==long['binary_sha256']
    a,b = [run.joinpath('L5_INPUT.bin').read_bytes() for run in runs]
    assert len(a)==small*4096 and len(b)==large*4096 and a==b[:len(a)]
    qk = [run['attention_qk_pv_ns'] for run in (short,long)]
    residual = [run['attention_ns']-run['attention_qk_pv_ns'] for run in (short,long)]
    assert all(t>0 for t in qk+residual)
    quadratic = predict(*qk,small**2,large**2,target**2)
    attention = max(quadratic,qk[1])+max(predict(*residual,small,large,target),residual[1])
    moe = max(predict(short['moe_ns'],long['moe_ns'],small,large,target),long['moe_ns'])
    wall_ratios = [run['execution_wall_seconds']/run['layer_ns'] for run in (short,long)]
    layer = attention+moe
    return dict(seed=seed,tokens=target,measured=[short,long],estimated_layer_ns=round(layer),
                estimated_moe_ns=round(moe),estimated_attention_ns=round(attention),
                indicative_wall_seconds=[round(layer*min(wall_ratios)),round(layer*max(wall_ratios))],
                scope='Extrapolated operator and layer time. Wall endpoints use the two observed simulator rates, '
                      'not a confidence interval. Circuit gain and full-scale communication contention are unmeasured.')


if __name__=='__main__':
    folder=Path(sys.argv[1]).resolve()
    seed,small,large,target=map(int,sys.argv[2:])
    result=fit(folder,seed,small,large,target)
    path=folder/f'ESTIMATE_{target}_{seed}.json'
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(result,indent=2)+'\n')
    temp.replace(path)
    print(json.dumps(result))
