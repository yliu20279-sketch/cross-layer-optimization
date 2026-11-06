#!/usr/bin/env python3
"""Build a V3.6 Qwen1.5-MoE analytical workload and LegoSim traffic contracts."""
from __future__ import annotations

import argparse, csv, hashlib, json, math
from pathlib import Path

H=2048; HEADS=16; KV_HEADS=16; D=128; LAYERS=24; VOCAB=151936
EXPERTS=60; TOPK=4; MOE_I=1408; SHARED_I=5632; ACT_BYTES=2
PP=4; TP=4; EP=4; PARTITION_BYTES=512*1024*1024; RESERVE=32*1024*1024
STAGES={f"PP{i}":[f"N{4*i+j}" for j in range(4)] for i in range(4)}

def write_csv(path, rows):
    rows=list(rows)
    if not rows: return
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def stage(layer): return f"PP{layer//6}"
def parts(s): return ["CH"+n[1:] for n in STAGES[s]]

def add_node(nodes, phase, layer, op, unit, tokens, params=0, macs=0, note=""):
    s=stage(layer) if layer>=0 else ("PP0" if op=="embedding" else "PP3")
    n={"node_id":f"{phase[:2].upper()}{len(nodes):04d}","phase":phase,"layer":layer,"op":op,
       "execution_unit":unit,"tokens":tokens,"parameter_count_global":int(params),
       "useful_macs_global":int(macs),"pp_stage":s,"tp_degree":TP,"ep_degree":EP if "expert" in op or "router" in op else 0,
       "clusters":STAGES[s],"hb_partitions":parts(s),"evidence_class":"analytical_from_official_config","note":note}
    nodes.append(n); return n["node_id"]

def edge(edges, phase, src, dst, kind, bytes_global, route="local_sram", activations=0):
    edges.append({"edge_id":f"{phase[:2].upper()}E{len(edges):04d}","src":src,"dst":dst,"traffic_class":kind,
                  "materialized_bytes_global":int(bytes_global),"route_policy":route,
                  "expert_activations":int(activations),"evidence_class":"analytical_tensor_shape"})

def build_phase(phase,tokens,past):
    nodes=[]; edges=[]; hidden=tokens*H*ACT_BYTES
    x=add_node(nodes,phase,-1,"embedding","HB_DRAM_NPU",tokens,VOCAB*H,tokens*H)
    for layer in range(LAYERS):
        if layer and layer%6==0:
            y=add_node(nodes,phase,layer,"pipeline_transfer","POPNET_DMA",tokens)
            edge(edges,phase,x,y,"pipeline",hidden,"rank_matched_xy"); x=y
        n=add_node(nodes,phase,layer,"attention_norm","NPU_VECTOR",tokens,H)
        edge(edges,phase,x,n,"activation",hidden)
        qkv=add_node(nodes,phase,layer,"qkv_projection_tp4","NPU_MAC",tokens,3*H*H,3*tokens*H*H)
        edge(edges,phase,n,qkv,"activation",hidden)
        attn=add_node(nodes,phase,layer,"flash_attention_kv_cache","NPU_MAC_HB_DRAM",tokens,0,
                      HEADS*D*tokens*(tokens+past),"scores are tiled and not materialized to HB-DRAM")
        edge(edges,phase,qkv,attn,"kv_cache",2*(tokens+past)*KV_HEADS*D*ACT_BYTES,"Ni_to_CHi")
        o=add_node(nodes,phase,layer,"o_projection_allreduce_tp4","NPU_MAC_POPNET",tokens,H*H,tokens*H*H)
        edge(edges,phase,attn,o,"collective",hidden,"stage_ring")
        router=add_node(nodes,phase,layer,"router_top4","NPU_VECTOR",tokens,H*EXPERTS,tokens*H*EXPERTS)
        edge(edges,phase,o,router,"activation",hidden)
        shuffle=add_node(nodes,phase,layer,"sem_moe_shuffled_reduce_scatter","POPNET_COLLECTIVE",tokens,
                         note="trace-dependent remote fraction is supplied by sem_moe_metrics.json")
        edge(edges,phase,router,shuffle,"expert_dispatch",tokens*TOPK*H*ACT_BYTES,"semantic_rank",tokens*TOPK)
        experts=add_node(nodes,phase,layer,"routed_experts_ep4","NPU_MAC_HB_DRAM",tokens,
                         EXPERTS*3*H*MOE_I,tokens*TOPK*3*H*MOE_I)
        edge(edges,phase,shuffle,experts,"expert_local",tokens*TOPK*H*ACT_BYTES,"EP4_15_experts_per_rank",tokens*TOPK)
        shared=add_node(nodes,phase,layer,"shared_expert_tp4","NPU_MAC_HB_DRAM",tokens,3*H*SHARED_I,
                        tokens*3*H*SHARED_I)
        edge(edges,phase,router,shared,"activation",hidden)
        combine=add_node(nodes,phase,layer,"sem_moe_deferred_shuffled_allgather","POPNET_COLLECTIVE",tokens)
        edge(edges,phase,experts,combine,"expert_combine",tokens*TOPK*H*ACT_BYTES,"semantic_rank",tokens*TOPK)
        out=add_node(nodes,phase,layer,"moe_residual","NPU_VECTOR",tokens)
        edge(edges,phase,combine,out,"activation",hidden); edge(edges,phase,shared,out,"activation",hidden); x=out
    lm=add_node(nodes,phase,-1,"lm_head","HB_DRAM_NPU",tokens,VOCAB*H,tokens*VOCAB*H)
    edge(edges,phase,x,lm,"activation",hidden)
    return nodes,edges

