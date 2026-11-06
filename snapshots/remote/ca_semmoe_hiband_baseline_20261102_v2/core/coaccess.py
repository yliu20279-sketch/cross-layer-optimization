"""Historical accepted-request intervals, not command-level Bank residence."""
from collections import defaultdict
import math
import random
from .common import digest, nonnegative_time, require
from .memory import split_pages, validate_mapping


def build_profile(events, profile_ids, eval_ids):
    require(bool(profile_ids) and not set(profile_ids) & set(eval_ids), "invalid profile identity")
    pending, completed, closed = {}, set(), []
    owner_request, request_owner = {}, {}
    for row in events:
        require(row.get("request_id") in profile_ids, "non-profile event")
        require(row.get("request_id") not in eval_ids, "eval event in profile")
        require(row.get("owner") not in (None, -1, "-1"), "unknown logical request owner")
        owner, request = row["owner"], row["request_id"]
        require(owner not in owner_request or owner_request[owner] == request, "owner spans different requests")
        require(request not in request_owner or request_owner[request] == owner, "request changes owner")
        owner_request[owner], request_owner[request] = request, owner
        require(row.get("role") == "weight" and not row.get("router", False), "non-movable profile role")
        require(row.get("partition", -1) >= 0 and row.get("generation", -1) >= 0,
                "invalid partition/generation")
        require(isinstance(row.get("object_id"), str) and row["object_id"], "object identity required")
        key = tuple(row[k] for k in ("partition", "object_id", "generation", "op_id", "transaction_id"))
        time = nonnegative_time(row["time"])
        kind = row.get("event")
        if kind == "accept":
            require(key not in pending and key not in completed, "duplicate accepted transaction")
            require(isinstance(row.get("offset"), int) and row["offset"] >= 0 and
                    isinstance(row.get("bytes"), int) and row["bytes"] > 0 and
                    row["offset"] + row["bytes"] <= row.get("object_bytes", 0), "invalid object extent")
            pending[key] = row.copy()
        elif kind == "callback":
            require(key in pending and key not in completed, "unpaired/duplicate callback")
            begin = pending.pop(key)
            require(all(row.get(k) == begin.get(k) for k in
                        ("request_id", "owner", "offset", "bytes", "object_bytes", "role", "router")),
                    "callback identity changed")
            require(time >= begin["time"], "callback before accept")
            completed.add(key)
            for page, _, size in split_pages(begin["offset"], begin["bytes"]):
                page_id = f'{row["partition"]}/{row["object_id"]}/{row["generation"]}/{page}'
                closed.append({"page": page_id, "partition": row["partition"],
                               "request_id": row["request_id"], "owner": row["owner"],
                               "start": begin["time"], "done": time, "bytes": size})
        else:
            require(False, "only successful accept and callback events allowed")
    require(not pending and bool(closed), "incomplete/empty profile")
    heat, edges, grouped = defaultdict(int), defaultdict(float), defaultdict(list)
    for interval in closed:
        heat[interval["page"]] += interval["bytes"]
        grouped[interval["partition"]].append(interval)
    for intervals in grouped.values():
        active = []
        for right in sorted(intervals, key=lambda x: (x["start"], x["done"], x["page"])):
            active = [left for left in active if left["done"] > right["start"]]
            for left in active:
                if left["page"] == right["page"] or left["owner"] == right["owner"] or left["request_id"] == right["request_id"]:
                    continue
                overlap = min(left["done"], right["done"]) - right["start"]
                if overlap > 0:
                    pair = tuple(sorted((left["page"], right["page"])))
                    edges[pair] += overlap
            active.append(right)
    return {"method": "CA4-TIME-accepted-to-callback-proxy", "heat": dict(heat),
            "edges": [[a, b, w] for (a, b), w in sorted(edges.items())],
            "event_sha256": digest(events), "transactions": len(completed),
            "valid_bytes": sum(heat.values()), "not_bank_residence": True}


def optimize(base, pages, decoder, profile, seeds, evaluations=20000, move_fraction=.1, heat_only=False):
    require(bool(seeds) and len(set(seeds)) == len(seeds) and evaluations >= 0 and
            0 <= move_fraction <= 1, "invalid search budget")
    validate_mapping(base, base, pages, decoder)
    require(set(profile["heat"]) <= set(pages), "profile includes unknown pages")
    require(all(isinstance(value, int) and value >= 0 for value in profile["heat"].values()),
            "invalid profile byte heat")
    for a, b, weight in profile["edges"]:
        require(a in pages and b in pages and pages[a]["partition"] == pages[b]["partition"] and
                isinstance(weight, (int, float)) and math.isfinite(weight) and weight >= 0,
                "invalid coaccess edge")
    def bank(key, frame):
        return decoder["frame_banks"][str(pages[key]["partition"])][str(frame)]
    def score(mapping):
        loads = defaultdict(int)
        for key, frame in mapping.items():
            loads[pages[key]["partition"], bank(key, frame)] += profile["heat"].get(key, 0)
        conflict = sum(w for a, b, w in profile["edges"] if bank(a, mapping[a]) == bank(b, mapping[b]))
        heat = sum(value * value for value in loads.values())
        return (heat,) if heat_only else (conflict, heat)
    groups = defaultdict(list)
    for key in sorted(pages):
        if pages[key].get("movable", False):
            groups[pages[key]["partition"]].append(key)
    groups = [keys for _, keys in sorted(groups.items()) if len(keys) >= 2]
    budget = int(sum(p["bytes"] for p in pages.values() if p.get("movable", False)) * move_fraction)
    runs = []
    for seed in seeds:
        rng = random.Random(seed)
        mapping, current, accepted = dict(base), score(base), 0
        for _ in range(evaluations):
            if not groups:
                break
            a, b = rng.sample(rng.choice(groups), 2)
            candidate = dict(mapping)
            candidate[a], candidate[b] = candidate[b], candidate[a]
            moved = sum(pages[k]["bytes"] for k in pages if candidate[k] != base[k])
            if moved > budget:
                continue
            cost = score(candidate)
            if cost < current:
                mapping, current, accepted = candidate, cost, accepted + 1
        validate_mapping(base, mapping, pages, decoder)
        runs.append({"seed": seed, "mapping": mapping, "score": current,
                     "accepted": accepted, "evaluations": evaluations if groups else 0,
                     "changed_payload_bytes": sum(pages[k]["bytes"] for k in pages if mapping[k] != base[k])})
    best = min(runs, key=lambda x: (x["score"], x["seed"]))
    return {"selected": best, "runs": runs, "move_budget_bytes": budget,
            "method": "HEAT4" if heat_only else "CA4-TIME", "runtime_cost_certified": False}
