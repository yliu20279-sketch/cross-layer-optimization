#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
V35 = ROOT.parent / "target_architecture_v3_5"

arch = yaml.safe_load((ROOT / "target_architecture_v3_6.yaml").read_text(encoding="utf-8-sig"))
addr = json.loads((ROOT / "address_mapping.json").read_text(encoding="utf-8-sig"))
npu = json.loads((ROOT / "npusim_cluster_v3_6.json").read_text(encoding="utf-8-sig"))
ram = yaml.safe_load((ROOT / "ramulator2_hb_partition_v3_6.yaml").read_text(encoding="utf-8-sig"))
prov = json.loads((ROOT / "PROVENANCE_V3_6.json").read_text(encoding="utf-8-sig"))
qwen = json.loads((ROOT / "qwen3_w4a16_capacity_profile.json").read_text(encoding="utf-8-sig"))
thermal = json.loads((ROOT / "thermal_stack_v3_6.json").read_text(encoding="utf-8-sig"))
tile = json.loads((ROOT / "tile_memory_noc_mapping_v3_6.json").read_text(encoding="utf-8-sig"))
deepstack = json.loads((ROOT / "deepstack_bank_oracle_v3_6.json").read_text(encoding="utf-8-sig"))
hb = json.loads((ROOT / "hb_link_model.json").read_text(encoding="utf-8-sig"))

checks = {}

def check(name, condition, detail):
    checks[name] = {"pass": bool(condition), "detail": detail}

check("schema_3_6", float(arch["schema_version"]) == 3.6, arch["schema_version"])
check("component_schemas_3_6", thermal["schema_version"].startswith("3.6") and tile["schema_version"] == "3.6" and deepstack["schema_version"].startswith("3.6") and hb["schema_version"].startswith("3.6"), {"thermal": thermal["schema_version"], "tile": tile["schema_version"], "deepstack": deepstack["schema_version"], "hb": hb["schema_version"]})
check("not_execution_validated", arch["execution_ready"] is False and arch["execution_validation"]["status"] == "NOT_RUN", arch["status"])
check("total_capacity_8_gib", arch["hb_dram"]["total_capacity_mib"] == 8192, arch["hb_dram"]["total_capacity_mib"])
check("per_partition_512_mib", arch["hb_dram"]["capacity_mib_per_partition"] == 512, arch["hb_dram"]["capacity_mib_per_partition"])
check("capacity_arithmetic", arch["hb_dram"]["total_capacity_mib"] == arch["hb_dram"]["partitions"] * arch["hb_dram"]["capacity_mib_per_partition"], arch["hb_dram"])
check("address_total_8_gib", addr["total_bytes"] == 8 * 1024**3, addr["total_bytes"])
check("address_partition_512_mib", addr["partition_bytes"] == 512 * 1024**2, addr["partition_bytes"])
check("address_selector_updated", addr["partition_selection"] == "address[32:29]", addr["partition_selection"])
check("sixteen_contiguous_ranges", len(addr["partition_ranges"]) == 16 and all(r["base"] == i * addr["partition_bytes"] and r["limit_exclusive"] == (i + 1) * addr["partition_bytes"] for i, r in enumerate(addr["partition_ranges"])), len(addr["partition_ranges"]))
check("last_range_ends_at_total", addr["partition_ranges"][-1]["limit_exclusive"] == addr["total_bytes"], addr["partition_ranges"][-1])
check("npu_capacity_matches", npu["external_memory"]["size_bytes_per_client"] == addr["partition_bytes"] and npu["external_memory"]["region_bytes"] == addr["partition_bytes"], npu["external_memory"])
check("ramulator_capacity_matches", ram["metadata"]["capacity_bytes_per_instance"] == addr["partition_bytes"], ram["metadata"]["capacity_bytes_per_instance"])
check("ramulator_row_depth_doubled", ram["memory_system"]["controllers"][0]["dram"]["org"]["count"] == [1, 1, 4, 4, 16384, 1024], ram["memory_system"]["controllers"][0]["dram"]["org"]["count"])
check("decoded_banks_unchanged", ram["metadata"]["decoded_banks_per_partition"] == 16, ram["metadata"]["decoded_banks_per_partition"])
check("hb_bandwidth_unchanged", arch["hybrid_bonding"]["hb_io_bandwidth_GBps_per_pe"] == 25.6, arch["hybrid_bonding"]["hb_io_bandwidth_GBps_per_pe"])
check("qwen_theoretical_headroom_positive", qwen["minimum_unallocated_bytes_before_quant_metadata_and_runtime"] > 0, qwen["minimum_unallocated_bytes_before_quant_metadata_and_runtime"])

current_hashes = {name: hashlib.sha256((V35 / name).read_bytes()).hexdigest() for name in prov["source_hashes"]}
check("v3_5_sources_unchanged", current_hashes == prov["source_hashes"], {"files": len(current_hashes)})

status = "PASS" if all(x["pass"] for x in checks.values()) else "FAIL"
result = {"schema_version": "3.6-selfcheck-1.0", "status": status, "checks": checks}
(ROOT / "V3_6_SELFCHECK.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if status == "PASS" else 1)
