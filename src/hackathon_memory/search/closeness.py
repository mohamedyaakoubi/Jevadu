"""How close the projects of one list are to each other in meaning (design 8.6): the similarity of
each pair, the closest project of each, their groups, and the most central project of a group.

Everything comes from the embeddings of the pages (design 8.1), compared exactly by the database,
with no model call. Closeness is similarity of meaning, never a judgement of quality.

The groups come from Ward's method: it starts with each project alone and, step by step, joins the
two groups whose joining spreads their projects least, until the number of groups that was asked
is left. It needs no threshold of similarity. In one list the similarities lie close together
(120 projects of ETHOnline 2026: 8 pairs in 10 between 0.72 and 0.82, measured on 23 October
2026), so a threshold joins nearly every project into one group, or leaves nearly every
project alone.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import psycopg

from hackathon_memory.db.embeddings import PAGE

# The similarity of each pair of projects, under (the smaller id, the larger id).
Pairs = Mapping[tuple[int, int], float]


def similarities(
    conninfo: str, ids: Sequence[int], *, model: str, kind: str = PAGE
) -> dict[tuple[int, int], float]:
    """The cosine similarity of each pair of the projects of `ids` that have an embedding."""
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            "SELECT a.project_id, b.project_id, 1 - (a.embedding <=> b.embedding) "
            "FROM project_embeddings a JOIN project_embeddings b "
            "ON b.project_id > a.project_id AND b.model = a.model AND b.text_kind = a.text_kind "
            "WHERE a.model = %s AND a.text_kind = %s "
            "AND a.project_id = ANY(%s) AND b.project_id = ANY(%s)",
            (model, kind, list(ids), list(ids)),
        ).fetchall()
    return {(a, b): float(similarity) for a, b, similarity in rows}


def with_embedding(conninfo: str, ids: Sequence[int], *, model: str, kind: str = PAGE) -> set[int]:
    """The projects of `ids` that have an embedding of this model."""
    with psycopg.connect(conninfo) as conn:
        return {pid for (pid,) in conn.execute(
            "SELECT project_id FROM project_embeddings WHERE model = %s AND text_kind = %s "
            "AND project_id = ANY(%s)", (model, kind, list(ids))).fetchall()}  # fmt: skip


def similarity(pairs: Pairs, a: int, b: int) -> float:
    return pairs[(a, b) if a < b else (b, a)]


def nearest(ids: Sequence[int], pairs: Pairs) -> dict[int, int]:
    """The closest project of the list to each project; for a tie, the first in `ids`."""
    return {
        pid: max(
            (other for other in ids if other != pid),
            key=lambda other: similarity(pairs, pid, other),
        )  # fmt: skip
        for pid in ids
        if len(ids) > 1
    }


def central(group: Sequence[int], pairs: Pairs) -> int:
    """The project of the group closest in meaning to all the others: the highest mean
    similarity to them; for a tie, the first in `group`."""
    if len(group) == 1:
        return group[0]
    return max(group, key=lambda pid: sum(similarity(pairs, pid, other)
                                          for other in group if other != pid))  # fmt: skip


def groups(ids: Sequence[int], pairs: Pairs, count: int) -> list[list[int]]:
    """The projects of `ids` in `count` groups by Ward's method. Each group keeps the order of
    `ids`, and the groups come in the order of their first project.

    The distance of two embeddings is the square of the straight line between them, 2 (1 - their
    cosine similarity) for vectors of length one, and Lance and Williams' formula gives the
    distance of a joined group to the others. The steps are found with the nearest-neighbour chain,
    which needs about n * n comparisons in place of n * n * n, and then taken in the order of their
    distance, as the method takes them."""
    size = len(ids)
    if size == 0:
        return []
    count = max(1, min(count, size))
    distance: dict[int, dict[int, float]] = {i: {} for i in range(size)}
    for i in range(size):
        for j in range(i + 1, size):
            far = 2.0 * (1.0 - similarity(pairs, ids[i], ids[j]))
            distance[i][j] = distance[j][i] = far
    members = {i: [i] for i in range(size)}
    height = dict.fromkeys(range(size), 0.0)  # the distance at which a group was made
    steps: list[tuple[float, int, int, int]] = []  # the height, the two groups, the new group
    chain: list[int] = []
    alive = set(range(size))
    new = size
    while len(alive) > 1:
        if not chain:
            chain.append(min(alive))
        last = chain[-1]
        before = chain[-2] if len(chain) > 1 else None
        # the closest group; on a tie the one before in the chain, so that the chain ends
        close = min((other for other in alive if other != last),
                    key=lambda other: (distance[last][other], other != before, other))  # fmt: skip
        if close != before:
            chain.append(close)
            continue
        chain.pop()
        chain.pop()
        one, two = len(members[last]), len(members[close])
        joined = distance[last][close]
        distance[new] = {}
        for other in alive - {last, close}:
            three = len(members[other])
            far = ((one + three) * distance[last][other] + (two + three) * distance[close][other]
                   - three * joined) / (one + two + three)  # fmt: skip
            distance[new][other] = distance[other][new] = far
            del distance[other][last], distance[other][close]
        del distance[last], distance[close]
        alive -= {last, close}
        alive.add(new)
        members[new] = members[last] + members[close]
        # Ward's distances never fall as groups grow; the maximum keeps that true when the
        # rounding of a computer would not, so a group is always made before it is joined again.
        height[new] = max(joined, height[last], height[close])
        steps.append((height[new], last, close, new))
        new += 1
    # The method takes the steps by their distance, and on a tie in the order they were found.
    found = {i: [i] for i in range(size)}
    for _, last, close, made in sorted(steps, key=lambda step: (step[0], step[3]))[: size - count]:
        found[made] = found.pop(last) + found.pop(close)
    ordered = sorted(sorted(group) for group in found.values())
    return [[ids[i] for i in group] for group in ordered]
