"""Bounded one-decision implementation of the four configuration policies."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
import re


FLOW_LIMIT = 4
PATH_LIMIT = 2
EVAL_LIMIT = 8
HOT_RESERVE = 3
WINDOW = 8192
PREDICT_ERROR = 1
SLOWDOWN_BUDGET = 0


@dataclass(frozen=True)
class Circuit:
    src: int
    dst: int
    switches: tuple

    @property
    def image(self):
        return sum((32 + 4 * op + (ip - (ip > op))) << (6 * sw)
                   for sw, ip, op in self.switches)


@dataclass(frozen=True)
class Candidate:
    paths: tuple
    assignments: tuple

    @property
    def image(self):
        return sum(path.image for path in self.paths)

    @property
    def volume(self):
        return len(self.assignments) * 132


KEEP = Candidate((), ())


def wired_paths():
    source = Path("aux_packed.sv").read_text()
    peer = {int(p): int(q) for p, q in re.findall(r"(\d+): peer=(\d+);", source)}
    for p, q in peer.items():
        if q >= 16:
            assert peer[q - 16] == p + 16

    def visit(src, switch, incoming, trail):
        visited = {sw for sw, _, _ in trail}
        if switch in visited:
            return
        for outgoing in range(5):
            target = peer.get(switch * 5 + outgoing)
            if incoming == outgoing or target is None:
                continue
            hops = trail + ((switch, incoming, outgoing),)
            if target < 16:
                if target != src:
                    yield Circuit(src, target, hops)
                continue
            sw, port = divmod(target - 16, 5)
            yield from visit(src, sw, port, hops)

    result = defaultdict(set)
    for p, node in peer.items():
        if node < 16:
            sw, port = divmod(p, 5)
            for path in visit(node, sw, port, ()):
                result[path.src, path.dst].add(path)
    return {od: sorted(paths, key=lambda p: (len(p.switches), p.image))
            for od, paths in result.items()}


def xy(src, dst):
    nodes = [src]
    while nodes[-1] != dst:
        node = nodes[-1]
        if node % 4 != dst % 4:
            nodes.append(node + (1 if dst % 4 > node % 4 else -1))
        else:
            nodes.append(node + (4 if dst > node else -4))
    return tuple(zip(nodes, nodes[1:]))


def compatible(paths):
    switches = [sw for path in paths for sw, _, _ in path.switches]
    return (len(set(switches)) == len(switches)
            and len({path.src for path in paths}) == len(paths)
            and len({path.dst for path in paths}) == len(paths))


def service_feasible(packets, assignments, cc_src, cc_dst, cc_count):
    work = Counter()
    for index, a, mid, phase, src, dst, release in packets:
        work["ni_read", src] += 132
        work["ni_write", dst] += 132
        for seq in range(132):
            b = (mid + seq) % 8
            work["bank", src, b] += 1
            work["bank", dst, b] += 1
        if index not in assignments:
            for edge in xy(src, dst):
                work["mesh", edge] += 132
    for endpoint in (cc_src, cc_dst):
        work["ni_read", endpoint] += 4 * cc_count
        work["ni_write", endpoint] += 4 * cc_count
        for bank in range(8):
            work["bank", endpoint, bank] += cc_count
    for start, stop, size in ((cc_src, cc_dst, cc_count),
                              (cc_dst, cc_src, 3 * cc_count)):
        for edge in xy(start, stop):
            work["mesh", edge] += size
    return all(count <= WINDOW // {"bank": 4, "mesh": 2}.get(key[0], 1)
               for key, count in work.items())


def build_pool(flows, packets, paths, start, stop, cc_count, scores=None):
    path_options = []
    order = sorted(flows, key=lambda f: (-len(flows[f]), f))
    if scores:
        order = sorted((f for f in flows if scores[f]),
                       key=lambda f: (-scores[f], -len(flows[f]), f))
    for _, src, dst in order[:FLOW_LIMIT]:
        path_options.extend(paths.get((src, dst), ())[:PATH_LIMIT])
    options = list(dict.fromkeys(path_options))
    packet_index = defaultdict(list)
    for i, _, _, _, src, dst, _ in packets:
        packet_index[src, dst].append(i)
    pool = []

    def extend(parent, addition_size):
        for extension in combinations(options, addition_size):
            group = parent + extension
            if not compatible(group):
                continue
            assignments = tuple(sorted(i for path in group
                                       for i in packet_index[path.src, path.dst]))
            if service_feasible(packets, assignments, start, stop, cc_count):
                yield Candidate(tuple(sorted(group, key=lambda p: p.image)), assignments)

    parent = ()
    while len(parent) < 13:
        extensions = set(extend(parent, 1)) | set(extend(parent, 2))
        if not extensions:
            break
        ranked = sorted(extensions, key=lambda c: rank(c, packets, scores))
        pool.extend(ranked)
        parent = ranked[0].paths
    return sorted(set(pool), key=lambda c: rank(c, packets, scores))


def rank(candidate, packets, scores=None):
    changes = sum(len(path.switches) for path in candidate.paths)
    common = (-candidate.volume, changes, candidate.image)
    if scores:
        selected_pairs = {(path.src, path.dst) for path in candidate.paths}
        affected = {(app, src, dst) for _, app, _, _, src, dst, _ in packets
                    if (src, dst) in selected_pairs}
        return (-sum(scores[key] for key in sorted(affected)),) + common
    return common


def overlap_scores(result, packets, decision):
    scores = defaultdict(int)
    cc_by_edge = defaultdict(list)
    for u, v, app, msg, seq, cycle in result.edges:
        if app == 2:
            cc_by_edge[u, v].append(cycle)
    keys = {(app, msg): (app, src, dst) for _, app, msg, _, src, dst, _ in packets}
    # Include a short look-ahead on both sides of predicted CC passage.
    for u, v, app, msg, seq, cycle in result.edges:
        key = keys.get((app, msg))
        cc = cc_by_edge.get((u, v))
        if key and cc and cycle >= decision and cc[0] - 96 <= cycle <= cc[-1] + 32:
            scores[key] += 1
    return scores


def cap_pools(volume, hot):
    reserved = hot[:HOT_RESERVE]
    earlier = [item for item in volume if item not in reserved]
    return list(dict.fromkeys(earlier[:EVAL_LIMIT - len(reserved)] + reserved
                              + earlier[EVAL_LIMIT - len(reserved):]))[:EVAL_LIMIT]


def new_choice(baseline, candidates, predictions):
    passed = []
    checks = {}
    for candidate in candidates:
        trial = predictions[candidate]
        gain = baseline.cc_step - trial.cc_step - PREDICT_ERROR
        deltas = {k: trial.metrics[k] - baseline.metrics[k] for k in baseline.metrics}
        guard = max(deltas.values())
        # Equal deterministic resource schedules need no error margin. For unequal
        # results charge the fixed paired-error sensitivity floor.
        guarded = max(value + (PREDICT_ERROR if value else 0) for value in deltas.values())
        if gain <= 0:
            reason = "cc_gain"
        elif guarded > SLOWDOWN_BUDGET:
            reason = "moe_guard"
        else:
            passed.append((-gain, sum(len(p.switches) for p in candidate.paths),
                           candidate.image, candidate))
            reason = "pass"
        checks[candidate] = (reason, gain, guard)
    return (min(passed)[-1] if passed else KEEP), checks


def old_choice(baseline, candidates, predictions):
    checks = {}
    best = KEEP
    for candidate in sorted(candidates, key=lambda c: (-c.volume, len(c.paths), c.image)):
        trial = predictions[candidate]
        delta = baseline.wave_done - trial.wave_done
        background = max(trial.metrics[k] - baseline.metrics[k] for k in ("A_all", "B_all", "A_pref", "B_pref"))
        if delta <= PREDICT_ERROR:
            reason = "wave_gain"
        elif background + (PREDICT_ERROR if background else 0) > SLOWDOWN_BUDGET:
            reason = "background_guard"
        else:
            best, reason = candidate, "pass"
        checks[candidate] = (reason, delta - PREDICT_ERROR, background)
        if best != KEEP:
            break
    return best, checks

