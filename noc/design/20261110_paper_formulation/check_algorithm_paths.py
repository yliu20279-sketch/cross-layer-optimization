"""Static topology/state checks only; no runtime controller or RTL simulation."""
from itertools import combinations
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
LD = ('NW', 'NE', 'SW', 'SE', 'U')
ATTACH = {0: 9, 2: 10, 6: 11, 8: 12}
POS = {9: (0, 0), 10: (0, 1), 11: (1, 0), 12: (1, 1)}
RING = (9, 10, 12, 11)


def corners(c):
    r, k = divmod(c, 3)
    return dict(zip(LD[:4], (4*r+k, 4*r+k+1, 4*(r+1)+k, 4*(r+1)+k+1)))


def nd(c, n):
    return next(d for d, node in corners(c).items() if node == n)


def facing(a, b):
    ar, ac = POS[a]
    br, bc = POS[b]
    return {(0, 1): 'E', (0, -1): 'W', (1, 0): 'S', (-1, 0): 'N'}[br-ar, bc-ac]


def dirs(c):
    if c < 9:
        return LD
    r, k = POS[c]
    return ('E' if k == 0 else 'W', 'S' if r == 0 else 'N', 'D')


def peer(c, d):
    if c < 9:
        if d == 'U':
            return ('C', ATTACH[c], 'D') if c in ATTACH else None
        return ('N', corners(c)[d])
    if d == 'D':
        return ('C', next(k for k, v in ATTACH.items() if v == c), 'U')
    for other, b in POS.items():
        a = POS[c]
        if abs(a[0]-b[0])+abs(a[1]-b[1]) == 1 and facing(c, other) == d:
            return ('C', other, facing(other, c))
    return None


def encode(c, i, o):
    assert i != o and peer(c, i) is not None and peer(c, o) is not None
    ds = dirs(c)
    return (ds.index(o) << (3 if c < 9 else 2)) | (tuple(d for d in ds if d != o).index(i) << 1) | 1


def decode(c, v):
    assert 0 <= v < (64 if c < 9 else 16)
    if not v & 1:
        return None
    oc = v >> (3 if c < 9 else 2)
    assert oc < len(dirs(c))
    o = dirs(c)[oc]
    i = tuple(d for d in dirs(c) if d != o)[(v >> 1) & (3 if c < 9 else 1)]
    assert peer(c, i) is not None and peer(c, o) is not None
    return i, o


def check(s, d, steps):
    assert len({c for c, _, _ in steps}) == len(steps)
    assert peer(steps[0][0], steps[0][1]) == ('N', s)
    assert peer(steps[-1][0], steps[-1][2]) == ('N', d)
    for c, i, o in steps:
        assert decode(c, encode(c, i, o)) == (i, o)
    for (c, _, o), (nc, ni, _) in zip(steps, steps[1:]):
        assert peer(c, o) == ('C', nc, ni)
        assert peer(nc, ni) == ('C', c, o)


def paths(s, d):
    if s == d:
        return []
    result = [((c, nd(c, s), nd(c, d)),) for c in range(9)
              if s in corners(c).values() and d in corners(c).values()]
    sc = next(c for c in ATTACH if s in corners(c).values())
    dc = next(c for c in ATTACH if d in corners(c).values())
    if sc != dc:
        for sign in (1, -1):
            ups = [ATTACH[sc]]
            while ups[-1] != ATTACH[dc]:
                ups.append(RING[(RING.index(ups[-1])+sign) % 4])
            steps = [(sc, nd(sc, s), 'U')]
            for j, c in enumerate(ups):
                steps.append((c, 'D' if j == 0 else facing(c, ups[j-1]),
                              'D' if j == len(ups)-1 else facing(c, ups[j+1])))
            result.append(tuple(steps+[(dc, 'U', nd(dc, d))]))
    for p in result:
        check(s, d, p)
    return result


def used(p):
    return {c for c, _, _ in p}


def rejects(c, i, o):
    try:
        encode(c, i, o)
    except AssertionError:
        return True
    return False


def main():
    table = {(s, d): paths(s, d) for s in range(16) for d in range(16) if s != d}
    flat = [p for pp in table.values() for p in pp]
    assert len(table) == 240 and all(table.values())
    assert all(len(pp) == len(set(pp)) for pp in table.values())
    assert all(paths(s, s) == [] for s in range(16))
    assert all(rejects(c, d, d) for c in range(13) for d in dirs(c))
    assert all(rejects(c, i, o) for c in set(range(9))-ATTACH.keys()
               for i, o in [('NW', 'U'), ('U', 'NE')])
    pair = [p for p in table[5, 6] if len(p) == 1]
    assert len(pair) == 2 and used(pair[0]).isdisjoint(used(pair[1]))
    rev = next(p for p in table[6, 5] if used(p) == used(pair[0]))
    assert not used(pair[0]).isdisjoint(used(rev))
    independent = [paths(0, 1)[0], paths(2, 3)[0], paths(8, 9)[0]]
    assert all(used(a).isdisjoint(used(b)) for a, b in combinations(independent, 2))
    assert len(table[0, 15]) == 2 and all(len(p) == 5 for p in table[0, 15])
    report = {
        'status': 'PASS', 'scope': 'Static topology, state encoding/decoding and CS exclusion',
        'directed_node_pairs': len(table), 'unreachable_pairs': 0, 'paths': len(flat),
        'local_paths': sum(len(p) == 1 for p in flat),
        'upper_paths': sum(len(p) > 1 for p in flat),
        'max_paths_per_pair': max(map(len, table.values())),
        'max_CSs_per_simple_path': max(map(len, flat)),
        'same_NI_pair_two_local_paths_CSs': [sorted(used(p)) for p in pair],
        'three_CS_disjoint_example': [sorted(used(p)) for p in independent],
        'self_connections_rejected': True, 'absent_U_rejected': True,
        'no_claim': ['ready/credit RTL correctness', 'finite-buffer deadlock freedom',
                     'physical timing', 'window estimator or online controller implementation',
                     'prediction accuracy or performance benefit']}
    (ROOT/'algorithm_path_checks.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
