import csv
import re
from pathlib import Path

root = Path(__file__).resolve().parent
rows = []
for arm, design in enumerate(("mesh", "mesh_cs")):
    mapping = (root / f"map_{arm}.log").read_text()
    area, = re.findall(r"Chip area for module .*?: ([\d.]+)", mapping)
    for stage, log in (("asic_synthesis", f"synth_timing_power_{arm}.log"),
                       ("placement_rc_estimate", f"placement_estimate_{arm}.log"),
                       ("asic_postroute", f"extracted_{arm}.log")):
        report_path = root / log
        if not report_path.exists():
            continue
        report = report_path.read_text()
        if stage == "asic_postroute":
            if not (root / f"route_{arm}.spef").is_file() or f"PASS_PHYSICAL {arm}" not in report:
                continue
        if stage == "placement_rc_estimate" and f"PASS_PLACEMENT_ESTIMATE {arm}" not in report:
            continue
        if stage != "asic_synthesis":
            area, = re.findall(r"Design area\s+(\d+(?:\.\d+)?)", report)
        drc = ""
        if stage == "asic_postroute":
            drc_path = root / f"drc_{arm}.rpt"
            if not drc_path.exists():
                raise ValueError(f"Missing detailed-route DRC report: {drc_path}")
            drc = len(re.findall(r"(?m)^violation type:", drc_path.read_text()))
        slack = re.findall(r"(?m)^worst slack\s+(-?[\d.]+)", report)
        power = re.findall(r"(?m)^Total\s+([\deE+.-]+)\s+([\deE+.-]+)\s+([\deE+.-]+)\s+([\deE+.-]+)", report)
        if not slack or len(power) != 1:
            raise ValueError(f"Incomplete timing or power report: {log}")
        internal, switching, leakage, total = map(float, power[0])
        rows.append((stage, design, area, 1.000, slack[0],
                     slack[1] if len(slack) > 1 else "", f"{internal + switching:.3g}",
                     f"{leakage:.3g}", f"{total:.3g}", "0.10", "0.50", drc, log))
with (root / "TABLE_V_NANGATE45.csv").open("w", newline="") as stream:
    writer = csv.writer(stream)
    writer.writerow(("stage", "design", "std_cell_area_um2", "clock_period_ns",
                     "setup_wns_ns", "hold_wns_ns", "dynamic_W", "leakage_W", "total_W",
                     "vectorless_activity", "duty", "router_drc_markers", "report"))
    writer.writerows(rows)

