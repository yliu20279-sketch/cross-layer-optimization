"""Audit recorded runs and derive hardware-only generic cell counts.

This reads existing artifacts; it does not resynthesize or modify raw results.
"""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    subprocess.run([sys.executable, str(ROOT / "check_artifacts.py")], check=True)
    status = read_json(ROOT / "build/synth/synthesis_status.json")
    assert status["status"] == "passed_generic_synthesis"
    assert status["process_library"] is None and status["area_um2"] is None
    assert status["timing_closed"] is False and status["application_performance"] is False
    for name, digest in status["source_sha256"].items():
        assert sha(ROOT / name) == digest, name
    for name in ("pipeline.exit", "final_checks.exit"):
        assert (ROOT / "build" / name).read_text().strip() == "0", name

    wheels = status["tool_wheel_sha256"]
    present = [name for name in wheels if (ROOT / "tools/wheels" / name).is_file()]
    # The local evidence copy need not contain the private remote tool install.
    assert not present or len(present) == len(wheels), "incomplete wheel set"
    for name in present:
        assert sha(ROOT / "tools/wheels" / name) == wheels[name], name

    summary = {
        "audit_host": platform.node(),
        "audit_utc": datetime.now(timezone.utc).isoformat(),
        "synthesis_host": status["host"],
        "tool_version": status["tool_version"].strip(),
        "source_hashes_verified": len(status["source_sha256"]),
        "wheel_hashes_recorded": len(wheels),
        "wheel_hashes_verified_here": len(present),
        "process_library": None,
        "area_um2": None,
        "timing_closed": False,
        "application_performance": False,
        "metadata_excluded": ["$scopeinfo"],
        "metadata_reference": "https://yosyshq.readthedocs.io/projects/yosys/en/docs-preview-ci/cmd/index_passes_hierarchy.html",
        "tops": {},
    }
    for top, record in status["tops"].items():
        assert record["passed"] and record["returncode"] == 0, top
        for suffix, field in (("stat.json", "stat_sha256"), ("netlist.json", "netlist_sha256"),
                              ("netlist.v", "verilog_sha256"), ("log", "log_sha256"),
                              ("ys", "script_sha256")):
            assert sha(ROOT / "build/synth" / (top + "." + suffix)) == record[field], (top, field)
        cells = read_json(ROOT / "build/synth" / (top + ".netlist.json"))["modules"][top]["cells"]
        counts = Counter(cell["type"] for cell in cells.values())
        assert dict(counts) == record["cell_types"]
        assert len(cells) == record["generic_cells"]
        assert all(t == "$scopeinfo" or t.startswith("$_") for t in counts), counts
        assert not any("LATCH" in t.upper() for t in counts), top
        hardware = len(cells) - counts.get("$scopeinfo", 0)
        flip_flops = sum(n for t, n in counts.items() if "DFF" in t)
        log = (ROOT / "build/synth" / (top + ".log")).read_text(encoding="utf-8")
        assert "Found 0 SCCs" in log, top
        script = (ROOT / "build/synth" / (top + ".ys")).read_text(encoding="utf-8")
        assert "check -assert" in script and "scc -expect 0" in script
        summary["tops"][top] = {
            "raw_cell_objects": len(cells),
            "scope_metadata_objects": counts.get("$scopeinfo", 0),
            "hardware_generic_cells": hardware,
            "flip_flop_cells": flip_flops,
            "combinational_cells": hardware - flip_flops,
            "latch_cells": 0,
            "combinational_sccs": 0,
        }

    nettests = read_json(ROOT / "build/netlist_tests/verification.json")
    assert nettests["all_passed"] and set(nettests["tests"]) == {"router", "cs"}
    for name, test in nettests["tests"].items():
        assert test["passed"], name
        for path, digest in test["sha256"].items():
            assert sha(ROOT / path) == digest, path
        log = (ROOT / "build/netlist_tests" / (name + "_simulation.log")).read_text(encoding="utf-8")
        assert log.strip() == test["output"] and "PASS" in log and "FATAL" not in log
    summary["netlist_regression"] = {name: t["output"] for name, t in nettests["tests"].items()}
    before = summary["tops"]["router_local_top"]
    after = summary["tops"]["router_aux_top"]
    summary["aux_delta"] = {key: after[key] - before[key] for key in
                            ("hardware_generic_cells", "flip_flop_cells", "combinational_cells")}
    previous = ROOT.parent / "noc_aux_port_20261104/rtl"
    if previous.is_dir():
        files = sorted((ROOT / "rtl").glob("*.sv"))
        assert all(sha(p) == sha(previous / p.name) for p in files), "RTL snapshot changed"
        summary["previous_rtl_identical_files"] = len(files)
    output = ROOT / "build/generic_summary.json"
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("PASS synthesis/netlist artifact audit; raw results unchanged")


if __name__ == "__main__":
    main()
