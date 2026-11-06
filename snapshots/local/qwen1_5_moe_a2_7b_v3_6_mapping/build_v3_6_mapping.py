#!/usr/bin/env python3
"""Regenerate Qwen1.5-MoE graphs and map them to the 8 GiB V3.6 target."""
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
SRC=HERE.parent/"qwen1_5_moe_a2_7b_v3_5_mapping"/"build_moe_graph.py"
spec=importlib.util.spec_from_file_location("moe_base",SRC); base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
PART=512*2**20; RESERVE=32*2**20

def placement():
    # Layer-specific placement balances 24*60=1440 entries exactly: 90 per cluster.
    rows=[]; counts={f"N{i}":0 for i in range(16)}
    for layer in range(base.LAYERS):
        for expert in range(base.EXPERTS):
            cluster=f"N{(layer*base.EXPERTS+expert)%16}"; counts[cluster]+=1
            rows.append({"layer":layer,"expert":expert,"cluster":cluster,"partition":"CH"+cluster[1:]})
    return rows,counts

def capacity(context,counts):
    p=base.params(); expert_one=p["expert_one"]; nonexpert_layer=p["layer"]-p["experts"]
    head=2*(base.VOCAB*base.H//base.TP//2)
    nonexpert=base.LAYERS*(nonexpert_layer//base.TP//2)
    kv=base.LAYERS*context*2*base.D*base.B
    expert=90*(expert_one//2); occupied=head+nonexpert+kv+expert+RESERVE
    return {"schema":"qwen1.5-moe-v3.6-capacity-1.0","total_parameters_formula":p["total"],"active_parameters_per_token_formula":p["active"],"capacity_bytes_total":16*PART,"capacity_bytes_per_partition":PART,"ideal_all_weight_int4_bytes":(p["total"]+1)//2,"kv_cache_bytes_global":base.LAYERS*context*2*base.HEADS*base.D*base.B,"placement":"layer_expert_cyclic_balanced","expert_entries_per_partition":counts,"per_partition":{"embedding_and_lm_W4_bytes":head,"nonexpert_W4_bytes":nonexpert,"expert_W4_bytes":expert,"kv_cache_bytes":kv,"combined_metadata_runtime_reserve_bytes":RESERVE,"occupied_bytes":occupied,"headroom_bytes":PART-occupied},"status":"STATIC_IDEAL_W4_FITS_CONDITIONALLY","condition":"The 32 MiB reserve must cover serialized quantization metadata, activation/DMA buffers and allocator overhead; no execution is claimed."}

def snapshot(out):
    arch=HERE.parent/"whisper_operator_inventory"/"target_architecture_v3_6"; prov=json.loads((arch/"PROVENANCE_V3_6.json").read_text(encoding="utf-8")); files=[]
    for p in sorted(arch.iterdir()):
        if p.is_file() and p.suffix in (".json",".yaml",".gv"):
            files.append({"file":p.name,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
    (out/"v3_6_source_snapshot.json").write_text(json.dumps({"architecture_provenance":prov["schema_version"],"files":files},indent=2)+"\n",encoding="utf-8")

def main():
    a=argparse.ArgumentParser();a.add_argument("--out",required=True);a.add_argument("--prompt-tokens",type=int,default=4096);a.add_argument("--generated-tokens",type=int,default=256);x=a.parse_args();out=Path(x.out);out.mkdir(parents=True,exist_ok=True)
    phases=(("prefill",x.prompt_tokens,0),("first_decode",1,x.prompt_tokens),("incremental_decode",1,x.prompt_tokens+x.generated_tokens-1));man={"model":"Qwen/Qwen1.5-MoE-A2.7B","target":"V3.6","schema":"operator-dag-1.0","evidence":"analytical_not_profiled","graphs":{}}
    for ph,t,past in phases:
        g=base.build(ph,t,past);data={"metadata":{"phase":ph,"query_tokens":t,"past_tokens":past,"key_tokens":t+past},"nodes":g.nodes,"edges":g.edges};(out/f"{ph}_graph.json").write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8");base.csvout(out/f"{ph}_nodes.csv",g.nodes);base.csvout(out/f"{ph}_edges.csv",g.edges);base.csvout(out/f"{ph}_npusim_ir.csv",({"task_id":n["node_id"],"layer":n["layer"],"op":n["op"],"unit":n["execution_unit"],"parallelism":n["parallelism"],"clusters":n["clusters"],"macs":n["useful_macs_global"],"timing":"UNMEASURED"} for n in g.nodes if n["clusters"]));base.csvout(out/f"{ph}_noc_traffic.csv",({"edge_id":e["edge_id"],"src":e["src"],"dst":e["dst"],"tensor":e["tensor"],"bytes":e["materialized_bytes_global"],"transport":e["transport"],"status":"REQUIRES_POPNET_REPLAY"} for e in g.edges if e["transport"]=="popnet"));man["graphs"][ph]={"nodes":len(g.nodes),"edges":len(g.edges),"useful_macs":sum(n["useful_macs_global"] for n in g.nodes)}
    rows,counts=placement();base.csvout(out/"layer_expert_placement.csv",rows);cap=capacity(x.prompt_tokens+x.generated_tokens,counts);(out/"memory_feasibility.json").write_text(json.dumps(cap,indent=2)+"\n",encoding="utf-8");(out/"manifest.json").write_text(json.dumps(man,indent=2)+"\n",encoding="utf-8");(out/"v3_6_mapping_manifest.json").write_text(json.dumps({"status":"STRUCTURAL_MAPPING_READY_STATIC_W4_CONDITIONAL","parallelism":"TP16+EP16","expert_placement":"cluster=(layer*60+expert)%16","expert_entries_per_cluster":counts,"vertical_rule":"Ni_to_CHi","execution":"NOT_RUN","thermal":"BLOCKED_UNRESOLVED_INTERFACE_RC"},indent=2)+"\n",encoding="utf-8");snapshot(out);print(json.dumps(man,indent=2))
if __name__=="__main__":main()
