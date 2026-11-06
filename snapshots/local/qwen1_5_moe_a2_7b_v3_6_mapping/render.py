#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

C = {"attn":"#4477AA", "moe":"#EE6677", "shared":"#228833", "noc":"#AA3377", "mem":"#CCBB44", "ctl":"#999999"}

def box(ax, x, y, w, h, text, color, fs=7):
    ax.add_patch(FancyBboxPatch((x,y), w,h, boxstyle="round,pad=.006", fc=color, ec="#333", lw=.8))
    ax.text(x+w/2, y+h/2, text, ha="center", va="center", fontsize=fs)

def render_graph(out, manifest):
    fig, axes = plt.subplots(1, 3, figsize=(14, 7.5), constrained_layout=True)
    phases = [("prefill","Prefill","Q=4096, K=4096"), ("first_decode","First decode","Q=1, K=4097"), ("incremental_decode","Incremental decode","Q=1, K=4352")]
    ops = [("RMSNorm -> Q/K/V -> RoPE","attn"), ("Tiled QK -> Softmax -> P x V","attn"), ("O projection -> TP16 all-reduce","noc"), ("Residual -> RMSNorm","attn"), ("Router logits -> Softmax -> Top-4","moe"), ("Top-4 token dispatch (EP16)","noc"), ("Selected expert Gate/Up -> SiLU -> Down","moe"), ("Expert weighted combine","noc"), ("Shared Gate/Up -> SiLU -> Down","shared"), ("Sparse + gated shared -> residual","shared")]
    for ax, (key,title,shape) in zip(axes, phases):
        ax.set(xlim=(0,1), ylim=(0,1)); ax.axis("off"); ax.set_title(title+"\n"+shape, fontsize=11, weight="bold")
        box(ax,.12,.88,.76,.055,"CPU input -> vocab-parallel embedding",C["ctl"]); y=.79
        for label,color in ops:
            box(ax,.12,y,.76,.048,label,C[color]); y-=.061
        ax.text(.5,.16,"MoE decoder layer x24",ha="center",weight="bold",fontsize=9)
        box(ax,.12,.07,.76,.05,"Final norm -> vocab LM Head -> TopK",C["mem"])
        g=manifest["graphs"][key]
        ax.text(.5,.015,f'{g["nodes"]} nodes | {g["edges"]} edges | {g["useful_macs"]/1e9:.2f} GMAC',ha="center",fontsize=7)
    fig.suptitle("Qwen1.5-MoE-A2.7B operator-level DAGs",fontsize=15,weight="bold")
    for ext in ("png","pdf","svg"):
        fig.savefig(out/f"qwen1_5_moe_operator_graph_v3_6.{ext}",dpi=220,bbox_inches="tight")
    plt.close(fig)

def render_mapping(out, capacity):
    fig,(grid,bar)=plt.subplots(1,2,figsize=(13,6),constrained_layout=True)
    grid.set(xlim=(-.25,4.05),ylim=(-.7,4.2)); grid.axis("off")
    grid.set_title("TP16 attention + EP16 routed experts",weight="bold")
    entries=capacity["expert_entries_per_partition"]
    for row in range(4):
        for col in range(4):
            idx=4*row+col
            box(grid,col,3-row,.84,.70,f'N{idx} / CH{idx}\nHead {idx}\n90 layer-expert entries',C["moe"],6.5)
    grid.text(1.7,-.42,"Placement: cluster = (layer x 60 + expert) mod 16\nAll clusters run attention/shared expert; Top-4 tokens route to owners.",ha="center",fontsize=8.5)
    assert set(entries.values())=={90}

    p=capacity["per_partition"]
    vals=[p["embedding_and_lm_W4_bytes"],p["nonexpert_W4_bytes"],p["expert_W4_bytes"],p["kv_cache_bytes"],p["combined_metadata_runtime_reserve_bytes"]]
    labels=["Embed + LM W4","Nonexpert W4","90 expert entries W4","KV cache","Metadata/runtime reserve"]
    colors=[C["mem"],C["attn"],C["moe"],C["shared"],C["ctl"]]
    left=0
    for value,label,color in zip(vals,labels,colors):
        mib=value/2**20
        bar.barh([0],[mib],left=left,color=color,label=f"{label}: {mib:.1f} MiB")
        left+=mib
    limit=capacity["capacity_bytes_per_partition"]/2**20
    headroom=p["headroom_bytes"]/2**20
    bar.axvline(limit,color="#AA0000",ls="--",lw=1.4)
    bar.set(xlim=(0,535),ylim=(-.72,.68),xlabel="Per-partition occupancy (MiB)",yticks=[])
    bar.set_title("V3.6 HB partition at context 4,352",weight="bold")
    bar.legend(frameon=False,fontsize=8,loc="lower left")
    bar.text(limit,.32,f"512 MiB\nheadroom {headroom:.2f} MiB",ha="right",color="#AA0000",fontsize=8)
    fig.suptitle("Qwen1.5-MoE mapping to V3.6 (analytical, not profiled)",fontsize=15,weight="bold")
    for ext in ("png","pdf","svg"):
        fig.savefig(out/f"qwen1_5_moe_v3_6_mapping.{ext}",dpi=220,bbox_inches="tight")
    plt.close(fig)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--generated",required=True); args=parser.parse_args()
    out=Path(args.generated)
    render_graph(out,json.loads((out/"manifest.json").read_text(encoding="utf-8")))
    render_mapping(out,json.loads((out/"memory_feasibility.json").read_text(encoding="utf-8")))

if __name__=="__main__":
    main()
