from collections import Counter
from .common import require


def communication_scope(scheme, src, dst, width=4, partitions=16):
    require(scheme in ("baseline_ep", "sem_moe", "hiband", "hiband_sem_moe"), "unknown scheme")
    require(width > 0 and partitions > 0 and partitions % width == 0, "invalid topology")
    require(0 <= src < partitions and 0 <= dst < partitions and src != dst, "invalid peer")
    if scheme not in ("hiband", "hiband_sem_moe"):
        return "global"
    hops = abs(src % width - dst % width) + abs(src // width - dst // width)
    return "local" if hops == 1 else "global"


def dispatch_combine(flows, rank_to_pe, scheme, vector_bytes):
    """All actual destination peers, no aggregate single-peer substitution."""
    require(vector_bytes > 0, "invalid activation bytes")
    identities = set()
    packets = []
    for flow in flows:
        key = tuple(flow[k] for k in ("request_id", "position", "layer", "slot"))
        require(key not in identities, "duplicate routing slot")
        identities.add(key)
        src, dst = rank_to_pe[flow["src_rank"]], rank_to_pe[flow["dst_rank"]]
        if src == dst:
            continue
        for kind, a, b in (("dispatch", src, dst), ("combine", dst, src)):
            packets.append({"kind": kind, "src": a, "dst": b,
                            "bytes": vector_bytes, "slot_identity": key,
                            "scope": communication_scope(scheme, a, b)})
    require(Counter((p["src"], p["dst"], p["bytes"]) for p in packets if p["kind"] == "dispatch") ==
            Counter((p["dst"], p["src"], p["bytes"]) for p in packets if p["kind"] == "combine"),
            "dispatch/combine payload mismatch")
    return packets


def layer_dag(flows, decision, rank_to_pe, scheme, vector_bytes, shared_expert=False):
    """Semantic TP/MoE DAG, explicitly not target opcode/cycle lowering.

    Every consumer waits for its true producer. Route records are available
    only after router completion; scheduling is provided separately.
    """
    require(bool(flows), "empty layer")
    identity = (decision["request_id"], decision["position"], decision["layer"])
    require(all(tuple(f[k] for k in ("request_id", "position", "layer")) == identity for f in flows),
            "mixed token identities")
    require(all(f["src_rank"] == decision["rank"] and f["available_at"] >= decision["decision_at"]
                for f in flows), "causal route mismatch")
    packets = dispatch_combine(flows, rank_to_pe, scheme, vector_bytes)
    nodes = [{"id": "tp_partial", "kind": "attention_tp_partial"},
             {"id": "srs", "kind": "shuffled_reduce_scatter", "destination": decision["rank"]},
             {"id": "router", "kind": "actual_router_topk"}]
    edges = [("tp_partial", "srs"), ("srs", "router")]
    tails = []
    for flow in flows:
        slot = flow["slot"]
        dispatch, expert, combine = (f"{kind}_{slot}" for kind in ("dispatch", "expert", "combine"))
        remote = flow["src_rank"] != flow["dst_rank"]
        nodes.extend([{"id": dispatch, "kind": "dispatch" if remote else "local_operand", "slot": slot},
                      {"id": expert, "kind": "expert_gate_up_silu_down", "expert": flow["expert"]},
                      {"id": combine, "kind": "combine" if remote else "local_result", "slot": slot,
                       "weight": flow["weight"]}])
        edges.extend([("router", dispatch), (dispatch, expert), (expert, combine)])
        tails.append(combine)
    if shared_expert:
        nodes.extend([{"id": "shared_tp", "kind": "shared_expert_tp"},
                      {"id": "shared_reduce", "kind": "shared_tp_reduce"},
                      {"id": "shared_gate", "kind": "shared_gate_sigmoid"},
                      {"id": "shared_mul", "kind": "shared_gate_multiply"}])
        edges.extend([("srs", "shared_tp"), ("shared_tp", "shared_reduce"),
                      ("srs", "shared_gate"), ("shared_reduce", "shared_mul"),
                      ("shared_gate", "shared_mul")])
        tails.append("shared_mul")
    nodes.extend([{"id": "slot_sum", "kind": "ordered_weighted_slot_sum"},
                  {"id": "sag", "kind": "deferred_shuffled_allgather"}])
    edges.extend((tail, "slot_sum") for tail in tails)
    edges.append(("slot_sum", "sag"))
    ids = [node["id"] for node in nodes]
    require(len(set(ids)) == len(ids), "duplicate node")
    index = {name: i for i, name in enumerate(ids)}
    require(all(index[a] < index[b] for a, b in edges), "DAG producer order invalid")
    return {"nodes": nodes, "edges": edges, "packets": packets,
            "decision": decision, "target_opcode_lowering": False,
            "precision_and_cost_validated": False}
