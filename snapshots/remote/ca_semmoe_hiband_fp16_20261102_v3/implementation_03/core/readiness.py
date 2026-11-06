"""Fail closed: schema/semantic-reference success is not target admission."""
from pathlib import Path
from .common import file_hash

IDENTITY = ("checkpoint_content_sha256", "tokenizer_sha256", "precision_sha256")
CAPABILITIES = ("native_sem_moe_schedule", "native_srs_sag", "full_operator_lowering",
                "actual_bf16_memory_io", "full_capacity_lifetimes", "cpu_costs",
                "cache_version_services", "hiband_controls_and_timing", "ca_native_address_binding")


def preflight(contract):
    blockers = []
    for field in IDENTITY:
        if not contract.get(field):
            blockers.append("identity:" + field)
    # Immutable local content identity is distinct from an upstream commit.
    # This does not relax any native numerical, timing or cost requirement.
    if not contract.get("revision") and not contract.get("content_snapshot_id"):
        blockers.append("identity:immutable_snapshot")
    for name in CAPABILITIES:
        item = contract.get("capabilities", {}).get(name, {})
        if item.get("status") != "verified" or not item.get("evidence_sha256"):
            blockers.append("capability:" + name)
        else:
            evidence = Path(item.get("evidence_path", ""))
            if not evidence.is_file() or file_hash(evidence) != item["evidence_sha256"]:
                blockers.append("capability:evidence_missing_or_changed:" + name)
    runtime = contract.get("runtime", {})
    if not runtime.get("binary") or not runtime.get("libraries") or not runtime.get("source_build_identity_sha256"):
        blockers.append("runtime:incomplete")
    for item in ([runtime["binary"]] if runtime.get("binary") else []) + runtime.get("libraries", []):
        path = Path(item.get("path", ""))
        if not path.is_file() or not item.get("sha256") or file_hash(path) != item["sha256"]:
            blockers.append("runtime:artifact_missing_or_changed")
    if not contract.get("capacity_verified"):
        blockers.append("capacity:unverified")
    if not contract.get("costs_verified"):
        blockers.append("costs:unverified")
    return {"model_id": contract["model_id"], "ready": not blockers,
            "blockers": blockers, "native_runs": 0, "p0_2_started": False}
