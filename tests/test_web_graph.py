"""The places of the graph of a list (web/graph.py, design 8.6, S7), on invented projects: the
names of the groups, the distances to an idea, and dots that never overlap."""

from __future__ import annotations

import math

import pytest

from hackathon_memory.web import graph
from hackathon_memory.web.graph import Group


def apart(dots: tuple[graph.Dot, ...]) -> bool:
    """True when no two dots overlap."""
    return all(math.hypot(a.x - b.x, a.y - b.y) >= a.r + b.r
               for i, a in enumerate(dots) for b in dots[i + 1 :])  # fmt: skip


def inside(box: tuple[float, float, float, float], dot: graph.Dot) -> bool:
    left, top, width, height = box
    return left <= dot.x - dot.r and dot.x + dot.r <= left + width and (
        top <= dot.y - dot.r and dot.y + dot.r <= top + height)  # fmt: skip


def made(groups: list[list[int]], *, ranked: bool, distance: dict | None = None, linked=()):  # noqa: ANN001, ANN201
    """A graph of the invented projects of `groups`, the first of each its most central, the
    projects of one group close to each other."""
    order = sorted(pid for group in groups for pid in group)
    group_of = {pid: n for n, group in enumerate(groups) for pid in group}

    def closeness(one: int, two: int) -> float:
        return (0.9 if group_of[one] == group_of[two] else 0.5) - abs(one - two) / 10_000

    typical = {pid: closeness(pid, group[0]) for group in groups for pid in group[1:]}
    return graph.build(
        order, groups, ranked=ranked, distance=distance, typical=typical,
        nearest={pid: next(other for other in order if other != pid) for pid in order},
        centres=[group[0] for group in groups],
        categories={pid: "Payments" if pid % 2 else "Developer tools" for pid in order},
        names={pid: f"Project {pid}" for pid in order}, linked=linked,
    )  # fmt: skip


def test_the_number_of_groups_follows_the_size_of_the_list() -> None:
    assert [graph.group_count(size) for size in (2, 5, 6, 15, 16, 29, 30, 300)] == [
        1, 1, 2, 2, 3, 3, 4, 4]  # fmt: skip


def test_a_group_is_named_after_its_most_central_project() -> None:
    assert graph.named([1, 2, 3], {1: "Health", 2: "Payments", 3: "Payments"}) == ("Payments", 2)
    assert graph.named([1, 2], {1: "Health", 2: "Payments"}) == ("Health", 1)  # the first, on a tie
    assert graph.named([1, 2], {1: "", 2: ""}) == ("", 0)
    some = Group(1, 25, "Tools for AI agents", 23, 7, "Allowance")
    assert some.title == "Like Allowance"
    assert some.subtitle == "25 projects · 23 in Tools for AI agents"
    assert some.said == "25 projects, 23 in Tools for AI agents"
    assert Group(1, 4, "Health", 4, 7, "Leash").subtitle == "4 projects · all in Health"
    assert Group(1, 1, "Health", 1, 7, "Leash").subtitle == "1 project · Health"
    assert Group(1, 3, "", 0, 7, "Leash").said == "3 projects"
    assert Group(1, 3, "", 0, 7, "A name much longer than the label").title == (
        "Like A name much longer than…")  # fmt: skip


def test_the_distance_to_the_idea_follows_the_closeness_in_meaning() -> None:
    order = [1, 2, 3]
    assert graph._distances(order, {1: 0.2, 2: 0.25, 3: 0.4}) == pytest.approx(
        {1: graph.NEAR, 2: graph.NEAR + (graph.FAR - graph.NEAR) / 4, 3: graph.FAR})  # fmt: skip
    assert graph._distances(order, {1: 0.3, 2: 0.3, 3: 0.3})[2] == (graph.NEAR + graph.FAR) / 2
    by_place = graph._distances(order, None)  # without Google: the places in the list
    assert by_place[1] == graph.NEAR and by_place[3] == graph.FAR


def test_every_group_gets_a_fair_part_of_the_circle() -> None:
    spans = graph._spans([40, 9, 1])
    assert sum(spans) == pytest.approx(2 * math.pi - 3 * graph.SECTOR_GAP)
    assert spans[2] == pytest.approx(graph.SECTOR_MIN) and spans[0] > spans[1] > spans[2]


def test_around_an_idea_the_closest_project_stands_nearest() -> None:
    groups = [[1, 4, 6, 8, 10, 12, 14], [2, 3, 5, 7, 9, 11, 13]]
    distance = {pid: 0.2 + pid / 100 for pid in range(1, 15)}
    drawn = made(groups, ranked=True, distance=distance)
    middle = {dot.project_id: math.hypot(dot.x, dot.y) for dot in drawn.dots}
    assert sorted(middle, key=middle.get) == list(range(1, 15))
    assert [dot.rank for dot in drawn.dots] == list(range(1, 15)) and drawn.by_meaning
    assert {dot.r for dot in drawn.dots if dot.rank <= 10} == {graph.NUMBERED}
    assert apart(drawn.dots) and all(inside(drawn.box, dot) for dot in drawn.dots)
    assert [group.title for group in drawn.groups] == ["Like Project 1", "Like Project 2"]
    without = made(groups, ranked=True)  # no distances: the places in the list stand in
    assert not without.by_meaning


def test_without_an_idea_each_group_is_a_disc_the_largest_first() -> None:
    groups = [[1, 2, 3, 4, 5], list(range(10, 30)), list(range(40, 52)), [60, 61, 62]]
    drawn = made(groups, ranked=False)
    assert [group.size for group in drawn.groups] == [20, 12, 5, 3]  # the largest, first colour
    assert {dot.group for dot in drawn.dots if dot.project_id >= 10 and dot.project_id < 30} == {1}
    assert all(dot.rank is None for dot in drawn.dots)
    assert apart(drawn.dots) and all(inside(drawn.box, dot) for dot in drawn.dots)
    first = [dot for dot in drawn.dots if dot.group == 1]
    middle = (sum(dot.x for dot in first) / len(first), sum(dot.y for dot in first) / len(first))
    nearest = min(first, key=lambda dot: math.hypot(dot.x - middle[0], dot.y - middle[1]))
    assert nearest.project_id == 10  # the most central project stands nearest the middle
    tops = [group.y for group in drawn.groups]
    assert tops[0] == pytest.approx(tops[1]) and tops[2] > tops[0]  # two rows of two


def test_a_strong_line_joins_only_projects_on_the_graph() -> None:
    drawn = made([[1, 2, 3], [4, 5, 6]], ranked=False, linked=[[1, 5, 99], [2, 4], [77, 78]])
    assert [(line.a, line.b) for line in drawn.lines] == [(1, 5), (2, 4)]
    assert drawn.view_box.count(" ") == 3
