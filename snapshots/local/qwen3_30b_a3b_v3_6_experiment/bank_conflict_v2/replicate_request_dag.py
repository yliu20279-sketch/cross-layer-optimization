#!/usr/bin/env python3
import argparse,csv,hashlib,json,shutil
from pathlib import Path

def read(p):
    with p.open(newline="") as h:return list(csv.DictReader(h))
def write(p,rs):
    with p.open("w",newline="") as h:
        w=csv.DictWriter(h,fieldnames=rs[0].keys());w.writeheader();w.writerows(rs)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--input",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);ap.add_argument("--copies",type=int,required=True);a=ap.parse_args()
    if a.copies<2:raise ValueError("copies must be >=2")
    if a.output.exists():raise FileExistsError(a.output)
    a.output.mkdir(parents=True)
    for p in a.input.iterdir():
        if p.is_file() and p.name not in ("ops.csv","deps.csv","address_manifest.csv","graph_manifest.json","memory_stress_manifest.json"):
            shutil.copy2(p,a.output/p.name)
    ops=read(a.input/"ops.csv");deps=read(a.input/"deps.csv");addr=read(a.input/"address_manifest.csv");n=len(ops)
    owners=[int(r["inference_request_id"]) for r in ops if int(r["inference_request_id"])>=0];base_batch=max(owners)+1
    out_ops=[];out_deps=[];out_addr=[]
    for copy in range(a.copies):
        off=copy*n;owner_off=copy*base_batch
        for r0 in ops:
            r=dict(r0);r["id"]=str(int(r["id"])+off);r["task"]=f"C{copy}_"+r["task"]
            if int(r["inference_request_id"])>=0:r["inference_request_id"]=str(int(r["inference_request_id"])+owner_off)
            out_ops.append(r)
        for d0 in deps:
            d=dict(d0);d["src"]=str(int(d["src"])+off);d["dst"]=str(int(d["dst"])+off);out_deps.append(d)
        for x0 in addr:
            x=dict(x0);x["op_id"]=str(int(x["op_id"])+off)
            if int(x["inference_request_id"])>=0:x["inference_request_id"]=str(int(x["inference_request_id"])+owner_off)
            out_addr.append(x)
    write(a.output/"ops.csv",out_ops);write(a.output/"deps.csv",out_deps);write(a.output/"address_manifest.csv",out_addr)
    g=json.loads((a.input/"graph_manifest.json").read_text());pages=[]
    for copy in range(a.copies):
        off=copy*n
        for p0 in g.get("page_operations",[]):
            p=dict(p0)
            for k in ("fetch","evict","commit"):p[k]=int(p[k])+off
            pages.append(p)
    for k in ("operations","dependencies","batch","microbatches","hits","misses","evictions"):
        if isinstance(g.get(k),int):g[k]*=a.copies
    g["page_operations"]=pages;g["request_ids"]=[f"copy{c}:{x}" for c in range(a.copies) for x in g.get("request_ids",[])]
    g["inference_request_id_map"]={f"copy{c}:{k}":int(v)+c*base_batch for c in range(a.copies) for k,v in g.get("inference_request_id_map",{}).items()}
    g["replay_concurrency"]={"copies":a.copies,"base_batch":base_batch,"effective_batch":base_batch*a.copies,"classification":"synthetic replay-expanded concurrency","routes_addresses_and_per_request_dependencies_unchanged":True}
    g.setdefault("limitations",[]).append(f"synthetic replay-expanded concurrency: {a.copies} copies of the same {base_batch}-request cohort")
    (a.output/"graph_manifest.json").write_text(json.dumps(g,indent=2)+"\n")
    report={"status":"PASS","copies":a.copies,"base_batch":base_batch,"effective_batch":base_batch*a.copies,"operations":len(out_ops),"dependencies":len(out_deps),"source_ops_sha256":sha(a.input/"ops.csv"),"output_ops_sha256":sha(a.output/"ops.csv")}
    (a.output/"replay_manifest.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report,indent=2))
if __name__=="__main__":main()
