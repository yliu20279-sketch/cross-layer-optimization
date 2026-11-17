"""Bounded circuit selection for the ready set of a single pure-MoE wave."""

from collections import Counter, defaultdict
from itertools import combinations

from planner import EVAL_LIMIT, PREDICT_ERROR, compatible, wired_paths, xy


def select(traffic, routes):
    """Choose using the most heavily loaded directed Mesh links in this wave."""
    volume = Counter()
    for src,dst,size in traffic:
        volume[src,dst] += (size+31)//32
    mesh_edges = {pair:xy(*pair) for pair in volume}
    edge_work = Counter()
    send = Counter()
    receive = Counter()
    for (src,dst),flits in volume.items():
        send[src] += flits
        receive[dst] += flits
        for edge in mesh_edges[src,dst]:
            edge_work[edge] += flits
    if not edge_work:
        return (),dict(mesh_bound=0,project_bound=0,evaluated=0)
    order = sorted(volume,key=lambda pair:(-max(edge_work[e] for e in mesh_edges[pair]),-volume[pair],pair))
    single = [path for pair in order[:4] for path in routes.get(pair,())[:2]]
    candidates = [(p,) for p in single]
    candidates.extend(c for c in combinations(single,2) if compatible(c))

    def bound(paths):
        work = edge_work.copy()
        circuit_complete = 0
        for path in paths:
            pair = path.src,path.dst
            for edge in mesh_edges[pair]:
                work[edge] -= volume[pair]
            circuit_complete = max(circuit_complete,40+len(path.switches)+volume[pair])
        # All candidates share the same source and destination service capacity.
        remaining = max((w for w in work.values()),default=0)
        return max(remaining,max(send.values()),max(receive.values()),circuit_complete)

    base = bound(())
    scored = [(bound(paths),sum(len(p.switches) for p in paths),tuple(p.image for p in paths),paths)
              for paths in candidates[:EVAL_LIMIT]]
    best = min(scored,key=lambda item:item[:3],default=(base,0,(),()))
    selected = best[3] if base-best[0]>PREDICT_ERROR else ()
    return selected,dict(mesh_bound=base,project_bound=bound(selected),evaluated=len(scored),
                         busiest_mesh_edges=edge_work.most_common(4),
                         circuits=[dict(src=p.src,dst=p.dst,image=f'{p.image:x}',switches=p.switches) for p in selected])
