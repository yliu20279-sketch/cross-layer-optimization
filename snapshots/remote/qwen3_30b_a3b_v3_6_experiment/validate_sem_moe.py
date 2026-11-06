"""Independent structural and metric audit of Sem-MoE reproduction outputs."""
import argparse,csv,gzip,json
from collections import Counter,defaultdict
from pathlib import Path
LAYERS,EXPERTS,EP=48,128,16
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--context',type=int,required=True);ap.add_argument('--result',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    manifest=json.loads((a.root/f'results/routes_context{a.context}/trace_manifest.json').read_text());ids=[r['request_id'] for r in manifest['records']]
    profile=set(ids[:20]);evaluation=set(ids[20:]);assert profile.isdisjoint(evaluation) and len(profile)==20 and len(evaluation)==80
    placement=json.loads((a.result/'placement.json').read_text());claimed=json.loads((a.result/'metrics.json').read_text())
    assert set(map(int,placement))==set(range(LAYERS));seen_profile=set();counts=defaultdict(lambda:defaultdict(Counter))
    for layer in range(LAYERS):
        er={int(k):int(v) for k,v in placement[str(layer)]['expert_to_rank'].items()}
        assert set(er)==set(range(EXPERTS)) and Counter(er.values())==Counter({r:8 for r in range(EP)})
        pr=placement[str(layer)]['profile_request_to_rank'];assert set(pr)==profile;seen_profile|=set(pr);assert max(Counter(pr.values()).values())<=2
    with gzip.open(a.root/f'results/routes_context{a.context}/routing_trace.csv.gz','rt',newline='') as f:
        for r in csv.DictReader(f):
            if r['request_id'] in evaluation:counts[int(r['layer'])][r['request_id']][int(r['expert'])]+=1
    total=local=base_local=0
    for layer in range(LAYERS):
        assert set(counts[layer])==evaluation
        er={int(k):int(v) for k,v in placement[str(layer)]['expert_to_rank'].items()}
        for mapping,isbase in ((er,False),({e:e%EP for e in range(EXPERTS)},True)):
            loads=[0]*EP;rr={}
            for q in sorted(counts[layer],key=lambda q:(-sum(counts[layer][q].values()),q)):
                choices=[r for r in range(EP) if loads[r]<5]
                rank=max(choices,key=lambda r:(sum(v for e,v in counts[layer][q].items() if mapping[e]==r),-loads[r],-r));rr[q]=rank;loads[rank]+=1
            val=sum(v for q,c in counts[layer].items() for e,v in c.items() if mapping[e]==rr[q])
            if isbase:base_local+=val
            else:local+=val
        total+=sum(sum(c.values()) for c in counts[layer].values())
    base_remote=total-base_local;remote=total-local;reduction=1-remote/base_remote
    assert total==claimed['sem_moe_reproduction']['activations'];assert local==claimed['sem_moe_reproduction']['local'];assert base_local==claimed['baseline']['local'];assert abs(reduction-claimed['remote_reduction'])<1e-12
    report={'status':'PASS','context':a.context,'checks':['20/80 source-disjoint split','48 layers and 128 experts complete','exactly eight experts per rank per layer','profile request assignment contains no eval IDs','eval metric independently recomputed from raw trace','reported remote reduction exactly reproduced'],'eval_activations':total,'baseline_remote':base_remote,'sem_moe_remote':remote,'remote_reduction':reduction,'claim_scope':'communication-locality proxy only; not latency or official-code equivalence'}
    a.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
