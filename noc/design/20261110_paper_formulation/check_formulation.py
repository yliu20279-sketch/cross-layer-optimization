"""Synthetic checks of the written constraints, not a runtime scheduler."""
from pathlib import Path
import json
import check_algorithm_paths as topo

ROOT = Path(__file__).resolve().parent
PATHS = {'a': topo.paths(5, 6)[0],
         'b': next(p for p in topo.paths(5, 6) if len(p) == 1 and p != topo.paths(5, 6)[0]),
         'rev': topo.paths(6, 5)[0]}
ENDPOINTS = {'a': (5, 6), 'b': (5, 6), 'rev': (6, 5)}


def evaluate(packets, z, x, costs, capacity):
    assert all(v in (0, 1) for v in z.values())
    assert all(v in (0, 1) for v in x.values())
    selected = [p for p, v in z.items() if v]
    switches = set()
    states = {}
    for p in selected:
        assert p in PATHS
        for c, i, o in PATHS[p]:
            assert c not in switches
            switches.add(c)
            states[c] = topo.encode(c, i, o)
            assert topo.decode(c, states[c]) == (i, o)
    load = {r: 0 for r in capacity}
    volume = 0
    for m, packet in packets.items():
        choices = [p for (mm, p), v in x.items() if mm == m and v]
        assert len(choices) <= 1
        if choices:
            p = choices[0]
            assert z.get(p, 0) == 1 and packet['eligible']
            assert ENDPOINTS[p] == packet['endpoints']
            volume += packet['bytes']
        else:
            p = 'mesh'
        for r in load:
            load[r] += costs.get((m, p, r), 0)
    assert all(m in packets and p in PATHS for m, p in x)
    assert all(load[r] <= capacity[r] for r in load)
    return volume, load, states


def main():
    checks = []
    packets = {m: {'bytes': 4, 'eligible': True, 'endpoints': (5, 6)} for m in (0, 1)}
    costs = {}
    for m in packets:
        for p in ('a', 'b', 'mesh'):
            costs[m, p, 'shared_NI'] = 1
            costs[m, p, 'SRAM'] = 1
            costs[m, p, 'mesh_link'] = int(p == 'mesh')
            costs[m, p, 'CS_a'] = int(p == 'a')
            costs[m, p, 'CS_b'] = int(p == 'b')
    cap = {'shared_NI': 2, 'SRAM': 2, 'mesh_link': 1, 'CS_a': 2, 'CS_b': 2}

    def reject(name, zz, xx, pp=packets, cc=cap):
        try:
            evaluate(pp, zz, xx, costs, cc)
        except AssertionError:
            checks.append(name)
        else:
            raise AssertionError('Expected rejection: '+name)

    v, load, states = evaluate(packets, {'a': 1}, {(0, 'a'): 1}, costs, cap)
    assert v == 4 and load['mesh_link'] == 1 and load['shared_NI'] == 2
    checks.append('Mesh fallback counted; same source service retained')
    v, _, states = evaluate(packets, {'a': 1, 'b': 1}, {(0, 'a'): 1, (1, 'b'): 1}, costs, cap)
    assert v == 8 and len(states) == 2
    checks.append('Two NI attachments use distinct CSs and count two distinct packets')
    reject('Same packet cannot be counted twice', {'a': 1, 'b': 1}, {(0, 'a'): 1, (0, 'b'): 1})
    reject('Unconfigured path rejected', {}, {(0, 'a'): 1})
    reject('Shared CS rejected even for opposite direction', {'a': 1, 'rev': 1}, {})
    reject('Binary assignment domain enforced', {'a': 1}, {(0, 'a'): 2})
    reject('Mesh-only work can exceed a planning budget', {}, {})
    not_ready = {m: dict(p) for m, p in packets.items()}
    not_ready[0]['eligible'] = False
    reject('Unready or bound transfer cannot be assigned', {'a': 1}, {(0, 'a'): 1}, pp=not_ready)
    constrained = dict(cap, shared_NI=1)
    reject('Additional CSs do not remove the shared NI limit', {'a': 1, 'b': 1},
           {(0, 'a'): 1, (1, 'b'): 1}, cc=constrained)
    constrained = dict(cap, SRAM=1)
    reject('Additional CSs do not remove the shared SRAM limit', {'a': 1, 'b': 1},
           {(0, 'a'): 1, (1, 'b'): 1}, cc=constrained)
    assert v == sum(p['bytes'] for p in packets.values())
    checks.append('Objective counts payload, not service work or header bytes')
    # Volume is primary; failed timing checks reject application, not redefine V.
    ranked = sorted([('old', 8, True, 0), ('high', 12, False, 2), ('next', 10, True, 1)],
                    key=lambda a: (-a[1], a[0] != 'old', a[3]))
    selected = next(a[0] for a in ranked if a[0] == 'old' or a[2])
    assert selected == 'next'
    checks.append('Volume ranking followed by timing acceptance')
    ranked = sorted([('old', 8, True, 0), ('tie', 8, True, 1), ('low', 6, True, 1)],
                    key=lambda a: (-a[1], a[0] != 'old', a[3]))
    assert ranked[0][0] == 'old'
    checks.append('Keep active on a volume tie or lower-volume candidate')
    report = {'status': 'PASS', 'checks': checks, 'count': len(checks),
              'scope': 'Synthetic algebra, physical state mapping and ranking examples',
              'not_claimed': ['online heuristic implementation', 'global optimality',
                              'real resource calibration', 'queue/credit/RTL correctness',
                              'runtime speedup']}
    (ROOT/'formulation_unit_checks.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
