#!/usr/bin/env python3
"""Run/resume the 60 trace-driven coupled LegoSim cases."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--legosim-root", type=Path, required=True)
    ap.add_argument("--deepstack-root", type=Path, required=True)
    ap.add_argument("--deepstack-python", type=Path, required=True)
    ap.add_argument("--graphs", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--only", help="optional comma-separated case names")
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args()
    here = Path(__file__).resolve().parent
    suite = args.legosim_root / "benchmark/whisper_operator_inventory/hiband_whisper_migration/step7_closure_cmd006"
    binary = suite / "popnet_coupled_src/build_coupled/popnet"
    os.environ.update({
        "HB_EXECUTABLE": str(binary),
        "HB_RAM_CONFIG_TEMPLATE": str(here / "target_architecture_v3_6/ramulator2_hb_partition_v3_6_execution_overlay.yaml"),
        "HB_RAM_BASE_CHANNEL_WIDTH": "128",
        "HB_RAM_BASE_ROWS": "16384",
        "HB_ARCH_TX_BYTES": "256",
        "HB_BASE_BYTES_PER_CYCLE": "25.6",
        "DEEPSTACK_ROOT": str(args.deepstack_root),
        "DEEPSTACK_PYTHON": str(args.deepstack_python),
        "HB_DEEPSTACK_CONFIG": str(here / "target_architecture_v3_6/deepstack_bank_oracle_v3_6_execution_overlay.json"),
    })
    sys.path.insert(0, str(suite))
    import run_suite

    requested = set(args.only.split(",")) if args.only else None
    cases = []
    for concurrency in (1, 2, 4, 8, 16):
        for repeat in (1, 2, 3):
            for scheme in ("baseline_ep", "hiband", "sem_moe", "hiband_sem_moe"):
                name = f"c{concurrency}_rep{repeat}_{scheme}"
                if requested is None or name in requested:
                    controls = {} if scheme in ("hiband", "hiband_sem_moe") else {"HB_FIXED_MODE": "GLOBAL_BIAS"}
                    graph = args.graphs / f"c{concurrency}" / f"rep{repeat}" / scheme
                    cases.append((name, graph, controls))
    args.out.mkdir(parents=True, exist_ok=True)
    def execute(item):
        index, (name, graph, controls) = item
        print(json.dumps({"starting": name, "index": index, "total": len(cases)}), flush=True)
        result = run_suite.run(args.out, name, graph, controls)
        attr_path = args.out / name / "critical_path_attribution.json"
        subprocess.run([
            sys.executable, str(here / "critical_path_attribution.py"),
            "--graph", str(graph), "--run", str(args.out / name), "--out", str(attr_path),
        ], check=True)
        result["attribution"] = json.loads(attr_path.read_text())["components"]
        return result

    indexed = list(enumerate(cases, 1))
    if args.workers == 1:
        results = [execute(item) for item in indexed]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(execute, indexed))
    summary = {
        "status": "PASS", "cases": len(results), "results": results,
        "binary_sha256": sha256(binary),
        "graphs_manifest_sha256": sha256(args.graphs / "matrix_manifest.json"),
        "scheme_contract": {
            "baseline_ep": "round-robin expert placement + static GLOBAL_BIAS bandwidth split",
            "hiband": "round-robin expert placement + dynamic HiBand mode selection",
            "sem_moe": "profile-learned expert placement + static GLOBAL_BIAS bandwidth split",
            "hiband_sem_moe": "profile-learned expert placement + dynamic HiBand mode selection",
        },
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "cases": len(results)}, indent=2))


if __name__ == "__main__":
    main()
