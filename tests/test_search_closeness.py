"""How close the projects of a list are to each other (search/closeness.py, design 8.6): the
groups of Ward's method against the method done the slow way, the closest project of each, the
most central project of a group, and the similarities read from the database, on invented
vectors."""

from __future__ import annotations

import math
import random

import pytest

from hackathon_memory.db.embeddings import EmbeddingStore
from hackathon_memory.llm.embeddings import Embedding
from hackathon_memory.search import closeness
from searchfakes import ids_of, three_projects


def unit(values: list[float]) -> list[float]:
    length = math.sqrt(sum(value * value for value in values))
    return [value / length for value in values]


def pairs_of(vectors: dict[int, list[float]]) -> dict[tuple[int, int], float]:
    ids = sorted(vectors)
    return {(a, b): sum(x * y for x, y in zip(vectors[a], vectors[b], strict=True))
            for i, a in enumerate(ids) for b in ids[i + 1 :]}  # fmt: skip


def slow_ward(ids: list[int], vectors: dict[int, list[float]], count: int) -> list[list[int]]:
    """Ward's method as its definition says: join the two groups whose joining adds least to the
    sum of the squared distances of each vector to the centre of its group."""

    def spread(group: list[int]) -> float:
        size = len(vectors[group[0]])
        centre = [sum(vectors[pid][k] for pid in group) / len(group) for k in range(size)]
        return sum(sum((vectors[pid][k] - centre[k]) ** 2 for k in range(size)) for pid in group)

    groups = [[pid] for pid in ids]
    while len(groups) > count:
        best = min(((i, j) for i in range(len(groups)) for j in range(i + 1, len(groups))),
                   key=lambda pair: spread(groups[pair[0]] + groups[pair[1]])
                   - spread(groups[pair[0]]) - spread(groups[pair[1]]))  # fmt: skip
        i, j = best
        groups[i] = groups[i] + groups[j]
        del groups[j]
    place = {pid: n for n, pid in enumerate(ids)}
    return sorted((sorted(group, key=place.get) for group in groups), key=lambda g: place[g[0]])


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_the_groups_are_those_of_wards_method(seed: int) -> None:
    chance = random.Random(seed)  # noqa: S311 - invented vectors, not a secret
    centres = [unit([chance.gauss(0, 1) for _ in range(6)]) for _ in range(3)]
    vectors = {}
    for pid in range(100, 124):
        near = centres[pid % 3]
        vectors[pid] = unit([value + chance.gauss(0, 0.35) for value in near])
    ids = list(vectors)
    chance.shuffle(ids)
    pairs = pairs_of(vectors)
    for count in (1, 2, 3, 4, 6):
        assert closeness.groups(ids, pairs, count) == slow_ward(ids, vectors, count)


def test_groups_keep_the_order_of_the_list() -> None:
    vectors = {1: [1.0, 0.0], 2: [0.0, 1.0], 3: unit([1.0, 0.1]), 4: unit([0.1, 1.0])}
    pairs = pairs_of(vectors)
    assert closeness.groups([4, 1, 2, 3], pairs, 2) == [[4, 2], [1, 3]]
    assert closeness.groups([4, 1, 2, 3], pairs, 9) == [[4], [1], [2], [3]]  # never more groups
    assert closeness.groups([], pairs, 2) == []


def test_the_closest_and_the_most_central_projects() -> None:
    vectors = {1: [1.0, 0.0, 0.0], 2: unit([1.0, 0.2, 0.0]), 3: unit([1.0, 0.0, 0.4]),
               4: [0.0, 0.0, 1.0]}  # fmt: skip
    pairs = pairs_of(vectors)
    assert closeness.nearest([1, 2, 3, 4], pairs) == {1: 2, 2: 1, 3: 1, 4: 3}
    assert closeness.central([2, 3, 1], pairs) == 1  # the closest to both others
    assert closeness.central([4], pairs) == 4
    same = {(1, 2): 0.5, (1, 3): 0.5, (2, 3): 0.1}
    assert closeness.nearest([3, 2, 1], same)[1] == 3  # on a tie, the first of the list


@pytest.mark.integration
def test_the_similarities_come_from_the_embeddings_in_the_database(empty_database: str) -> None:
    database = three_projects(empty_database)
    ids = ids_of(database)
    store = EmbeddingStore(database)
    vectors = {"Pebble Pay": [1.0, 0.0], "Cedar Post": unit([1.0, 1.0])}
    for name, values in vectors.items():
        store.save(ids[name], "a-model", "f" * 64, Embedding(values + [0.0] * 3070, 4, False))
    wanted = list(ids.values())
    assert closeness.with_embedding(database, wanted, model="a-model") == {
        ids["Pebble Pay"], ids["Cedar Post"]}  # fmt: skip
    found = closeness.similarities(database, wanted, model="a-model")
    pair = tuple(sorted((ids["Pebble Pay"], ids["Cedar Post"])))
    assert list(found) == [pair] and found[pair] == pytest.approx(math.sqrt(0.5))
    assert closeness.similarities(database, wanted, model="another-model") == {}
