#!/usr/bin/env python3
"""Draw the optimized soft70 Bank-by-layer hotspot heatmap."""
import csv
import json
import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm

ROOT = Path(__file__).resolve().parents[1]
SKILL = Path(r"C:\Users\21747\.codex\skills\scipilot-figure-skill")
sys.path.insert(0, str(SKILL / "scripts"))
from visual_qa import audit_layout, render_preview  # noqa: E402

RUN = ROOT / "results/bank_soft70_triple_v1/run_c4_bank_online"
OUT = ROOT / "results/bank_soft70_triple_v1/figures"


def load_matrix(path):
    matrix = np.zeros((16, 48), dtype=float)
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            matrix[int(row["decoded_bank"]), int(row["decoder_layer"])] += float(
                row["cross_request_bank_wait_ticks"]
            )
    return matrix


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    matrix = load_matrix(RUN / "layer_bank_wait.csv") / 1000.0
    positive = matrix[matrix > 0]
    vmin = max(1.0, float(np.percentile(positive, 1)))
    vmax = float(np.percentile(positive, 99.5))

    mpl.rcParams.update({
        "font.family": "Arial",
        "font.size": 8,
        "axes.labelsize": 9,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "axes.unicode_minus": False,
    })
    fig, ax = plt.subplots(figsize=(7.16, 2.55), constrained_layout=True)
    image = ax.imshow(
        np.ma.masked_less_equal(matrix, 0),
        origin="upper",
        aspect="auto",
        interpolation="nearest",
        cmap="magma",
        norm=LogNorm(vmin=vmin, vmax=vmax),
        rasterized=True,
    )
    ax.set_xlabel("Decoder layer")
    ax.set_ylabel("Global decoded Bank ID")
    ax.set_xticks(np.arange(0, 48, 4))
    ax.set_yticks(np.arange(16))
    ax.tick_params(length=2.5, width=0.6)
    for spine in ax.spines.values():
        spine.set_linewidth(0.6)
    colorbar = fig.colorbar(image, ax=ax, pad=0.018, fraction=0.035)
    colorbar.set_label("Same-Bank wait\n($10^3$ DRAM ticks, log scale)", fontsize=8)
    colorbar.ax.tick_params(labelsize=7, width=0.6, length=2.5)

    basename = OUT / "opportunity_soft70_triple_hotspot_log"
    preview = OUT / "opportunity_soft70_triple_hotspot_log_preview.png"
    render_preview(fig, str(preview), dpi=180)
    issues = audit_layout(fig)
    (OUT / "opportunity_soft70_triple_hotspot_log_visual_qa.json").write_text(
        json.dumps(issues, indent=2, default=str) + "\n"
    )
    fig.savefig(basename.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(basename.with_suffix(".svg"), bbox_inches="tight")
    fig.savefig(basename.with_suffix(".png"), dpi=600, bbox_inches="tight")

    sums = matrix.sum(axis=1)
    order = np.argsort(sums)[::-1]
    metrics = {
        "status": "PASS",
        "matrix_shape": [16, 48],
        "aggregation": "decoded Bank x decoder layer; summed over 16 partitions",
        "unit": "thousand DRAM ticks in figure",
        "normalization": "LogNorm; zeros masked",
        "total_wait_ticks": float(matrix.sum() * 1000),
        "top4_banks": [int(x) for x in order[:4]],
        "top4_share": float(sums[order[:4]].sum() / sums.sum()),
        "maximum_cell_ticks": float(matrix.max() * 1000),
        "scope": "50% compression plus soft70-then-XOR online Bank simulation; hotspot link and 128 B/cycle decode do not change decoded Bank identity",
        "limitation": "controlled soft70 address-mapping stress; not a natural Qwen3 workload",
    }
    (OUT / "opportunity_soft70_triple_hotspot_metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n"
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
