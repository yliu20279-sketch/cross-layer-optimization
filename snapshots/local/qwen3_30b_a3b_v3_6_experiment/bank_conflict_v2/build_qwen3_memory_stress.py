#!/usr/bin/env python3
import argparse, csv, hashlib, json, math, re, shutil
from collections import defaultdict, deque
from pathlib import Path

EXPERT_MEM = re.compile(r"^S\d+L(?P<layer>\d+)W\d+E(?P<expert>\d+)_(?P<stage>victim_read|commit|weight_read)$")

def rows(path):
    with path.open(newline="") as h:return list(csv.DictReader(h))

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--input",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);ap.add_argument("--lanes",type=int,default=4);ap.add_argument("--compute-multiplier",type=float,default=.25);a=ap.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    if a.lanes<0 or not 0<a.compute_multiplier<=1:raise ValueError("invalid stress controls")
    shutil.copytree(a.input,a.output)
    ops=rows(a.input/"ops.csv");old_edges=rows(a.input/"deps.csv");edges={(int(r["src"]),int(r["dst"])) for r in old_edges}
    groups=defaultdict(list);old_cycles=new_cycles=0;compute_ops=0;memory_ops=0
    for r in ops:
        if r["kind"]=="COMPUTE":
            compute_ops+=1;old=int(r["cycles"]);new=max(1,math.ceil(old*a.compute_multiplier));r["cycles"]=str(new);old_cycles+=old;new_cycles+=new
        if r["kind"] not in ("LOAD","STORE"):continue
        memory_ops+=1;m=EXPERT_MEM.match(r["task"])
        if not m or a.lanes==0:continue
        expert=int(m.group("expert"));key=(int(r["inference_request_id"]),int(m.group("layer")),int(r["pe"]),m.group("stage"),expert%a.lanes)
        groups[key].append((expert,int(r["id"])))
    added=0
    for values in groups.values():
        ids=[i for _,i in sorted(values)]
        for s,d in zip(ids,ids[1:]):
            if (s,d) not in edges:edges.add((s,d));added+=1
    indeg={int(r["id"]):0 for r in ops};children=defaultdict(list)
    for s,d in edges:indeg[d]+=1;children[s].append(d)
    q=deque(i for i,v in indeg.items() if v==0);seen=0
    while q:
        x=q.popleft();seen+=1
        for y in children[x]:
            indeg[y]-=1
            if indeg[y]==0:q.append(y)
    if seen!=len(ops):raise RuntimeError(f"cycle introduced: {seen}/{len(ops)}")
    with (a.output/"ops.csv").open("w",newline="") as h:
        w=csv.DictWriter(h,fieldnames=ops[0].keys());w.writeheader();w.writerows(ops)
    with (a.output/"deps.csv").open("w",newline="") as h:
        w=csv.writer(h);w.writerow(("src","dst"));w.writerows(sorted(edges))
    manifest=json.loads((a.output/"graph_manifest.json").read_text())
    manifest["memory_stress"]={"label":"Qwen3-30B-A3B controlled memory stress","expert_memory_lanes_per_request":a.lanes,"compute_cycle_multiplier":a.compute_multiplier,"full_memory_trace_preserved":manifest.get("full_memory_trace") is True,"sample_bytes_unchanged":True,"represented_bytes_unchanged":True,"addresses_unchanged":True,"routing_unchanged":True,"placement_unchanged":True,"original_compute_cycles":old_cycles,"stress_compute_cycles":new_cycles,"added_serialization_edges":added}
    lane_note=(f"{a.lanes} expert-memory lanes" if a.lanes else "no expert-memory lane serialization")
    manifest.setdefault("limitations",[]).append(f"synthetic memory-stress transform: {lane_note} and {a.compute_multiplier}x compute; not a natural serving workload")
    (a.output/"graph_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    report={"status":"PASS","source":str(a.input),"destination":str(a.output),"operations":len(ops),"memory_operations":memory_ops,"compute_operations":compute_ops,"original_edges":len(old_edges),"final_edges":len(edges),"added_serialization_edges":added,"dag_nodes_visited":seen,"lanes":a.lanes,"compute_multiplier":a.compute_multiplier,"full_memory_trace_preserved":manifest.get("full_memory_trace") is True,"source_ops_sha256":sha(a.input/"ops.csv"),"output_ops_sha256":sha(a.output/"ops.csv"),"source_deps_sha256":sha(a.input/"deps.csv"),"output_deps_sha256":sha(a.output/"deps.csv")}
    (a.output/"memory_stress_manifest.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report,indent=2))
if __name__=="__main__":main()
