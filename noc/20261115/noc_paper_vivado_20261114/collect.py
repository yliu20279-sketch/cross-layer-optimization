"""Extract paired results from Vivado reports, without treating OOC timing as board Fmax."""
from pathlib import Path
import csv
import re

root = Path(__file__).resolve().parent
rows = []
for arm in (0, 1):
    for stage in ("synth", "route"):
        directory = root / f"onehot_reports_{arm}"
        utilization = directory / f"utilization_{stage}.rpt"
        timing = directory / f"timing_{stage}.rpt"
        if not utilization.exists() or not timing.exists():
            continue
        utilization_text = utilization.read_text(encoding="ascii", errors="replace")
        timing_text = timing.read_text(encoding="ascii", errors="replace")
        counts = []
        for label in ("CLB LUTs", "CLB Registers", "Block RAM Tile", "DSPs"):
            match = re.search(rf"^\|\s*{label}\*?\s*\|\s*([\d.]+)", utilization_text, re.M)
            if not match:
                raise ValueError(f"{label} missing in {utilization}")
            counts.append(match[1])
        match = re.search(r"^noc_clk\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)", timing_text, re.M)
        if not match:
            raise ValueError(f"Clock summary missing in {timing}")
        wns, tns = match.groups()
        estimate = round(1000 / (5 - float(wns)), 1)
        rows.append((stage, ("mesh", "mesh_cs")[arm], *counts, "5.000", wns, tns, estimate))
with (root / "TABLE_V_FPGA.csv").open("w", newline="") as output:
    writer = csv.writer(output)
    writer.writerow(("stage", "configuration", "LUT", "FF", "BRAM_tile", "DSP",
                     "constraint_ns", "WNS_ns", "TNS_ns", "internal_setup_estimate_MHz"))
    writer.writerows(rows)
