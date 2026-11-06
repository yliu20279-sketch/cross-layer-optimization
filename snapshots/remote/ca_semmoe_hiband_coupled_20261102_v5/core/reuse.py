"""Reuse is about artifact identity, never about whether the result is positive."""
from .common import require

FIELDS = ("model_id", "checkpoint_content_sha256", "tokenizer_sha256", "precision_sha256",
          "binary_sha256", "libraries_sha256", "configuration_sha256", "dag_sha256",
          "input_sha256", "initial_state_sha256", "timing_contract_sha256", "intervention_sha256")


def compare_contracts(old, new):
    missing = [name for name in FIELDS if not old.get(name) or not new.get(name)]
    differences = [name for name in FIELDS if old.get(name) and new.get(name) and old[name] != new[name]]
    exact = not missing and not differences
    return {"level": "MATCHED_CYCLES" if exact else "HISTORICAL_SCOPED_ONLY",
            "cycle_reuse_allowed": exact, "missing": missing, "differences": differences}


def verify_manifest(records, actual_hashes):
    require(records, "empty manifest")
    seen, failures = set(), []
    for row in records:
        path = row["path"]
        require(path not in seen, "duplicate manifest path")
        seen.add(path)
        if not row.get("sha256") or actual_hashes.get(path) != row["sha256"]:
            failures.append(path)
    return {"pass": not failures, "checked": len(records), "failures": failures}
