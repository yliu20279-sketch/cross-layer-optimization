"""TP permutation semantics only: no numerical-kernel or cycle claim."""
from .common import require


def shuffled_reduce_scatter(partials, destinations, add):
    """Each rank contributes a vector for every token; add defines arithmetic."""
    ranks = len(partials)
    require(ranks > 0 and len(destinations) > 0, "empty collective")
    require(all(len(p) == len(destinations) for p in partials), "token count mismatch")
    width = len(partials[0][0])
    require(width > 0 and all(len(v) == width for rank in partials for v in rank),
            "vector shape mismatch")
    require(all(isinstance(d, int) and 0 <= d < ranks for d in destinations), "bad destination")
    shards = [[] for _ in range(ranks)]
    for token, dst in enumerate(destinations):
        reduced = list(partials[0][token])
        for rank in partials[1:]:
            reduced = [add(a, b) for a, b in zip(reduced, rank[token])]
        shards[dst].append((token, reduced))
    return shards


def shuffled_allgather(shards, token_count):
    gathered = {}
    for shard in shards:
        for token, value in shard:
            require(isinstance(token, int) and 0 <= token < token_count and token not in gathered,
                    "duplicate/invalid token")
            gathered[token] = list(value)
    require(set(gathered) == set(range(token_count)), "missing tokens")
    return [gathered[token] for token in range(token_count)]
