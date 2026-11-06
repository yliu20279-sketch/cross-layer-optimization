#!/usr/bin/env python3
"""Materialize V3.6 as a non-destructive 8 GiB fork of V3.5."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml


HERE = Path(__file__).resolve().parent
V35 = HERE.parent / "target_architecture_v3_5"
MIB = 1024 * 1024
PARTITIONS = 16
PARTITION_MIB = 512
PARTITION_BYTES = PARTITION_MIB * MIB
TOTAL_MIB = PARTITIONS * PARTITION_MIB


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_version(value):
    if isinstance(value, dict):
        return {k: replace_version(v) for k, v in value.items()}
    if isinstance(value, list):
        return [replace_version(v) for v in value]
    if isinstance(value, str):
        return value.replace("V3.5", "V3.6").replace("v3_5", "v3_6").replace("v3.5", "v3.6")
    return value


def build_architecture():
    arch = yaml.safe_load((V35 / "target_architecture_v3_5.yaml").read_text(encoding="utf-8-sig"))
    arch = replace_version(arch)
    arch["schema_version"] = 3.6
    arch["status"] = "CONFIGURATION_READY_EXECUTION_NOT_VALIDATED"
    arch["execution_ready"] = False
    arch["execution_candidate_ready"] = True
    arch["execution_scope"] = "QWEN3_8B_W4A16_capacity_enabled_NoC_plus_DeepStack_DRAM_without_absolute_thermal_claims"
    arch["execution_validation"] = {
        "status": "NOT_RUN",
        "source_validation": "V3.5 results are provenance only and are not V3.6 execution evidence",
        "required": [
            "static configuration self-check",
            "Ramulator2 512 MiB per-partition address coverage",
            "NPUSim external-memory boundary test",
            "Qwen3 operator-graph byte conservation",
            "HB and NoC bandwidth sensitivity",
        ],
    }
    arch["provenance"]["architecture_baseline"] = "target_architecture_v3_5"
    arch["provenance"]["v3_5_architecture_parameters_reused"] = True
    arch["provenance"]["v3_6_delta"] = "HB-DRAM capacity doubled from 4 GiB to 8 GiB by doubling per-partition row depth"
    arch["hb_dram"]["total_capacity_mib"] = TOTAL_MIB
    arch["hb_dram"]["capacity_mib_per_partition"] = PARTITION_MIB
    arch["hb_dram"]["capacity_change_from_v3_5"] = {
        "old_total_mib": 4096,
        "old_per_partition_mib": 256,
        "new_total_mib": TOTAL_MIB,
        "new_per_partition_mib": PARTITION_MIB,
        "changed_dimension": "row_depth_only",
        "logical_banks_per_partition_unchanged": True,
        "bandwidth_unchanged": True,
    }
    arch["thermal_stack"]["canonical_file"] = "thermal_stack_v3_6.json"
    (HERE / "target_architecture_v3_6.yaml").write_text(
        yaml.safe_dump(arch, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def build_address_mapping():
    source = read_json(V35 / "address_mapping.json")
    ranges = []
    for i in range(PARTITIONS):
        ranges.append({
            "id": f"CH{i}",
            "base": i * PARTITION_BYTES,
            "limit_exclusive": (i + 1) * PARTITION_BYTES,
            "banks": [f"B{4*i+j}" for j in range(4)],
        })
    source.update({
        "schema_version": "3.6",
        "total_bytes": PARTITIONS * PARTITION_BYTES,
        "partition_bytes": PARTITION_BYTES,
        "partition_selection": "address[32:29]",
        "partition_ranges": ranges,
        "note": "16 disjoint 512 MiB partitions; four logical projected banks per partition; row/column fields are owned by Ramulator2.",
    })
    write_json(HERE / "address_mapping.json", source)


def build_npu_config():
    cfg = replace_version(read_json(V35 / "npusim_cluster_v3_5.json"))
    cfg["schema_version"] = "3.6"
    cfg["npu"]["topology"]["graph"] = "noc_v3_6.gv"
    cfg["external_memory"]["size_bytes_per_client"] = PARTITION_BYTES
    cfg["external_memory"]["region_bytes"] = PARTITION_BYTES
    cfg["external_memory"]["capacity_change"] = "V3.6 doubles addressable rows; transaction size, banks and bandwidth are unchanged"
    cfg["implementation_status"] = {
        "recognized_by_current_npusim_without_changes": False,
        "reason": "V3.6 capacity and Qwen3 W4A16 lowering require boundary and mixed-precision validation before execution claims.",
    }
    write_json(HERE / "npusim_cluster_v3_6.json", cfg)


def build_ramulator_config():
    text = (V35 / "ramulator2_hb_partition_v3_5.yaml").read_text(encoding="utf-8-sig")
    text = text.replace("= 256 MiB/partition", "= 512 MiB/partition")
    text = text.replace("count: [1, 1, 4, 4, 8192, 1024]", "count: [1, 1, 4, 4, 16384, 1024]")
    text = text.replace("schema_version: 3.5", "schema_version: 3.6")
    text = text.replace("capacity_bytes_per_instance: 268435456", f"capacity_bytes_per_instance: {PARTITION_BYTES}")
    text += "  capacity_delta_from_v3_5: row count doubled from 8192 to 16384; decoded banks and timing unchanged\n"
    (HERE / "ramulator2_hb_partition_v3_6.yaml").write_text(text, encoding="utf-8")


def adapt_copied_files():
    for old_name, new_name in [
        ("thermal_stack_v3_5.json", "thermal_stack_v3_6.json"),
        ("tile_memory_noc_mapping_v3_5.json", "tile_memory_noc_mapping_v3_6.json"),
        ("deepstack_bank_oracle_v3_5.json", "deepstack_bank_oracle_v3_6.json"),
        ("hb_link_model.json", "hb_link_model.json"),
    ]:
        obj = replace_version(read_json(V35 / old_name))
        schema_overrides = {
            "thermal_stack_v3_6.json": "3.6-thermal-1.0",
            "tile_memory_noc_mapping_v3_6.json": "3.6",
            "deepstack_bank_oracle_v3_6.json": "3.6-deepstack-bank-1.0",
            "hb_link_model.json": "3.6-hb-link-1.0",
        }
        obj["schema_version"] = schema_overrides[new_name]
        if new_name == "tile_memory_noc_mapping_v3_6.json":
            obj["scope"] = "workload-independent architecture contract; Qwen3-8B mapping candidate"
            obj["bank_address_mapping"]["partition_selection"] = "address[32:29]"
            obj["bank_address_mapping"]["status"] = "V3.6_static_mapping_updated_runtime_verification_pending"
        write_json(HERE / new_name, obj)

    graph = (V35 / "noc_v3_5.gv").read_text(encoding="utf-8-sig")
    graph = graph.replace("whisper_v3_5_noc", "qwen3_v3_6_noc")
    (HERE / "noc_v3_6.gv").write_text(graph, encoding="utf-8")


def write_provenance():
    source_files = [
        "target_architecture_v3_5.yaml", "address_mapping.json", "npusim_cluster_v3_5.json",
        "ramulator2_hb_partition_v3_5.yaml", "thermal_stack_v3_5.json",
        "tile_memory_noc_mapping_v3_5.json", "deepstack_bank_oracle_v3_5.json",
        "hb_link_model.json", "clock_domain_mapping.json", "pcie_dma_model.json", "noc_v3_5.gv",
    ]
    provenance = {
        "schema_version": "3.6-provenance-1.0",
        "parent": "target_architecture_v3_5",
        "creation_policy": "non-destructive fork; parent files are not modified",
        "capacity_delta": {
            "total_mib": {"v3_5": 4096, "v3_6": TOTAL_MIB},
            "per_partition_mib": {"v3_5": 256, "v3_6": PARTITION_MIB},
            "ramulator_rows": {"v3_5": 8192, "v3_6": 16384},
            "partition_address_bits": {"v3_5": "address[31:28]", "v3_6": "address[32:29]"},
        },
        "unchanged_by_design": [
            "16 NPU clusters", "16 HB-DRAM partitions", "four logical projected banks per partition",
            "Ramulator decoded-bank organization", "25.6 GB/s per vertical link", "4x4 PopNet topology",
            "NoC width and latency", "NPU compute and SRAM parameters", "thermal evidence boundary",
        ],
        "source_hashes": {name: sha256(V35 / name) for name in source_files},
        "execution_status": "NOT_RUN",
        "prohibition": "Do not reuse V3.5 PASS results as V3.6 validation evidence.",
    }
    write_json(HERE / "PROVENANCE_V3_6.json", provenance)


def write_qwen_capacity_profile():
    exact_params = 8_190_427_136
    kv_fp16_4096 = 36 * 4096 * 2 * 8 * 128 * 2
    profile = {
        "schema_version": "3.6-qwen3-capacity-1.0",
        "model": "Qwen/Qwen3-8B",
        "target_quantization": "W4A16",
        "capacity_bytes": TOTAL_MIB * MIB,
        "ideal_int4_weight_bytes": (exact_params + 1) // 2,
        "kv_cache_fp16_bytes_context_4096": kv_fp16_4096,
        "minimum_unallocated_bytes_before_quant_metadata_and_runtime": TOTAL_MIB * MIB - ((exact_params + 1) // 2) - kv_fp16_4096,
        "status": "CAPACITY_ENABLED_WITH_HEADROOM_VALIDATION_REQUIRED",
        "requirements": [
            "measure serialized W4 scale and zero-point bytes",
            "reserve per-cluster activation and collective buffers",
            "validate peak rather than average partition occupancy",
            "reject mapping if any 512 MiB partition overflows",
        ],
    }
    write_json(HERE / "qwen3_w4a16_capacity_profile.json", profile)


def main():
    build_architecture()
    build_address_mapping()
    build_npu_config()
    build_ramulator_config()
    adapt_copied_files()
    write_provenance()
    write_qwen_capacity_profile()


if __name__ == "__main__":
    main()
