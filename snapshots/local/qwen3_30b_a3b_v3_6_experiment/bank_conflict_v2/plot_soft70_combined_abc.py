#!/usr/bin/env python3
"""Combine the soft70 phenomenon, cause, and opportunity panels."""
import json
import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results/bank_soft70_scale_v1"
OPT = ROOT / "results/bank_soft70_triple_v1"
OUT = ROOT / "results/bank_soft70_combined_v1/figures"
SKILL = Path(r"C:\Users\21747\.codex\skills\scipilot-figure-skill")
sys.path.insert(0, str(SKILL / "scripts"))
from visual_qa import audit_layout, render_preview  # noqa: E402

COMP = [
    "Compute", "NoC", "DRAM service and non-cross-request memory wait",
    "Paging DMA", "Sync/other", "Strict cross-request Bank exposed",
]
LABEL = {
    "Compute": "Compute", "NoC": "NoC",
    "DRAM service and non-cross-request memory wait": "DRAM service +\nother memory wait",
    "Paging DMA": "Paging DMA", "Sync/other": "Sync / other",
    "Strict cross-request Bank exposed": "Cross-user\nBank contention",
}
COLOR = {
    "Compute": "#0072B2", "NoC": "#56B4E9",
    "DRAM service and non-cross-request memory wait": "#009E73",
    "Paging DMA": "#CC79A7", "Sync/other": "#B3B3B3",
    "Strict cross-request Bank exposed": "#D55E00",
}


def matrix_from_csv(path):
    data = pd.read_csv(path)
    return data.pivot(
        index="decoded_bank", columns="decoder_layer",
        values="cross_request_bank_wait_ticks",
    ).reindex(index=range(16), columns=range(48), fill_value=0).to_numpy(float) / 1000.0


def draw_heatmap(fig, ax, matrix, short_label):
    positive = matrix[matrix > 0]
    image = ax.imshow(
        np.ma.masked_less_equal(matrix, 0), origin="upper", aspect="auto",
        interpolation="nearest", cmap="magma",
        norm=LogNorm(vmin=float(positive.min()), vmax=float(positive.max())),
        rasterized=True,
    )
    ax.set_xticks(np.arange(0, 48, 8))
    ax.set_yticks(np.arange(0, 16, 2))
    ax.set_xlabel("Decoder layer", labelpad=2)
    ax.set_ylabel("Global decoded Bank ID", labelpad=2)
    ax.tick_params(length=2.2, width=0.55, pad=1.5)
    for spine in ax.spines.values():
        spine.set_linewidth(0.55)
    cb = fig.colorbar(image, ax=ax, pad=0.015, fraction=0.035)
    cb.set_label(short_label, fontsize=6.4, labelpad=3)
    cb.ax.tick_params(labelsize=5.8, width=0.5, length=2)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    mpl.rcParams.update({
        "font.family": "Arial", "font.size": 7,
        "axes.labelsize": 7.5, "xtick.labelsize": 6.2, "ytick.labelsize": 6.2,
        "legend.fontsize": 5.7, "pdf.fonttype": 42, "ps.fonttype": 42,
        "axes.unicode_minus": False,
    })
    fig = plt.figure(figsize=(7.16, 4.85), constrained_layout=True)
    grid = fig.add_gridspec(2, 2, width_ratios=[0.88, 2.12], height_ratios=[1, 1])
    ax_a = fig.add_subplot(grid[:, 0])
    ax_b = fig.add_subplot(grid[0, 1])
    ax_c = fig.add_subplot(grid[1, 1])

    data = pd.read_csv(BASE / "scale_components.csv").set_index("concurrency").loc[[1, 2, 4]]
    x = np.arange(3)
    bottom = np.zeros(3)
    for component in COMP:
        values = data[component].to_numpy(float) / 1e6
        extra = ({"hatch": "////", "edgecolor": "#7A2E00", "linewidth": 0.55}
                 if component == COMP[-1] else {})
        ax_a.bar(x, values, 0.58, bottom=bottom, color=COLOR[component],
                 label=LABEL[component], **extra)
        bottom += values
    for j, concurrency in enumerate((1, 2, 4)):
        pct = 100 * float(data.loc[concurrency, "strict_bank_exposed_fraction"])
        ax_a.text(x[j], bottom[j] + 3.2, f"{pct:.1f}%", ha="center", va="bottom",
                  fontsize=6.2, color="#9C3D00")
    ax_a.set_xticks(x, ["c1\n1 user", "c2\n2 users", "c4\n4 users"])
    ax_a.set_xlabel("Cross-user concurrency", labelpad=3)
    ax_a.set_ylabel("End-to-end runtime (million cycles)", labelpad=3)
    ax_a.set_ylim(0, 220)
    ax_a.grid(axis="y", color="#D9D9D9", linewidth=0.4)
    ax_a.set_axisbelow(True)
    ax_a.legend(ncol=2, loc="upper left", frameon=False,
                bbox_to_anchor=(0.025, 0.985), columnspacing=0.75,
                handlelength=1.55, handletextpad=0.4, fontsize=5.3)

    baseline = matrix_from_csv(BASE / "runs/c4_soft70_normal/layer_bank_wait.csv")
    optimized = matrix_from_csv(OPT / "run_c4_bank_online/layer_bank_wait.csv")
    draw_heatmap(fig, ax_b, baseline, "Same-Bank wait\n($10^3$ DRAM ticks, log)")
    draw_heatmap(fig, ax_c, optimized, "Same-Bank wait\n($10^3$ DRAM ticks, log)")

    # Unified panel labels, with no per-panel titles.
    for ax, label in ((ax_a, "(a)"), (ax_b, "(b)"), (ax_c, "(c)")):
        ax.text(-0.13, 1.03, label, transform=ax.transAxes, fontsize=8.5,
                fontweight="bold", va="bottom", ha="left", clip_on=False)

    preview = OUT / "soft70_phenomenon_cause_opportunity_abc_preview.png"
    render_preview(fig, str(preview), dpi=180)
    issues = audit_layout(fig)
    (OUT / "soft70_phenomenon_cause_opportunity_abc_visual_qa.json").write_text(
        json.dumps(issues, indent=2, default=str) + "\n"
    )
    basename = OUT / "soft70_phenomenon_cause_opportunity_abc"
    fig.savefig(basename.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(basename.with_suffix(".svg"), bbox_inches="tight")
    fig.savefig(basename.with_suffix(".png"), dpi=600, bbox_inches="tight")
    print(json.dumps({"status": "PASS", "issues": issues, "output": str(basename)}, default=str))


if __name__ == "__main__":
    main()
