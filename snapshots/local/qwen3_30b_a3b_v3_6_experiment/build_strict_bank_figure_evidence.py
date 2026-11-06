#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path


CASES = (
    ("c2-fixed", "ctx128", "c2", "fixed", "512", "results/strict_ctx128_c2_owner_shadow_pairs_v1/hiband_sem_moe", "results/strict_ctx128_c2_owner_shadow_pairs_v1/paired_audit.json"),
    ("c4-fixed", "ctx128", "c4", "fixed", "512", "results/strict_ctx128_c4_hsm_owner_shadow_pair_v1", None),
    ("c8-fixed", "ctx128", "c8", "fixed", "512", "results/strict_ctx128_c8_hsm_owner_shadow_pair_postfix_v1", None),
    ("c8-cap768", "ctx128", "c8", "fixed", "768", "results/sensitivity_ctx128_c8_hsm_cap768_pair_v1", None),
    ("c8-cap1024", "ctx128", "c8", "fixed", "1024", "results/sensitivity_ctx128_c8_hsm_cap1024_pair_v1", None),
    ("c8-high-skew", "ctx128", "c8", "exploratory_high_skew", "512", "results/exploratory_ctx128_c8_hsm_high_skew_pair_v1", None),
    ("ctx512-c8-high-skew", "ctx512", "c8", "exploratory_high_skew", "512", "results/exploratory_ctx512_c8_hsm_high_skew_pair_v1", None),
)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    summary = []
    distribution = []
    provenance = {"schema": "strict-bank-figure-evidence-v1", "inputs": {}}
    for label, context, concurrency, route_policy, capacity, relative, audit_relative in CASES:
        pair = args.root / relative
        normal_validation = pair / "normal" / "validation.json"
        oracle_validation = pair / "oracle" / "validation.json"
        paired_audit = args.root / audit_relative if audit_relative else pair / "paired_audit.json"
        bank_requests = pair / "normal" / "bank_requests.csv"
        for path in (normal_validation, oracle_validation, paired_audit, bank_requests):
            if not path.is_file():
                raise FileNotFoundError(path)
        normal = read_json(normal_validation)
        oracle = read_json(oracle_validation)
        audit = read_json(paired_audit)
        if normal["status"] != "PASS" or oracle["status"] != "PASS" or audit["status"] != "PASS":
            raise RuntimeError(f"unvalidated case: {label}")
        total = int(normal["total_cycles"])
        conflict = total - int(oracle["total_cycles"])
        summary.append({
            "case": label,
            "context": context,
            "concurrency": concurrency,
            "route_policy": route_policy,
            "partition_capacity_mib": capacity,
            "total_cycles": total,
            "bank_conflict_cycles": conflict,
            "other_cycles": total - conflict,
            "bank_conflict_fraction": conflict / total,
            "page_misses": int(normal["page_misses"]),
            "interpretation": "negative_oracle_effect" if conflict < 0 else "positive_oracle_sensitivity",
        })
        aggregates = defaultdict(lambda: {"transactions": 0, "strict_wait_ticks": 0, "queue_ticks": 0})
        with bank_requests.open(newline="") as handle:
            for row in csv.DictReader(handle):
                key = tuple(int(row[name]) for name in ("partition", "channel", "rank", "bankgroup", "bank"))
                aggregates[key]["transactions"] += 1
                aggregates[key]["strict_wait_ticks"] += int(row["cross_request_bank_wait_ticks"])
                aggregates[key]["queue_ticks"] += int(row["controller_queue_ticks"])
        for key, values in sorted(aggregates.items()):
            partition, channel, rank, bankgroup, bank = key
            distribution.append({
                "case": label,
                "partition": partition,
                "channel": channel,
                "rank": rank,
                "bankgroup": bankgroup,
                "bank": bank,
                **values,
            })
        provenance["inputs"][label] = {
            str(path.relative_to(args.root)): sha256(path)
            for path in (normal_validation, oracle_validation, paired_audit, bank_requests)
        }
    with (args.out / "phenomenon_summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    with (args.out / "bank_distribution.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(distribution[0]))
        writer.writeheader()
        writer.writerows(distribution)
    provenance["outputs"] = {
        name: sha256(args.out / name)
        for name in ("phenomenon_summary.csv", "bank_distribution.csv")
    }
    (args.out / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "PASS", "cases": len(summary), "bank_rows": len(distribution), **provenance["outputs"]}, indent=2))


if __name__ == "__main__":
    main()
