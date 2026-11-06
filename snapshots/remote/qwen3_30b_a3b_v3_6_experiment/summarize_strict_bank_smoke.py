#!/usr/bin/env python3
import argparse,csv,json,math
from collections import Counter
from pathlib import Path

SCHEMES=("baseline_ep","hiband","sem_moe","hiband_sem_moe")

def gini(values):
    x=sorted(v for v in values if v>=0)
    if not x or sum(x)==0:return 0.0
    n=len(x)
    return (2*sum((i+1)*v for i,v in enumerate(x))/(n*sum(x)))-(n+1)/n

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--root",type=Path,required=True);ap.add_argument("--out",type=Path,required=True);a=ap.parse_args()
    report={"schema":"strict-bank-smoke-summary-v1","status":"PASS","cases":{},"claim_boundary":"request-wait diagnostic, not conserved wall-clock attribution"}
    for s in SCHEMES:
        p=a.root/s;v=json.loads((p/"validation.json").read_text()); waits=Counter(); reqs=Counter(); rows=0; nonzero=0
        with (p/"bank_requests.csv").open(newline="") as f:
            for r in csv.DictReader(f):
                rows+=1;w=int(r["cross_request_bank_wait_ticks"]);nonzero+=w>0
                bank=(int(r["partition"]),int(r["channel"]),int(r["rank"]),int(r["bankgroup"]),int(r["bank"]))
                waits[bank]+=w;reqs[bank]+=1
        total=sum(waits.values()); ranked=waits.most_common()
        report["cases"][s]={"total_cycles":v["total_cycles"],"transactions":rows,"nonzero_transactions":nonzero,"strict_wait_ticks":total,"strict_wait_per_transaction":total/rows,"active_banks":sum(x>0 for x in waits.values()),"bank_wait_gini":gini(list(waits.values())),"top8_bank_wait":[{"bank":list(k),"ticks":x,"share":x/total if total else 0} for k,x in ranked[:8]],"top8_share":sum(x for _,x in ranked[:8])/total if total else 0}
    b=report["cases"]["baseline_ep"]["strict_wait_ticks"]
    for s in SCHEMES:
        report["cases"][s]["strict_wait_reduction_vs_baseline"]=1-report["cases"][s]["strict_wait_ticks"]/b if b else None
    a.out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n");print(json.dumps(report,indent=2,sort_keys=True))
if __name__=="__main__":main()