def capacity():
    embedding=VOCAB*H; attn_layer=4*H*H; router_layer=H*EXPERTS
    routed_layer=EXPERTS*3*H*MOE_I; shared_layer=3*H*SHARED_I
    norm_layer=2*H
    total=2*embedding+LAYERS*(attn_layer+router_layer+routed_layer+shared_layer+norm_layer)
    ideal_w4=math.ceil(total/2)
    per_partition=math.ceil(ideal_w4/16)
    return {"formula_parameter_count":total,"official_model_card_total_parameters_approx":14_300_000_000,
            "ideal_w4_bytes":ideal_w4,"capacity_total_bytes":16*PARTITION_BYTES,
            "average_weight_bytes_per_partition":per_partition,"runtime_reserve_bytes_per_partition":RESERVE,
            "average_partition_occupancy_bytes":per_partition+RESERVE,
            "average_capacity_fits":per_partition+RESERVE<=PARTITION_BYTES,
            "warning":"Average fit is not a packing proof; quantization metadata and per-expert imbalance remain unmeasured."}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--out",type=Path,required=True); ap.add_argument("--prompt-tokens",type=int,default=4096); ap.add_argument("--generated-tokens",type=int,default=256); a=ap.parse_args(); a.out.mkdir(parents=True,exist_ok=True)
    phases=[("prefill",a.prompt_tokens,0),("first_decode",1,a.prompt_tokens),("incremental_decode",1,a.prompt_tokens+a.generated_tokens-1)]
    manifest={"schema_version":"qwen1.5-moe-v3.6-1.0","model":"Qwen/Qwen1.5-MoE-A2.7B","target":"V3.6","graphs":{}}
    for p,t,past in phases:
        ns,es=build_phase(p,t,past); (a.out/f"{p}_graph.json").write_text(json.dumps({"metadata":{"phase":p,"tokens":t,"past_tokens":past},"nodes":ns,"edges":es},indent=2)+"\n",encoding="utf-8"); write_csv(a.out/f"{p}_nodes.csv",ns); write_csv(a.out/f"{p}_edges.csv",es); manifest["graphs"][p]={"nodes":len(ns),"edges":len(es)}
    cap=capacity(); (a.out/"memory_feasibility.json").write_text(json.dumps(cap,indent=2)+"\n",encoding="utf-8")
    mapping={"schema_version":"hiband-sem-moe-v3.6-1.0","parallelism":{"pipeline":4,"tensor":4,"expert":4},
             "stages":{s:{"layers":[i*6,i*6+5],"clusters":c,"hb_partitions":parts(s),"experts_per_rank_per_layer":15} for i,(s,c) in enumerate(STAGES.items())},
             "sem_moe":{"offline":"balanced alternating token-expert co-clustering","attention_dp":"request affinity rebatching contract","attention_tp":"shuffled-reduce-scatter plus deferred shuffled-allgather","trace_required_for_claims":True},
             "baselines":["round_robin_EP","HiBand_round_robin_EP","HiBand_Sem-MoE"],"status":"ANALYTICAL_MAPPING_SMOKE_READY_EXECUTION_PENDING"}
    (a.out/"v3_6_mapping.json").write_text(json.dumps(mapping,indent=2)+"\n",encoding="utf-8"); (a.out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    local_src=Path(__file__).resolve().parent/"target_architecture_v3_6"
    workspace_src=Path(__file__).resolve().parent.parent/"whisper_operator_inventory"/"target_architecture_v3_6"
    src=local_src if local_src.exists() else workspace_src
    names=["target_architecture_v3_6.yaml","tile_memory_noc_mapping_v3_6.json","npusim_cluster_v3_6.json","ramulator2_hb_partition_v3_6.yaml","deepstack_bank_oracle_v3_6.json"]
    snap={n:hashlib.sha256((src/n).read_bytes()).hexdigest() for n in names}; (a.out/"v3_6_source_snapshot.json").write_text(json.dumps(snap,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({**manifest,"capacity":cap},indent=2))

if __name__=="__main__": main()
