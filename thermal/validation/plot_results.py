"""Export the sustained cohort timings and temperatures as scientific figures."""
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
from portable import PACKAGE, SRC, INPUT, RUNTIME, RUNS, VALIDATION, REFERENCE, resolve, warm_state, assert_first_schedule

os.environ.setdefault('MPLCONFIGDIR', '/tmp/moe65_matplotlib')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = RUNS / 'sustained65/fixed12'


def main():
    audit = json.loads((ROOT / 'audit.json').read_text())
    assert audit['status'] == 'PASS_COMPLETE'
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 5.6), sharex=True, constrained_layout=True)
    for name, label, color, marker in [('amber_energy', 'AMBER + same energy OPP', '#2166ac', 'o'),
                                      ('contract_energy', 'Contract + same energy OPP', '#b2182b', 's')]:
        rows = json.loads((ROOT / name / 'cohorts.json').read_text())
        x = [r['cohort'] for r in rows]
        axes[0].plot(x, [r['duration_s'] for r in rows], marker=marker, color=color, label=label, markersize=4)
        axes[1].plot(x, [r['peak_C'] for r in rows], marker=marker, color=color, label=label, markersize=4)
    for ax in axes:
        ax.axvspan(6.5, 12.5, color='#777777', alpha=.10)
        ax.grid(alpha=.22)
        ax.set_xlim(.6, 12.4)
    axes[0].set_ylabel('Time per 4-request cohort (s)')
    axes[0].set_ylim(0, 15)
    axes[0].legend(loc='lower left', frameon=False, fontsize=9)
    axes[0].text(9.1, 1.1, 'Fixed measurement window', ha='center', fontsize=9)
    axes[1].axhline(65, color='black', linestyle='--', linewidth=1, label='65 C cap')
    axes[1].set_ylabel('Peak temperature (C)')
    axes[1].set_ylim(63.9, 65.1)
    axes[1].set_xlabel('Back-to-back cohort number (full thermal state carried)')
    axes[1].set_xticks(range(1, 13))
    axes[1].legend(loc='center right', frameon=False)
    fig.savefig(ROOT / 'sustained_comparison.png', dpi=220)
    fig.savefig(ROOT / 'sustained_comparison.pdf')
    plt.close(fig)


if __name__ == '__main__':
    main()
