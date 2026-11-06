#!/usr/bin/env python3
"""Lower the analytical MoE contract to the completion-driven LegoSim CSV ABI."""
from __future__ import annotations
import argparse, csv, json, math
from pathlib import Path

H=2048; TOKEN_BYTES=H*2; TOPK=4; LAYERS=24; SAMPLE_LIMIT=2048
FIELDS=["id","kind","task","phase","pe","bytes","sample_bytes","address","cycles","src","dst","scope","rank"]
MODES=[("FULL_LOCAL",1536,0),("LOCAL_BIAS",1024,512),("GLOBAL_BIAS",512,1024),("FULL_GLOBAL",0,1536)]

def write(path, rows, fields=None):
    rows=list(rows); fields=fields or list(rows[0])
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(rows)

def build(out:Path, mode:str, remote_rate:float, tokens:int):
    out.mkdir(parents=True,exist_ok=True); ops=[]; deps=[]; tails={}
    def op(kind,task,phase,pe,bytes_=0,cycles=0,src=-1,dst=-1,scope="local",rank=0,address=0):
        i=len(ops); sample=min(bytes_,SAMPLE_LIMIT) if kind in ("LOAD","STORE") else 0
        ops.append(dict(id=i,kind=kind,task=task,phase=phase,pe=pe,bytes=int(bytes_),sample_bytes=int(sample),
                        address=int(address),cycles=max(0,int(cycles)),src=src,dst=dst,scope=scope,rank=rank)); return i
    def dep(a,b): deps.append({"src":a,"dst":b})
    for layer in range(LAYERS):
        stage=layer//6; pes=list(range(stage*4,stage*4+4)); layer_tails=[]
        for rank,pe in enumerate(pes):
            # The coupled runtime owns one Ramulator instance per PE, so the
            # address passed to that instance is partition-local (0..512 MiB).
            base=(layer%6)*64*1024*1024
            weight_bytes=48*1024*1024  # representative resident shard service, not serialized checkpoint size
            load=op("LOAD",f"L{layer}_weights",mode,pe,weight_bytes,address=base,rank=rank)
            if pe in tails: dep(tails[pe],load)
            attn=op("COMPUTE",f"L{layer}_attention","COMPUTE",pe,cycles=max(1,tokens*4096),rank=rank); dep(load,attn)
            router=op("COMPUTE",f"L{layer}_router","COMPUTE",pe,cycles=max(1,tokens*60),rank=rank); dep(attn,router)
            remote_activations=math.ceil(tokens*TOPK*remote_rate/4)
            # One deterministic peer per rank represents the aggregate remote all-to-all payload.
            peer=pes[(rank+1)%4]; net_bytes=remote_activations*TOKEN_BYTES
            dispatch=op("NET",f"L{layer}_expert_dispatch",mode,pe,net_bytes,src=pe,dst=peer,scope="global",rank=rank); dep(router,dispatch)
            expert=op("COMPUTE",f"L{layer}_routed_shared_experts","COMPUTE",pe,
                      cycles=max(1,tokens*(TOPK*3*2048*1408+3*2048*5632)//(256*256)),rank=rank); dep(dispatch,expert)
            combine=op("NET",f"L{layer}_expert_combine",mode,pe,net_bytes,src=peer,dst=pe,scope="global",rank=rank); dep(expert,combine)
            kv=op("STORE",f"L{layer}_kv_append",mode,pe,tokens*2*128*2,address=base+56*1024*1024,rank=rank); dep(combine,kv)
            tails[pe]=kv; layer_tails.append(kv)
        if layer%6==5 and layer<LAYERS-1:
            next_pes=list(range((stage+1)*4,(stage+2)*4))
            for rank,(src,dst) in enumerate(zip(pes,next_pes)):
                x=op("NET",f"L{layer}_pipeline",mode,src,tokens*TOKEN_BYTES,src=src,dst=dst,scope="global",rank=rank)
                dep(tails[src],x); tails[dst]=x
    barrier=op("BARRIER","finish",mode,0)
    for t in sorted(set(tails.values())): dep(t,barrier)
    write(out/"ops.csv",ops,FIELDS); write(out/"deps.csv",deps,["src","dst"])
    write(out/"modes.csv",({"mode":m,"local_bytes_per_cycle":l,"global_bytes_per_cycle":g} for m,l,g in MODES),
          ["mode","local_bytes_per_cycle","global_bytes_per_cycle"])
    manifest={"schema_version":"qwen1.5-moe-legosim-lowering-1.0","mode":mode,"tokens":tokens,
              "remote_activation_rate":remote_rate,"operations":len(ops),"dependencies":len(deps),
              "sample_limit_bytes_per_memory_op":SAMPLE_LIMIT,
              "limitations":["Compute cycles are analytical placeholders, not NPUSim measurements.",
                             "One peer aggregates each rank's all-to-all traffic; bytes are preserved but packet destinations are sampled.",
                             "Weight loads model service demand and do not replay checkpoint allocation addresses."]}
    (out/"graph_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    return manifest

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--metrics",type=Path,required=True); ap.add_argument("--out",type=Path,required=True); ap.add_argument("--tokens",type=int,default=32); a=ap.parse_args()
    m=json.loads(a.metrics.read_text()); rates={"ep_baseline":m["baseline"]["remote_activation_rate"],"hiband_only":m["baseline"]["remote_activation_rate"],"hiband_sem_moe":m["sem_moe"]["remote_activation_rate"]}
    result={name:build(a.out/name,name,rate,a.tokens) for name,rate in rates.items()}; print(json.dumps(result,indent=2))
if __name__=="__main__": main()
