"""Profile-only Sem-MoE-style expert/request co-placement for Qwen3-MoE.

This implements the published alternating affinity/swap structure from the
paper pseudocode. It is a reproduction, not official author code equivalence.
"""
import argparse,csv,gzip,json,random
from collections import Counter,defaultdict
from pathlib import Path

LAYERS,EXPERTS,EP=48,128,16
def read_ids(root,context):
    m=json.loads((root/f'results/routes_context{context}/trace_manifest.json').read_text())
    ids=[x['request_id'] for x in m['records']];assert len(ids)==100 and len(set(ids))==100
    return set(ids[:20]),set(ids[20:])
def load(root,context,allowed):
    data=defaultdict(lambda:defaultdict(Counter))
    path=root/f'results/routes_context{context}/routing_trace.csv.gz'
    with gzip.open(path,'rt',newline='') as f:
        for r in csv.DictReader(f):
            q=r['request_id']
            if q in allowed:data[int(r['layer'])][q][int(r['expert'])]+=1
    assert set(q for layer in data.values() for q in layer)==allowed
    return data
def balanced_requests(reqs,expert_rank,capacity):
    loads=[0]*EP;out={}
    for q in sorted(reqs,key=lambda q:(-sum(reqs[q].values()),q)):
        score=[]
        for rank in range(EP):
            local=sum(v for e,v in reqs[q].items() if expert_rank[e]==rank)
            score.append((local,-loads[rank],-rank))
        choices=[r for r in range(EP) if loads[r]<capacity]
        r=max(choices,key=lambda x:score[x]);out[q]=r;loads[r]+=1
    return out
def objective(reqs,expert_rank,request_rank):
    return sum(v for q,c in reqs.items() for e,v in c.items() if expert_rank[e]==request_rank[q])
def layer_place(reqs,seed,restarts=4,max_passes=12):
    rng=random.Random(seed);cap=EXPERTS//EP
    experts=list(range(EXPERTS));rng.shuffle(experts)
    best_er=None;best_rr=None;best=-1;accepted=0;passes=0
    for restart in range(restarts):
        if restart: rng.shuffle(experts)
        er={e:i//cap for i,e in enumerate(experts)}
        rr=balanced_requests(reqs,er,(len(reqs)+EP-1)//EP)
        for _ in range(max_passes):
            passes+=1;improved=False
            score=[[0]*EP for _ in range(EXPERTS)]
            for q,counts in reqs.items():
                for e,v in counts.items():score[e][rr[q]]+=v
            order=list(range(EXPERTS));rng.shuffle(order)
            for i,a in enumerate(order):
                for b in order[i+1:]:
                    if er[a]==er[b]:continue
                    ra,rb=er[a],er[b]
                    before=score[a][ra]+score[b][rb];after=score[a][rb]+score[b][ra]
                    if after>before:
                        er[a],er[b]=er[b],er[a];accepted+=1;improved=True
            rr=balanced_requests(reqs,er,(len(reqs)+EP-1)//EP)
            if not improved:break
        val=objective(reqs,er,rr)
        if val>best:best_er,best_rr,best=dict(er),dict(rr),val
    assert Counter(best_er.values())==Counter({r:cap for r in range(EP)})
    return best_er,best_rr,best,accepted,passes
def evaluate(data,placements):
    total=local=0;bylayer={}
    for layer in range(LAYERS):
        reqs=data[layer];er=placements[str(layer)]['expert_to_rank'];rr=balanced_requests(reqs,{int(k):v for k,v in er.items()},(len(reqs)+EP-1)//EP)
        t=sum(sum(c.values()) for c in reqs.values());l=objective(reqs,{int(k):v for k,v in er.items()},rr)
        bylayer[str(layer)]={'total':t,'local':l,'request_counts_by_rank':dict(Counter(rr.values()))};total+=t;local+=l
    return {'activations':total,'local':local,'remote':total-local,'local_rate':local/total,'remote_rate':(total-local)/total,'by_layer':bylayer}
def baseline(data):
    total=local=0
    for reqs in data.values():
        rr=balanced_requests(reqs,{e:e%EP for e in range(EXPERTS)},(len(reqs)+EP-1)//EP)
        total+=sum(sum(c.values()) for c in reqs.values());local+=objective(reqs,{e:e%EP for e in range(EXPERTS)},rr)
    return {'activations':total,'local':local,'remote':total-local,'local_rate':local/total,'remote_rate':(total-local)/total}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--context',type=int,default=128);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    profile_ids,eval_ids=read_ids(a.root,a.context);profile=load(a.root,a.context,profile_ids);evaluation=load(a.root,a.context,eval_ids)
    placements={}
    for layer in range(LAYERS):
        er,rr,obj,accepted,passes=layer_place(profile[layer],20260916+layer)
        placements[str(layer)]={'expert_to_rank':{str(k):v for k,v in sorted(er.items())},'profile_request_to_rank':rr,'profile_local_objective':obj,'accepted_swaps':accepted,'search_passes':passes}
    sem=evaluate(evaluation,placements);base=baseline(evaluation)
    result={'status':'REPRODUCTION_READY','context':a.context,'algorithm':'balanced alternating request assignment and cross-rank expert swaps','profile_requests':len(profile_ids),'eval_requests':len(eval_ids),'baseline':base,'sem_moe_reproduction':sem,'remote_reduction':1-sem['remote']/base['remote'],'limitations':['reproduction of published pseudocode; not verified as official-code equivalent','request balancing uses ceil capacity because 20 profile requests are not divisible by EP16','evaluation request placement is inferred independently per layer from expert affinity; online 2-gram scheduling is not implemented','routing trace is teacher-forced measured routing, not generated serving traffic','no latency claim until LegoSim replay and controls pass']}
    a.out.mkdir(parents=True,exist_ok=True);(a.out/'placement.json').write_text(json.dumps(placements,indent=2)+'\n');(a.out/'metrics.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('baseline','sem_moe_reproduction')},indent=2))
if __name__=='__main__':main()
