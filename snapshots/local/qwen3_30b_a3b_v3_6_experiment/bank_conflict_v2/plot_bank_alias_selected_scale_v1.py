#!/usr/bin/env python3
"""Publication figures for selected Bank-alias address-mapping stress."""
import json, sys
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
SUITE=ROOT/"results/bank_alias_pressure_selected_scale_v1"
SCREEN=ROOT/"results/bank_alias_pressure_screen_c4_v2"
FIG=SUITE/"figures"
SKILL=(Path.home()/".codex/skills/scipilot-figure-skill/scripts")
if not SKILL.exists(): SKILL=ROOT/"figure_skill_scripts"
sys.path.insert(0,str(SKILL))
from setup_style import setup_style
from export_figure import export_figure
from visual_qa import audit_layout

COMP=["Compute","NoC","DRAM service and non-cross-request memory wait","Paging DMA","Sync/other","Strict cross-request Bank exposed"]
LAB={"Compute":"Compute","NoC":"NoC","DRAM service and non-cross-request memory wait":"DRAM service +\nother memory wait","Paging DMA":"Paging DMA","Sync/other":"Sync / other","Strict cross-request Bank exposed":"Cross-request\nBank conflict"}
COL={"Compute":"#0072B2","NoC":"#56B4E9","DRAM service and non-cross-request memory wait":"#009E73","Paging DMA":"#CC79A7","Sync/other":"#B3B3B3","Strict cross-request Bank exposed":"#D55E00"}

def phenomenon(data,qa):
    cs=[1,2,4]; x=np.arange(3); width=.58
    sub=data[data.mapping=="alias"].set_index("concurrency").loc[cs]
    fig,ax=plt.subplots(figsize=(7.16,3.55),constrained_layout=True)
    bottom=np.zeros(3)
    for component in COMP:
        vals=sub[component].to_numpy(float)/1e6
        kw={"hatch":"////","edgecolor":"#7A2E00","linewidth":.65} if component==COMP[-1] else {}
        ax.bar(x,vals,width,bottom=bottom,color=COL[component],label=LAB[component],**kw); bottom+=vals
    for j,c in enumerate(cs):
        pct=100*float(sub.loc[c,"strict_bank_exposed_fraction"])
        ax.text(x[j],bottom[j]+bottom.max()*.018,f"{pct:.1f}%",ha="center",va="bottom",fontsize=7,color="#9C3D00")
    ax.set_xticks(x,["c1","c2","c4"]); ax.set_xlabel("Concurrent inference requests")
    ax.set_ylabel("End-to-end runtime (million cycles)")
    ax.set_title("Address-mapping stress (not natural Qwen3): effective-2-Bank alias",pad=7)
    ax.grid(axis="y",color="#D9D9D9",linewidth=.45); ax.set_axisbelow(True)
    ax.legend(ncol=3,loc="upper center",frameon=False,bbox_to_anchor=(.5,-.18),fontsize=6.4)
    ymax=ax.get_ylim()[1]; ax.set_ylim(0,ymax*1.08)
    qa["phenomenon"]=audit_layout(fig)
    export_figure(fig,str(FIG/"phenomenon_bank_alias_stacked"),formats=("pdf","svg","png"),size_inches=(7.16,3.55),dpi=600,grayscale_preview=True); plt.close(fig)

def load_bank(case):
    d=pd.read_csv(SCREEN/"runs"/f"{case}_normal"/"bank_aggregate.csv")
    d["decoded_bank"]=d.bankgroup*4+d.bank
    idx=pd.MultiIndex.from_product([range(16),range(16)],names=["partition","decoded_bank"])
    return d.set_index(["partition","decoded_bank"]).reindex(idx,fill_value=0).reset_index()

def cause(winner,qa):
    source=SUITE/"runs/c4_effective2_normal_layer_heatmap_v1/layer_bank_wait.csv"
    data=pd.read_csv(source)
    mat=data.pivot(index="decoded_bank",columns="decoder_layer",values="cross_request_bank_wait_ticks").reindex(index=range(16),columns=range(48),fill_value=0).to_numpy(float)
    display=mat/1000.0
    positive=display[display>0]
    vmax=float(np.percentile(positive,99)) if len(positive) else 1.0
    fig,ax=plt.subplots(figsize=(7.16,3.65),constrained_layout=True)
    image=ax.imshow(display,cmap="magma",vmin=0,vmax=vmax,aspect="auto",interpolation="nearest",origin="upper")
    ax.set_xticks(np.arange(0,48,4)); ax.set_yticks(np.arange(0,16,1))
    ax.set_xlabel("Decoder layer (execution window)")
    ax.set_ylabel("Decoded Bank ID\n(summed over 16 partitions)")
    ax.set_title("Qwen3-30B-A3B-derived effective-2-Bank address-mapping stress, c4",pad=7)
    cb=fig.colorbar(image,ax=ax,shrink=.88,pad=.025)
    cb.set_label("Cross-request same-Bank wait (thousand DRAM ticks)")
    qa["cause"]=audit_layout(fig)
    bank,layer=np.unravel_index(np.argmax(mat),mat.shape)
    metrics={"selected_case":winner,"matrix_shape":[16,48],"aggregation":"decoded Bank x decoder layer; summed over 16 partitions",
             "unit":"DRAM ticks in CSV; thousand DRAM ticks in figure","normalization":"none","vmin":0,"vmax_thousand_ticks_p99_positive":vmax,
             "total_cross_request_bank_wait_ticks":float(mat.sum()),
             "maximum_cell":{"decoded_bank":int(bank),"decoder_layer":int(layer),"ticks":float(mat[bank,layer])}}
    (SUITE/"cause_metrics.json").write_text(json.dumps(metrics,indent=2)+"\n")
    export_figure(fig,str(FIG/"cause_bank_contention_heatmap"),formats=("pdf","svg","png"),size_inches=(7.16,3.65),dpi=600,grayscale_preview=True); plt.close(fig)

def main():
    setup_style(journal="ieee",lang="en",use_sciplots=False); FIG.mkdir(parents=True,exist_ok=True)
    data=pd.read_csv(SUITE/"scale_components.csv")
    for _,r in data.iterrows():
        if not np.isclose(sum(float(r[x]) for x in COMP),float(r.normal_cycles),atol=1e-6): raise RuntimeError("non-conserving plot input")
    winner=json.loads((SUITE/"scale_report.json").read_text())["selected_case"]
    qa={}; phenomenon(data,qa); cause(winner,qa)
    norm={k:[{"severity":s,"message":m} for s,m in v] for k,v in qa.items()}; (FIG/"visual_qa.json").write_text(json.dumps(norm,indent=2)+"\n")
    print(json.dumps({"status":"PASS" if not any(s=="FAIL" for v in qa.values() for s,_ in v) else "FAIL","qa":norm},indent=2))
if __name__=="__main__": main()
