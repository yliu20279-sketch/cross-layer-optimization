#!/usr/bin/env python3
"""Publication figures for selected soft70 address-mapping stress."""
import json, sys
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "results/bank_soft70_scale_v1"
FIG = SUITE / "figures"
SKILL = Path.home() / ".codex/skills/scipilot-figure-skill/scripts"
sys.path.insert(0, str(SKILL))
from setup_style import setup_style
from export_figure import export_figure
from visual_qa import audit_layout, render_preview

COMP = ["Compute", "NoC", "DRAM service and non-cross-request memory wait",
        "Paging DMA", "Sync/other", "Strict cross-request Bank exposed"]
LABEL = {"Compute":"Compute", "NoC":"NoC",
         "DRAM service and non-cross-request memory wait":"DRAM service +\nother memory wait",
         "Paging DMA":"Paging DMA", "Sync/other":"Sync / other",
         "Strict cross-request Bank exposed":"Cross-request\nBank conflict"}
COLOR = {"Compute":"#0072B2", "NoC":"#56B4E9",
         "DRAM service and non-cross-request memory wait":"#009E73",
         "Paging DMA":"#CC79A7", "Sync/other":"#B3B3B3",
         "Strict cross-request Bank exposed":"#D55E00"}

def phenomenon(data, qa):
    data = data.set_index("concurrency").loc[[1,2,4]]
    x, bottom = np.arange(3), np.zeros(3)
    fig, ax = plt.subplots(figsize=(7.16, 3.55), constrained_layout=True)
    for component in COMP:
        values = data[component].to_numpy(float) / 1e6
        kwargs = {"hatch":"////", "edgecolor":"#7A2E00", "linewidth":.65} if component == COMP[-1] else {}
        ax.bar(x, values, .58, bottom=bottom, color=COLOR[component], label=LABEL[component], **kwargs)
        bottom += values
    for j, c in enumerate((1,2,4)):
        pct = 100 * float(data.loc[c, "strict_bank_exposed_fraction"])
        ax.text(x[j], bottom[j] + bottom.max()*.018, f"{pct:.1f}%", ha="center", va="bottom", fontsize=7, color="#9C3D00")
    ax.set_xticks(x, ["c1", "c2", "c4"])
    ax.set_xlabel("Concurrent inference requests")
    ax.set_ylabel("End-to-end runtime (million cycles)")
    ax.set_title("Soft-70 Bank-hotspot stress (controlled address mapping; not natural Qwen3)", pad=7)
    ax.set_ylim(0, ax.get_ylim()[1]*1.08)
    ax.grid(axis="y", color="#D9D9D9", linewidth=.45); ax.set_axisbelow(True)
    ax.legend(ncol=3, loc="upper center", frameon=False, bbox_to_anchor=(.5,-.18), fontsize=6.4)
    qa["phenomenon"] = audit_layout(fig)
    render_preview(fig, str(FIG/"_preview_phenomenon.png"), dpi=150)
    export_figure(fig, str(FIG/"phenomenon_soft70_stacked"), formats=("pdf","svg","png"),
                  size_inches=(7.16,3.55), dpi=600, grayscale_preview=True, tight=False)
    exact_png = FIG/"phenomenon_soft70_stacked.png"
    fig.savefig(exact_png, dpi=600, bbox_inches=None)
    Image.open(exact_png).convert("L").save(FIG/"phenomenon_soft70_stacked_grayscale.png")
    plt.close(fig)

