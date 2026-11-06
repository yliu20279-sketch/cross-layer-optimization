"""Measured expert heat and frozen nested cohorts; no performance claim."""
import argparse,csv,gzip,json
from collections import Counter,defaultdict
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True); args=ap.parse_args(); root=args.root
    output=root/'results/route_characterization'; output.mkdir(exist_ok=True)
    heat=[]; score={}; manifests={}
    for context in (128,512):
        p=root/f'results/routes_context{context}'; m=json.loads((p/'trace_manifest.json').read_text()); manifests[context]=m
        counts=defaultdict(Counter)
        with gzip.open(p/'routing_trace.csv.gz','rt',newline='') as f:
            for r in csv.DictReader(f): counts[r['split'],r['request_id'],int(r['layer'])][int(r['expert'])]+=1
        for split in ('profile','eval'):
            agg=defaultdict(Counter)
            for (s,req,layer),c in counts.items():
                if s==split: agg[layer].update(c)
            for layer,c in agg.items():
                total=sum(c.values())
                for expert in range(128): heat.append(dict(context=context,split=split,layer=layer,expert=expert,activations=c[expert],activation_share=c[expert]/total))
        for record in m['records'][m['profile_requests']:]:
            req=record['request_id']; shares=[max(counts['eval',req,l].values())/sum(counts['eval',req,l].values()) for l in range(48)]
            score.setdefault(req,[]).append(sum(shares)/48)
    ids=[r['request_id'] for r in manifests[128]['records'][20:]]
    ranked=sorted(ids,key=lambda r:(-sum(score[r])/2,r))
    cohorts=[]
    for policy,ordered in [('fixed_source_order',ids),('exploratory_high_skew',ranked),('exploratory_low_skew',list(reversed(ranked)))]:
        for repeat in range(5):
            group=ordered[repeat*16:(repeat+1)*16]
            for scale in (1,2,4,8,16): cohorts.append(dict(policy=policy,repeat=repeat+1,scale=scale,request_ids=group[:scale]))
    with (output/'expert_heat.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(heat[0]));w.writeheader();w.writerows(heat)
    payload={'status':'PASS','cohorts':cohorts,'request_skew_score':{r:sum(v)/2 for r,v in score.items()},'limitations':['same source records but different continuation tokens across contexts','high-skew cohorts selected from eval routes are exploratory, not a held-out confirmatory test','activation share is not Bank access share or latency']}
    (output/'cohort_manifest.json').write_text(json.dumps(payload,indent=2)+'\n')
    print(json.dumps({'status':'PASS','heat_rows':len(heat),'cohorts':len(cohorts),'skew_min':min(payload['request_skew_score'].values()),'skew_max':max(payload['request_skew_score'].values())},indent=2))
if __name__=='__main__': main()
