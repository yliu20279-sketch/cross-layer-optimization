#!/usr/bin/env python3
"""Publication figures for the validated full-48-layer strict C+O scale suite."""
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "results/bank_memory_stress_full48_co_scale_strict_v2"
FIGURES = SUITE / "figures"
SKILL = Path.home() / ".codex/skills/scipilot-figure-skill/scripts"
sys.path.insert(0, str(SKILL))
from setup_style import setup_style
from export_figure import export_figure
from visual_qa import audit_layout


COMPONENTS = [
    "Compute",
    "NoC",
    "DRAM service and non-cross-request memory wait",
    "Paging DMA",
    "Sync/other",
    "Strict cross-request Bank exposed",
]
LABELS = {
    "Compute": "Compute",
    "NoC": "NoC",
    "DRAM service and non-cross-request memory wait": "DRAM service +\nother memory wait",
    "Paging DMA": "Paging DMA",
    "Sync/other": "Sync / other",
    "Strict cross-request Bank exposed": "Cross-request\nBank conflict",
}
COLORS = {
    "Compute": "#0072B2",
    "NoC": "#56B4E9",
    "DRAM service and non-cross-request memory wait": "#009E73",
    "Paging DMA": "#CC79A7",
    "Sync/other": "#B3B3B3",
    "Strict cross-request Bank exposed": "#D55E00",
}


def gini(values):
    x = np.asarray(values, dtype=float)
    if np.allclose(x.sum(), 0):
        return 0.0
    x = np.sort(x)
    n = len(x)
    return float((2 * np.sum(np.arange(1, n + 1) * x) / (n * x.sum())) - (n + 1) / n)


def plot_phenomenon(data, qa):
    fig, ax = plt.subplots(figsize=(7.16, 3.25), constrained_layout=True)
    x = np.arange(len(data))
    bottom = np.zeros(len(data))
    for component in COMPONENTS:
        values = data[component].to_numpy(float) / 1e6
        kwargs = {}
        if component == "Strict cross-request Bank exposed":
            kwargs.update(hatch="////", edgecolor="#7A2E00", linewidth=0.7)
        ax.bar(x, values, bottom=bottom, width=0.68, color=COLORS[component],
               label=LABELS[component], **kwargs)
        bottom += values
    for i, row in data.iterrows():
        pct = 100 * float(row["strict_bank_exposed_fraction"])
        ax.text(i, float(row["normal_cycles"]) / 1e6 + 2.8, f"{pct:.2f}%",
                ha="center", va="bottom", fontsize=7, color="#9C3D00", fontweight="bold")
    ax.set_xticks(x, [f"c{int(v)}" for v in data["concurrency"]])
    ax.set_xlabel("Concurrent inference requests")
    ax.set_ylabel("End-to-end runtime (million cycles)")
    ax.set_ylim(0, bottom.max() * 1.14)
    ax.set_title("Full 48-layer C+O stress: strict Bank-conflict exposure grows with concurrency", pad=7)
    ax.grid(axis="y", color="#D9D9D9", linewidth=0.45, alpha=0.8)
    ax.set_axisbelow(True)
    ax.legend(ncol=3, loc="upper left", frameon=False, columnspacing=1.2,
              handlelength=1.8, bbox_to_anchor=(0.0, 1.01))
    qa["phenomenon"] = audit_layout(fig)
    export_figure(fig, str(FIGURES / "phenomenon_full48_co_stacked"),
                  formats=("pdf", "svg", "png"), size_inches=(7.16, 3.25),
                  dpi=600, grayscale_preview=True)
    plt.close(fig)


def matrix(frame, field):
    return frame.pivot(index="partition", columns="decoded_bank", values=field).sort_index().sort_index(axis=1)


