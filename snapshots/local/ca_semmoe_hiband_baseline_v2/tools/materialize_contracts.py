"""Materialize current evidence, candidates and non-promotion gates. No model run."""
from pathlib import Path
import collections
import csv
import datetime
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.common import digest, file_hash, require
from core.memory import tensor_bytes
from core.readiness import CAPABILITIES, preflight
from core.reuse import compare_contracts
from models.qwen3 import SPEC as Q3
from models.qwen15 import SPEC as Q15


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    evidence = ROOT / "evidence"
    current = json.loads((evidence / "REMOTE_CURRENT.json").read_text(encoding="utf-8"))
    reuse = json.loads((evidence / "REMOTE_REUSE_AUDIT.json").read_text(encoding="utf-8"))
    contracts = ROOT / "contracts"
    small = {Path(x["path"]).name: x for x in current["qwen3_checkpoint_headers_and_small_files"]
             if x.get("full_sha256")}
    full_path = evidence / "Q3_FULL_CHECKPOINT_HASHES.json"
    full_manifest = json.loads(full_path.read_text(encoding="utf-8")) if full_path.is_file() else None
    content_fingerprint = None
    if full_manifest and full_manifest.get("status") == "COMPLETE_READONLY_SHA256":
        header_files = {Path(x["file"]).name: x["file_bytes"] for x in reuse["q3_tensor_headers"]}
        complete_files = {Path(x["path"]).name: x["bytes"] for x in full_manifest["files"]}
        require(header_files == complete_files, "full hash manifest differs from header/index inventory")
        stats = json.loads((evidence / "Q3_SOURCE_FILE_STATS.json").read_text(encoding="utf-8"))
        observed_before_hash = datetime.datetime.fromisoformat(current["time_utc"]).timestamp()
        require(all(row["mtime_ns"] / 1e9 <= observed_before_hash for row in stats["files"]),
                "checkpoint modified after initial source observation")
        require({row["file"]: row["bytes"] for row in stats["files"]} == header_files,
                "checkpoint size changed during hash")
        content_fingerprint = digest([{"file": Path(row["path"]).name,
                                       "bytes": row["bytes"], "sha256": row["sha256"]}
                                      for row in full_manifest["files"]])
    index = json.loads(small["model.safetensors.index.json"]["text"])
    objects = {}
    errors = []
    for shard in reuse["q3_tensor_headers"]:
        name = Path(shard["file"]).name
        for tensor, data in shard["tensors"].items():
            if tensor in objects:
                errors.append("duplicate tensor:" + tensor)
            size = data["data_offsets"][1] - data["data_offsets"][0]
            require(size == tensor_bytes(data["shape"], data["dtype"]), "header byte/shape mismatch")
            require(index["weight_map"].get(tensor) == name, "index/header shard mismatch")
            objects[tensor] = {"shape": data["shape"], "dtype": data["dtype"], "bytes": size,
                               "file": shard["file"], "offsets": data["data_offsets"],
                               "header_sha256": shard["header_sha256"],
                               "checkpoint_sha256": next((x["sha256"] for x in full_manifest["files"]
                                                           if x["path"] == shard["file"]), None)
                               if content_fingerprint else None}
    require(not errors and set(objects) == set(index["weight_map"]), "tensor index incomplete")
    tensor_total = sum(x["bytes"] for x in objects.values())
    require(index["metadata"]["total_size"] == tensor_total, "index byte total mismatch")
    require(all(x["dtype"] == "BF16" for x in objects.values()), "not original BF16")
    save(contracts / "qwen3_tensor_inventory.json", {"scope": "headers/index and available full shard hashes; not numerical tensor comparison",
         "objects": objects, "tensors": len(objects), "valid_tensor_bytes": tensor_total,
         "full_checkpoint_identity_verified": bool(content_fingerprint),
         "checkpoint_content_manifest_sha256": content_fingerprint})

    precision = {"weights": "BF16", "activations": "BF16",
                 "accumulation": "per-op FP32 candidate; native operation order unverified",
                 "source_gpu_differences": "retained, no tolerance relaxation"}
    old_hashes = {}
    prior = ROOT.parent / "ca_contract_convergence_20261102_v1/SOURCE_COMPARISON.json"
    for item in json.loads(prior.read_text(encoding="utf-8")):
        old_hashes[item["local"]] = item["local_sha256"]
    preserve = [{"path": path, "sha256_before": value, "sha256_now": file_hash(path),
                 "unchanged": file_hash(path) == value} for path, value in old_hashes.items()]
    save(evidence / "HISTORICAL_SOURCE_PRESERVATION.json", preserve)
    require(all(x["unchanged"] for x in preserve), "historical source changed; do not overwrite")
    for name, spec in (("qwen3", Q3), ("qwen15", Q15)):
        contract = {"schema": "ca-composite-contract-2", "state": "PARTIAL_NOT_READY",
                    "model_id": spec["id"], "spec": spec,
                    "precision": precision, "precision_sha256": digest(precision),
                    "checkpoint_content_sha256": content_fingerprint if name == "qwen3" else None,
                    "content_fingerprint_definition": "SHA256 canonical filename/size/full-file-SHA256 manifest",
                    "revision": None, "upstream_revision_verified": False,
                    "content_snapshot_id": ("sha256:" + content_fingerprint)
                    if name == "qwen3" and content_fingerprint else None,
                    "tokenizer_sha256": small["tokenizer.json"]["full_sha256"] if name == "qwen3" else None,
                    "tokenizer_config_sha256": small["tokenizer_config.json"]["full_sha256"] if name == "qwen3" else None,
                    "source_config_sha256": small["config.json"]["full_sha256"] if name == "qwen3" else None,
                    "capacity_candidate": {"host_bytes": 128 * 1024**3, "hb_partitions": 16,
                                           "hb_partition_bytes": 512 * 1024**2},
                    "capacity_verified": False, "costs_verified": False,
                    "runtime": {"binary": None, "libraries": [], "source_build_identity_sha256": None},
                    "capabilities": {key: {"status": "not_verified", "evidence_sha256": None}
                                     for key in CAPABILITIES},
                    "software_reference": {"split_fallback": "rejected", "causal_token_scheduler": True,
                                           "two_gram": False, "collectives": "semantic reference only",
                                           "opcode_lowering": False, "costs": "missing costs rejected"},
                    "native_runs": 0, "author_equivalence": False,
                    "blocker_notes": (["Q3 header/index verified; upstream immutable revision not established",
                                        "existing v7/v8 not inherited as complete admission"] if name == "qwen3" else
                                       ["exact original checkpoint/tokenizer not found in bounded search",
                                        "Chat-GPTQ variant excluded, no substitute"])}
        save(contracts / (name + ".json"), contract)
    save(contracts / "runtime.json", {"state": "UNBOUND_REFUSE_LAUNCH", "binary": None,
         "libraries": [], "schema": "single explicit contract, no inherited launch",
         "clock_domains": {"cpu_tick_ns_candidate": .4, "dram_tick_ns_candidate": 1.25},
         "architecture_tx_bytes_candidate": 256, "pcie_one_way_ns_candidate": 270,
         "parameter_provenance": "historical overlay/launch assumptions, not measured/calibrated",
         "cost_services_missing": True})
    save(contracts / "ca.json", {"name": "CA4-TIME", "reference": "CA4-STRUCT-REF kept separate",
         "page_bytes": 4096, "interval": "successful accept to matched callback, half-open",
         "not_bank_residence": True, "historical_profile_only": True,
         "objective": ["same-bank pair interval overlap", "squared bank byte loads"],
         "seeds": [2026102301, 2026102302, 2026102303], "evaluations_per_seed": 20000,
         "changed_payload_fraction": .1, "native_sidecar_binding": None,
         "decoder": None, "optimizer_reference_only": True})
    save(contracts / "assets.json", {"qwen3_inventory": "qwen3_tensor_inventory.json",
         "qwen3_small_metadata": [{k: v for k, v in x.items() if k != "text"} for x in small.values()],
         "qwen15_search": current["config_search"], "chat_gptq_not_substituted": True,
         "full_tensor_bytes_not_hashed_this_turn": not bool(content_fingerprint)})

    # Full historical-small-metadata audit, not full replay. Precision/workload
    # mismatch alone prohibits reuse as new BF16 composite performance.
    q15_checks = [x for case in reuse["q15_cases"] for x in case["checks"]]
    pair_lookup = {c["case"]: c for c in reuse["q15_cases"]}
    require(len(reuse["q15_cases"]) == 125 and len(reuse["q15_pair_deltas"]) == 25, "old matrix count mismatch")
    require(all(c["status"] == "PASS" and c["completed"] == c["operations"] and
                c["causal_violations"] == 0 for c in reuse["q15_cases"]), "old completion metadata failed")
    require(all(p["paired"] and p["delta"] == 0 for p in reuse["q15_pair_deltas"]), "counterfactual differs")
    unexpected = [x for x in q15_checks if x["status"] not in ("MATCH", "HASHED_NO_EXPECTED")]
    old_new = compare_contracts({"model_id": Q15["id"], "precision_sha256": "historical-ideal-W4-proxy"},
                                {"model_id": Q15["id"], "precision_sha256": digest(precision)})
    local_provenance = json.loads((ROOT.parent / "qwen3_30b_a3b_v3_6_experiment/figure_evidence/strict_bank_v2/provenance.json").read_text())
    actual = {x["path"]: x.get("sha256") for c in reuse["q3_pairs"] for x in c["checks"] if x.get("sha256")}
    supplement_path = evidence / "Q3_PARENT_AUDIT.json"
    if supplement_path.is_file():
        supplement = json.loads(supplement_path.read_text(encoding="utf-8"))
        actual[supplement["path"]] = supplement["sha256"]
    q3match = []
    prefix = "/mnt/sda1/h3240101068/qwen3_30b_a3b_v3_6_experiment/"
    for name, inputs in local_provenance["inputs"].items():
        meta = [{"path": path, "expected": value, "actual": actual.get(prefix + path),
                 "match": actual.get(prefix + path) == value}
                for path, value in inputs.items() if not path.endswith("bank_requests.csv")]
        q3match.append({"case": name, "small_metadata": meta,
                        "all_small_metadata_match": all(x["match"] for x in meta),
                        "bank_raw_deferred": True, "new_cycles_reuse": False})
    reuse_result = {"status": "CLASSIFICATION_COMPLETE_HISTORICAL_SCOPED",
         "q15_cases": 125, "q15_pairs": 25, "q15_pair_deltas_zero": True,
         "q15_small_checks": dict(collections.Counter(x["status"] for x in q15_checks)),
         "q15_unexpected_checks": unexpected, "q15_new_cycle_reuse": old_new,
         "q3_remote_pair_roots": len(reuse["q3_pairs"]), "q3_frozen_seven": q3match,
         "raw_transaction_payloads_reaudited": False,
         "conclusion": "old methods and bounded historical negatives reusable; no old cycles promoted to new BF16 contract"}
    save(evidence / "REUSE_DECISIONS.json", reuse_result)
    searches = {}
    for name in ("LOCAL_MODEL_SEARCH", "REMOTE_MODEL_SEARCH", "REMOTE_MODEL_SEARCH_TARGETED"):
        path = evidence / (name + ".json")
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8"))
            searches[name] = {"status": value["status"], "visited_directories": value["visited_directories"],
                              "configs_read": value["configs_read"], "roots": value["roots"],
                              "candidates": value["candidates"], "not_global_absence_proof": True}
    save(contracts / "original_model_search.json", {"qwen15_original_found": False,
         "searches": searches, "chat_gptq_substitution": False,
         "action": "retain missing-asset blocker; no download authorized or started"})
    save(contracts / "gates.json", {name: preflight(json.loads((contracts / (name + ".json")).read_text(encoding="utf-8")))
                                    for name in ("qwen3", "qwen15")})

    rows = []
    for prefix, count in (("Q3", 6), ("Q15", 7), ("C", 7)):
        for i in range(1, count + 1):
            key = "%s-%02d" % (prefix, i)
            rows.append({"id": key, "software_status": "REFERENCE_IMPLEMENTED",
                         "native_status": "NOT_INTEGRATED", "native_evidence": "",
                         "scope": "see core/, models/ and SOFTWARE_CHECKS; not target admission"})
    # Declare precisely what reference modules do not implement.
    for row in rows:
        if row["id"] in ("Q3-04", "Q15-04", "Q15-05", "C-01", "C-04"):
            row["software_status"] = "PARTIAL_INTERFACE_ONLY"
        if row["id"] == "C-07":
            row["software_status"] = "IMPLEMENTED_IDENTITY_CLASSIFICATION"
            row["native_status"] = "NOT_APPLICABLE_NO_REPLAY"
    with (ROOT / "IMPLEMENTATION_STATUS.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"q3_tensors": len(objects), "q3_valid_bytes": tensor_total,
                      "q15_checks": reuse_result["q15_small_checks"],
                      "q3_small_frozen_matches": sum(x["all_small_metadata_match"] for x in q3match),
                      "old_sources_unchanged": len(preserve), "formal_ready": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
