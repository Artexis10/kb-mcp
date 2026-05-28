"""Reciprocal Rank Fusion for merging heterogeneous ranker outputs.

RRF is the standard way to combine BM25 + vector rankings without having
to normalize the underlying scores: each ranker votes purely by rank.
Formula: score(d) = sum over rankers r of 1 / (k + rank_r(d)).

k=60 is the conventional default (Cormack, Clarke, Buettcher 2009).
"""

from __future__ import annotations


def reciprocal_rank_fusion(
    result_lists: list[list[str]], k: int = 60
) -> list[tuple[str, float]]:
    """Fuse multiple ranked lists of paths into one ranking.

    Each input list is best-first. Duplicates within one list are ignored
    after the first occurrence (only the best rank in that list counts).
    Returns deduplicated `(path, fused_score)` pairs sorted by score desc,
    with path as a deterministic tie-breaker.
    """
    fused: dict[str, float] = {}
    for ranking in result_lists:
        seen: set[str] = set()
        for rank, path in enumerate(ranking, start=1):
            if path in seen:
                continue
            seen.add(path)
            fused[path] = fused.get(path, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda t: (-t[1], t[0]))
