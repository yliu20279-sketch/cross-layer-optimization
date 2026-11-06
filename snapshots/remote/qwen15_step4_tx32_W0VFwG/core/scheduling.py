"""Profile-only expert placement and token-affinity-only TP scheduling.

This implements an explicitly limited ablation, not the paper's 2-gram method.
The decision API has no current-layer routing argument. Real router outputs
are consumed separately, after routing completes, for dispatch/combine.
"""
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from .common import digest, nonnegative_time, require


def validate_split(records):
    require(bool(records), "empty trace")
    ids = {"profile": set(), "eval": set()}
    source = {"profile": set(), "eval": set()}
    tokens = {"profile": set(), "eval": set()}
    request_identity, identity_owners = {}, {}
    for row in records:
        split = row.get("split")
        require(split in ids, "explicit profile/eval split required; no fallback")
        identity = (row.get("source_sha256"), row.get("input_tokens_sha256"))
        require(all(isinstance(x, str) and len(x) == 64 and
                    all(c in "0123456789abcdef" for c in x) for x in identity),
                "source and full-request token hashes required")
        req = row.get("request_id")
        require(isinstance(req, str) and bool(req), "request_id required")
        key = (split, req)
        require(key not in request_identity or request_identity[key] == identity,
                "inconsistent request identity")
        request_identity[key] = identity
        for field, value in zip(("source", "tokens"), identity):
            identity_key = (split, field, value)
            require(identity_key not in identity_owners or identity_owners[identity_key] == req,
                    "duplicate source/token sequence under different request IDs")
            identity_owners[identity_key] = req
        ids[split].add(req)
        source[split].add(identity[0])
        tokens[split].add(identity[1])
    require(all(ids.values()), "both profile and eval are required")
    for label, groups in (("ID", ids), ("source", source), ("tokens", tokens)):
        require(not groups["profile"] & groups["eval"], label + " overlap")
    return {key: sorted(value) for key, value in ids.items()}


def train_placement(profile, layers, experts, ep, iterations=12):
    """Deterministic balanced expert capacity, frequency-load token penalty.

    Token frequency is derived from activation rows; no eval rows are accepted.
    This is a named project heuristic, not official author-code equivalence.
    """
    require(experts > 0 and ep > 0 and experts % ep == 0, "unequal expert capacity")
    require(layers > 0 and iterations > 0 and profile, "invalid training input")
    counts = defaultdict(lambda: defaultdict(Counter))
    for row in profile:
        require(row.get("split") == "profile", "training accepts profile only")
        layer, expert, token = row["layer"], row["expert"], row["token_id"]
        count = row.get("count", 1)
        require(isinstance(layer, int) and 0 <= layer < layers, "invalid layer")
        require(isinstance(expert, int) and 0 <= expert < experts, "invalid expert")
        require(isinstance(token, int) and token >= 0, "invalid token")
        require(isinstance(count, int) and count > 0, "invalid count")
        counts[layer][token][expert] += count
    result = {}
    for layer in range(layers):
        require(bool(counts[layer]), "profile must cover every selected layer")
        affinity = counts[layer]
        frequency = {t: sum(c.values()) for t, c in affinity.items()}
        owner = {e: e // (experts // ep) for e in range(experts)}
        token_rank = {}
        for _ in range(iterations):
            loads = [0] * ep
            target = sum(frequency.values()) / ep
            for token in sorted(affinity, key=lambda t: (-frequency[t], t)):
                def score(rank):
                    local = sum(n for e, n in affinity[token].items() if owner[e] == rank)
                    penalty = .15 * max(0, loads[rank] + frequency[token] - target) / max(target, 1)
                    return local / frequency[token] - penalty, -loads[rank], -rank
                rank = max(range(ep), key=score)
                token_rank[token] = rank
                loads[rank] += frequency[token]
            scores = [[0] * ep for _ in range(experts)]
            for token, values in affinity.items():
                for expert, count in values.items():
                    scores[expert][token_rank[token]] += count
            capacity = [experts // ep] * ep
            owner = {}
            for _, expert, rank in sorted(
                    ((scores[e][rank], e, rank) for e in range(experts) for rank in range(ep)),
                    key=lambda item: (-item[0], item[1], item[2])):
                if expert not in owner and capacity[rank]:
                    owner[expert] = rank
                    capacity[rank] -= 1
        # Recompute predicted token destinations for final expert layout.
        for token in affinity:
            token_rank[token] = max(range(ep), key=lambda rank: (
                sum(n for e, n in affinity[token].items() if owner[e] == rank), -rank))
        require(Counter(owner.values()) == Counter({r: experts // ep for r in range(ep)}),
                "expert assignment not balanced")
        result[str(layer)] = {"expert_to_rank": {str(e): owner[e] for e in range(experts)},
                              "token_to_rank": {str(t): token_rank[t] for t in sorted(token_rank)}}
    return {"method": "token-affinity-only-project-ablation", "two_gram": False,
            "ep": ep, "experts": experts, "layers": result,
            "profile_sha256": digest(profile), "official_equivalence": False}


@dataclass(frozen=True)
class DecisionInput:
    request_id: str
    position: int
    token_id: int
    layer: int
    available_at: float
    decision_at: float


def decide(placement, data):
    require(isinstance(data, DecisionInput), "typed causal input required")
    nonnegative_time(data.available_at)
    nonnegative_time(data.decision_at)
    require(data.available_at <= data.decision_at, "input unavailable at decision")
    require(bool(data.request_id) and data.position >= 0 and data.token_id >= 0,
            "invalid token identity")
    table = placement["layers"].get(str(data.layer))
    require(table is not None, "unknown layer")
    unknown = str(data.token_id) not in table["token_to_rank"]
    rank = table["token_to_rank"].get(str(data.token_id), data.token_id % placement["ep"])
    return {"request_id": data.request_id, "position": data.position, "layer": data.layer,
            "rank": rank, "unknown_token": unknown, "available_at": data.available_at,
            "decision_at": data.decision_at, "input_sha256": digest(asdict(data)), "input": asdict(data),
            "placement_sha256": digest(placement), "method": placement["method"]}


def route_after_router(placement, decision, experts, weights, router_done):
    nonnegative_time(router_done)
    require(router_done >= decision["decision_at"], "router before decision")
    require(decision["placement_sha256"] == digest(placement), "placement changed")
    require(decide(placement, DecisionInput(**decision["input"])) == decision, "decision altered")
    require(len(experts) == len(weights) and len(experts) > 0 and len(set(experts)) == len(experts),
            "invalid TopK slots")
    require(all(isinstance(w, (int, float)) and 0 <= w <= 1 for w in weights), "invalid weight")
    table = placement["layers"][str(decision["layer"])]["expert_to_rank"]
    flows = []
    for slot, (expert, weight) in enumerate(zip(experts, weights)):
        require(str(expert) in table, "unknown expert")
        flows.append({"request_id": decision["request_id"], "position": decision["position"],
                      "layer": decision["layer"], "slot": slot, "expert": expert,
                      "weight": weight, "src_rank": decision["rank"],
                      "dst_rank": table[str(expert)], "available_at": router_done})
    return flows