def plot_cause(bank, qa):
    bank = bank.copy()
    bank["decoded_bank"] = bank["bankgroup"] * 4 + bank["bank"]
    bank["access_share_pct"] = 100 * bank["transactions"] / bank["transactions"].sum()
    bank["wait_share_pct"] = 100 * bank["cross_request_bank_wait_ticks"] / bank["cross_request_bank_wait_ticks"].sum()
    access = matrix(bank, "access_share_pct")
    waits = matrix(bank, "wait_share_pct")
    access_values = bank["transactions"].to_numpy(float)
    wait_values = bank["cross_request_bank_wait_ticks"].to_numpy(float)
    amax = bank.loc[bank["access_share_pct"].idxmax()]
    wmax = bank.loc[bank["wait_share_pct"].idxmax()]
    metrics = {
        "cells": int(len(bank)),
        "access_cv": float(access_values.std() / access_values.mean()),
        "access_gini": gini(access_values),
        "hottest_access_cell": {"partition": int(amax["partition"]), "decoded_bank": int(amax["decoded_bank"]), "share_pct": float(amax["access_share_pct"])},
        "wait_cv": float(wait_values.std() / wait_values.mean()),
        "wait_gini": gini(wait_values),
        "hottest_wait_cell": {"partition": int(wmax["partition"]), "decoded_bank": int(wmax["decoded_bank"]), "share_pct": float(wmax["wait_share_pct"])},
        "top10_access_share_pct": float(100 * np.sort(access_values)[-10:].sum() / access_values.sum()),
        "top10_wait_share_pct": float(100 * np.sort(wait_values)[-10:].sum() / wait_values.sum()),
        "interpretation": "Accesses are nearly uniform across 256 Partition×Bank cells; wait time is more uneven but not dominated by a few cells. C+O exposure is primarily temporal overlap plus outstanding=1, not a strong spatial hotspot.",
    }
    (SUITE / "cause_metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")

    fig, axes = plt.subplots(1, 2, figsize=(7.16, 3.35), constrained_layout=True)
    panels = [
        (axes[0], access, "viridis", "Access share of all transactions (%)",
         f"(a) Access distribution: CV={metrics['access_cv']:.3f}"),
        (axes[1], waits, "magma", "Share of cross-request Bank-wait ticks (%)",
         f"(b) Conflict-wait distribution: CV={metrics['wait_cv']:.3f}"),
    ]
    for ax, values, cmap, cbar_label, title in panels:
        image = ax.imshow(values.to_numpy(), cmap=cmap, vmin=0,
                          vmax=float(values.to_numpy().max()), aspect="equal",
                          interpolation="nearest", origin="upper")
        cbar = fig.colorbar(image, ax=ax, shrink=0.77, pad=0.025)
        cbar.set_label(cbar_label)
        ax.set_xticks(np.arange(values.shape[1]))
        ax.set_yticks(np.arange(values.shape[0]))
        ax.set_xticks(np.arange(-0.5, values.shape[1], 1), minor=True)
        ax.set_yticks(np.arange(-0.5, values.shape[0], 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=0.18)
        ax.tick_params(which="minor", bottom=False, left=False)
        ax.set_xlabel("Decoded Bank ID (bankgroup × 4 + bank)")
        ax.set_ylabel("DRAM partition")
        ax.set_title(title, pad=6)
        ax.set_xticklabels([str(int(v)) for v in values.columns], rotation=0)
        ax.set_yticklabels([str(int(v)) for v in values.index], rotation=0)
    for ax, row in ((axes[0], amax), (axes[1], wmax)):
        ax.add_patch(patches.Rectangle((int(row["decoded_bank"]), int(row["partition"])), 1, 1,
                                       fill=False, edgecolor="#E69F00", linewidth=1.4))
    axes[0].text(0.01, -0.19,
                 f"Hottest: P{int(amax['partition'])}/B{int(amax['decoded_bank'])}, {amax['access_share_pct']:.3f}%",
                 transform=axes[0].transAxes, ha="left", va="top", fontsize=6.5)
    axes[1].text(0.01, -0.19,
                 f"Hottest: P{int(wmax['partition'])}/B{int(wmax['decoded_bank'])}, {wmax['wait_share_pct']:.3f}%",
                 transform=axes[1].transAxes, ha="left", va="top", fontsize=6.5)
    qa["cause"] = audit_layout(fig)
    export_figure(fig, str(FIGURES / "cause_c16_bank_distribution"),
                  formats=("pdf", "svg", "png"), size_inches=(7.16, 3.35),
                  dpi=600, grayscale_preview=True)
    plt.close(fig)


def main():
    setup_style(journal="ieee", lang="en", use_sciplots=False)
    FIGURES.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(SUITE / "scale_components.csv").sort_values("concurrency").reset_index(drop=True)
    for _, row in data.iterrows():
        total = sum(float(row[name]) for name in COMPONENTS)
        if not np.isclose(total, float(row["normal_cycles"]), atol=1e-6):
            raise RuntimeError(f"c{int(row['concurrency'])}: non-conserving plot input")
    bank = pd.read_csv(SUITE / "runs/c16_normal/bank_aggregate.csv")
    qa = {}
    plot_phenomenon(data, qa)
    plot_cause(bank, qa)
    normalized = {name: [{"severity": sev, "message": msg} for sev, msg in issues] for name, issues in qa.items()}
    (FIGURES / "visual_qa.json").write_text(json.dumps(normalized, indent=2) + "\n")
    status = "PASS" if not any(i[0] == "FAIL" for v in qa.values() for i in v) else "FAIL"
    print(json.dumps({"status": status, "qa": normalized}, indent=2))


if __name__ == "__main__":
    main()