def cause(qa):
    source = SUITE / "runs/c4_soft70_normal/layer_bank_wait.csv"
    data = pd.read_csv(source)
    matrix = data.pivot(index="decoded_bank", columns="decoder_layer", values="cross_request_bank_wait_ticks").reindex(index=range(16), columns=range(48), fill_value=0).to_numpy(float)
    display = matrix / 1000.0
    positive = display[display>0]
    vmax = float(np.percentile(positive, 99)) if len(positive) else 1.0
    fig, ax = plt.subplots(figsize=(7.16, 3.65), constrained_layout=True)
    image = ax.imshow(display, cmap="magma", vmin=0, vmax=vmax, aspect="auto", interpolation="nearest", origin="upper")
    ax.set_xticks(np.arange(0,48,4)); ax.set_yticks(np.arange(16))
    ax.set_xlabel("Decoder layer")
    ax.set_ylabel("Global decoded Bank ID")
    ax.set_title("Soft-70 Bank-hotspot stress at c4 (controlled address mapping)", pad=7)
    colorbar = fig.colorbar(image, ax=ax, shrink=.88, pad=.025)
    colorbar.set_label("Cross-request same-Bank wait (thousand DRAM ticks)")
    qa["cause"] = audit_layout(fig)
    render_preview(fig, str(FIG/"_preview_cause.png"), dpi=150)
    bank, layer = np.unravel_index(np.argmax(matrix), matrix.shape)
    metrics = {"matrix_shape":[16,48], "aggregation":"decoded Bank x decoder layer; summed over 16 partitions",
               "unit":"DRAM ticks in CSV; thousand DRAM ticks in figure", "normalization":"none",
               "vmin":0, "vmax_thousand_ticks_p99_positive":vmax,
               "nonzero_cells":int(np.count_nonzero(matrix)), "total_cells":int(matrix.size),
               "total_cross_request_bank_wait_ticks":float(matrix.sum()),
               "maximum_cell":{"decoded_bank":int(bank), "decoder_layer":int(layer), "ticks":float(matrix[bank,layer])}}
    (SUITE/"cause_metrics.json").write_text(json.dumps(metrics, indent=2)+"\n")
    export_figure(fig, str(FIG/"cause_soft70_bank_contention_heatmap"), formats=("pdf","svg","png"),
                  size_inches=(7.16,3.65), dpi=600, grayscale_preview=True, tight=False)
    exact_png = FIG/"cause_soft70_bank_contention_heatmap.png"
    fig.savefig(exact_png, dpi=600, bbox_inches=None)
    Image.open(exact_png).convert("L").save(FIG/"cause_soft70_bank_contention_heatmap_grayscale.png")
    plt.close(fig)

def cause_log_supplement(qa):
    source = SUITE / "runs/c4_soft70_normal/layer_bank_wait.csv"
    data = pd.read_csv(source)
    matrix = data.pivot(index="decoded_bank", columns="decoder_layer", values="cross_request_bank_wait_ticks").reindex(index=range(16), columns=range(48), fill_value=0).to_numpy(float)
    display = matrix / 1000.0
    positive = display[display > 0]
    if not len(positive):
        raise RuntimeError("log heatmap requires positive values")
    fig, ax = plt.subplots(figsize=(7.16, 3.65), constrained_layout=True)
    image = ax.imshow(display, cmap="magma", norm=LogNorm(vmin=float(positive.min()), vmax=float(positive.max())),
                      aspect="auto", interpolation="nearest", origin="upper")
    ax.set_xticks(np.arange(0,48,4)); ax.set_yticks(np.arange(16))
    ax.set_xlabel("Decoder layer")
    ax.set_ylabel("Global decoded Bank ID")
    ax.set_title("Soft-70 Bank-hotspot stress at c4 (log color scale; supplementary)", pad=7)
    colorbar = fig.colorbar(image, ax=ax, shrink=.88, pad=.025)
    colorbar.set_label("Cross-request same-Bank wait (thousand DRAM ticks, log scale)")
    qa["cause_log_supplement"] = audit_layout(fig)
    render_preview(fig, str(FIG/"_preview_cause_log.png"), dpi=150)
    basename = FIG/"cause_soft70_bank_contention_heatmap_log"
    export_figure(fig, str(basename), formats=("pdf","svg","png"), size_inches=(7.16,3.65),
                  dpi=600, grayscale_preview=True, tight=False)
    exact_png = Path(str(basename) + ".png")
    fig.savefig(exact_png, dpi=600, bbox_inches=None)
    Image.open(exact_png).convert("L").save(Path(str(basename) + "_grayscale.png"))
    metrics = {"matrix_shape":[16,48], "normalization":"logarithmic color normalization",
               "unit":"thousand DRAM ticks", "vmin":float(positive.min()), "vmax":float(positive.max()),
               "nonzero_cells":int(np.count_nonzero(matrix)), "total_cells":int(matrix.size),
               "warning":"Supplementary visualization only; log normalization compresses the hotspot-to-cold-Bank magnitude gap."}
    (SUITE/"cause_log_metrics.json").write_text(json.dumps(metrics, indent=2)+"\n")
    plt.close(fig)

def main():
    setup_style(journal="ieee", lang="en", use_sciplots=False)
    FIG.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(SUITE/"scale_components.csv")
    for _, row in data.iterrows():
        if not np.isclose(sum(float(row[x]) for x in COMP), float(row.normal_cycles), atol=1e-6):
            raise RuntimeError("non-conserving plot input")
    qa = {}; phenomenon(data, qa); cause(qa); cause_log_supplement(qa)
    normalized = {k:[{"severity":s,"message":m} for s,m in v] for k,v in qa.items()}
    status = "PASS" if not any(s=="FAIL" for v in qa.values() for s,_ in v) else "FAIL"
    (FIG/"visual_qa.json").write_text(json.dumps({"status":status,"issues":normalized}, indent=2)+"\n")
    print(json.dumps({"status":status,"qa":normalized}, indent=2))

if __name__ == "__main__": main()
