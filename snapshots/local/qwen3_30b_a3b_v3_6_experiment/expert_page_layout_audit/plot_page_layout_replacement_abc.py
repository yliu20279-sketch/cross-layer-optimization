#!/usr/bin/env python3
"""Replace panel (c) with the held-out page-layout hotspot map.

Panels (a) and (b) retain the original data. Panels (b) and (c) share one
color normalization and colorbar, unlike the superseded figure.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
AUDIT = Path(__file__).resolve().parent
BASE = ROOT / "results" / "bank_soft70_scale_v1"
OUT = ROOT / "results" / "expert_page_layout_v1" / "figures"
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


def matrix_from_csv(path: Path) -> np.ndarray:
    data = pd.read_csv(path)
    expected = {(bank, layer) for bank in range(16) for layer in range(48)}
    observed = set(zip(data["decoded_bank"], data["decoder_layer"]))
    if len(data) != 768 or observed != expected or data.isna().any().any():
        raise ValueError(f"invalid 16 x 48 heatmap: {path}")
    matrix = data.pivot(index="decoded_bank", columns="decoder_layer",
                        values="cross_request_bank_wait_ticks")
    values = matrix.reindex(index=range(16), columns=range(48)).to_numpy(float)
    if not np.all(np.isfinite(values)) or np.any(values < 0):
        raise ValueError(f"invalid wait values: {path}")
    return values / 1000.0


def style_axis(ax):
    ax.set_xticks(np.arange(0, 48, 8))
    ax.set_yticks(np.arange(0, 16, 2))
    ax.set_xlabel("Decoder layer", labelpad=2)
    ax.set_ylabel("Global decoded Bank ID", labelpad=2)
    ax.tick_params(length=2.2, width=0.55, pad=1.5)
    for spine in ax.spines.values():
        spine.set_linewidth(0.55)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--layout-run", default="c4_full48_round_robin_v2",
                        choices=("c4_full48_round_robin_v2",
                                 "c4_full48_heat_layout_v1",
                                 "c4_full48_coaccess_layout_v1"))
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    layout_file = AUDIT / f"{args.layout_run}_layer_bank_wait.csv"
    control_run = ("c4_full48_pager_control_v2" if args.layout_run == "c4_full48_round_robin_v2"
                   else args.layout_run.replace("_layout_", "_control_"))
    control_file = AUDIT / f"{control_run}_layer_bank_wait.csv"
    control_manifest = json.loads((AUDIT / f"{control_run}_run_manifest.json").read_text())
    layout_manifest = json.loads((AUDIT / f"{args.layout_run}_run_manifest.json").read_text())
    if control_manifest["status"] != "PASS" or layout_manifest["status"] != "PASS":
        raise ValueError("matched control/layout run is not PASS")
    for field in ("operations", "dependencies", "represented_mem_bytes", "packets_completed"):
        if control_manifest[field] != layout_manifest[field]:
            raise ValueError(f"matched control/layout differ in {field}")
    original = matrix_from_csv(BASE / "runs/c4_soft70_normal/layer_bank_wait.csv")
    control = matrix_from_csv(control_file)
    optimized = matrix_from_csv(layout_file)
    if control.sum() <= 0 or optimized.sum() <= 0:
        raise ValueError("missing Bank-wait evidence")
    if optimized.max() > 1e6 or original.max() > 1e6:
        raise ValueError("fixed shared color range would clip data")

    mpl.rcParams.update({
        "font.family": "Arial", "font.size": 7,
        "axes.labelsize": 7.5, "xtick.labelsize": 6.2, "ytick.labelsize": 6.2,
        "legend.fontsize": 5.7, "pdf.fonttype": 42, "ps.fonttype": 42,
        "axes.unicode_minus": False,
    })
    fig = plt.figure(figsize=(7.16, 4.85), constrained_layout=True)
    grid = fig.add_gridspec(2, 3, width_ratios=[0.88, 2.12, 0.07], height_ratios=[1, 1])
    ax_a = fig.add_subplot(grid[:, 0])
    ax_b = fig.add_subplot(grid[0, 1])
    ax_c = fig.add_subplot(grid[1, 1])
    cax = fig.add_subplot(grid[:, 2])

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

    cmap = mpl.colormaps["magma"].copy()
    cmap.set_bad(cmap(0.0))  # zero wait uses the floor, never the bright high-value end
    norm = LogNorm(vmin=1e-3, vmax=1e6)
    for ax, matrix in ((ax_b, original), (ax_c, optimized)):
        ax.imshow(np.ma.masked_less_equal(matrix, 0), origin="upper", aspect="auto",
                  interpolation="nearest", cmap=cmap, norm=norm, rasterized=True)
        style_axis(ax)
    colorbar = fig.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax)
    colorbar.set_label("Same-Bank wait ($10^3$ DRAM ticks, log)", fontsize=6.4, labelpad=3)
    colorbar.ax.tick_params(labelsize=5.8, width=0.5, length=2)
    for ax, label in ((ax_a, "(a)"), (ax_b, "(b)"), (ax_c, "(c)")):
        ax.text(-0.13, 1.03, label, transform=ax.transAxes, fontsize=8.5,
                fontweight="bold", va="bottom", ha="left", clip_on=False)

    suffix = {
        "c4_full48_round_robin_v2": "page_layout_abc_v1",
        "c4_full48_heat_layout_v1": "heat_layout_abc_v1",
        "c4_full48_coaccess_layout_v1": "coaccess_layout_abc_v1",
    }[args.layout_run]
    basename = OUT / f"soft70_phenomenon_cause_{suffix}"
    preview = basename.with_name(basename.name + "_preview.png")
    render_preview(fig, str(preview), dpi=180)
    issues = audit_layout(fig)
    report = {
        "status": "PREVIEW" if not args.final else "EXPORTED",
        "panel_a_source": str(BASE / "scale_components.csv"),
        "panel_b_source": str(BASE / "runs/c4_soft70_normal/layer_bank_wait.csv"),
        "panel_c_source": str(layout_file),
        "matched_control_source": str(control_file),
        "layout_run": args.layout_run,
        "matched_control_cycles": control_manifest["total_cycles"],
        "layout_cycles": layout_manifest["total_cycles"],
        "matched_control_wait_ticks": float(control.sum() * 1000),
        "layout_wait_ticks": float(optimized.sum() * 1000),
        "matched_operations": layout_manifest["operations"],
        "matched_dependencies": layout_manifest["dependencies"],
        "matched_represented_mem_bytes": layout_manifest["represented_mem_bytes"],
        "matched_packets_completed": layout_manifest["packets_completed"],
        "shared_color_scale_thousand_ticks": [norm.vmin, norm.vmax],
        "zero_wait_encoding": "same dark color as the log-scale floor",
        "classification": "controlled soft70 address-mapping stress, not natural Qwen3 serving",
        "visual_audit": issues,
    }
    (basename.with_name(basename.name + "_provenance.json")).write_text(
        json.dumps(report, indent=2, default=str) + "\n")
    if args.final:
        cycle_reduction = 100 * (1 - layout_manifest["total_cycles"] / control_manifest["total_cycles"])
        wait_reduction = 100 * (1 - optimized.sum() / control.sum())
        caption = (
            "Figure: Controlled soft70 Bank-hotspot stress and expert-page placement.\n\n"
            "(a) Original c1/c2/c4 end-to-end component breakdown; unchanged data. "
            "(b) Original c4 Bank-by-decoder-layer strict cross-request same-Bank wait; "
            "unchanged data. (c) c4 after profile-derived heat- and cross-request "
            "temporal-overlap-aware expert-page Bank placement, with a per-Bank-capacity-aware "
            "pager. Panels (b) and (c) share the same logarithmic color scale in thousands "
            "of DRAM ticks; zero wait is encoded at the dark floor. Each matrix is 16 Banks "
            "by 48 decoder layers.\n\n"
            f"In the pager-matched control, {control_manifest['operations']:,} operations, "
            f"{control_manifest['dependencies']:,} dependencies, "
            f"{control_manifest['represented_mem_bytes']:,} represented memory bytes, and "
            f"{control_manifest['packets_completed']:,} completed packets are held fixed. "
            f"The control took {control_manifest['total_cycles']:,} cycles and "
            f"{round(control.sum() * 1000):,} cross-request Bank-wait ticks; coaccess "
            f"placement took {layout_manifest['total_cycles']:,} cycles and "
            f"{round(optimized.sum() * 1000):,} ticks ({cycle_reduction:.2f}% and "
            f"{wait_reduction:.2f}% lower, respectively). This is one held-out "
            "four-request cohort, not a multi-seed confidence interval or physical-chip "
            "measurement. The original (b) and new (c) have different pager DAGs, so "
            "causal improvements are stated only against the pager-matched control. "
            "Coaccess did not outperform round-robin on this cohort.\n"
        ) if args.layout_run == "c4_full48_coaccess_layout_v1" else None
        if caption:
            basename.with_name(basename.name + "_caption.txt").write_text(caption)
        fig.savefig(basename.with_suffix(".pdf"), dpi=600, bbox_inches="tight")
        fig.savefig(basename.with_suffix(".svg"), dpi=600, bbox_inches="tight")
        fig.savefig(basename.with_suffix(".png"), dpi=600, bbox_inches="tight")
        from PIL import Image
        Image.open(preview).convert("L").save(
            basename.with_name(basename.name + "_grayscale_preview.png"))
    plt.close(fig)
    print(json.dumps({"status": report["status"], "preview": str(preview),
                      "visual_audit": issues}, default=str))


if __name__ == "__main__":
    main()
