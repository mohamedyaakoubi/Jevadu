"""The graph of a list (design 8.6, S7): a dot for each project, in the colour of its group.

With an idea, the idea stands in the middle, and each project stands as far from it as it is far
in meaning, compared with the others of the list, in the part of the circle that belongs to its
group; the first 10 of the list are numbered as in the list. Without an idea, the groups stand
around the middle, and the projects of a group around its most central project. In both, the
projects nearest the middle line of a group's part, or the middle of its disc, are the most
typical of the group. A strong line joins projects with the same code or the same Hedera ID
(design 8.4). Nothing here is written by a model, and nothing judges quality: closeness is
similarity of meaning.

The places are computed here, so that the page draws the graph with no script; the script of the
page only shows a project while the pointer rests on it, with a line to its closest project.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

MOST = 300  # the longest list that is drawn: every event of the collection fits (271 at most)
FIRST = 10  # the first projects of a search, numbered on the graph as in the list
# Four colours stay apart for every reader when any two of them meet, in the light and in the
# dark theme (the validator of the colours, run with all pairs on 23 October 2026); five do not.
GROUPS_AT_MOST = 4
NAME_LENGTH = 24  # the longest name in a label of the graph; the lists under it give it whole

# With an idea: the nearest and the farthest a project stands from it, in the units of the box.
NEAR, FAR = 56.0, 250.0
SECTOR_GAP = math.radians(12)  # between the parts of two groups
SECTOR_MIN = math.radians(50)  # the smallest part of the circle that a group gets
EDGE = math.radians(4)  # kept free inside each part
NUMBERED, PLAIN = 9.0, 5.5  # the radius of a numbered dot, and of the others

# The sizes of the text, to keep room for it (a letter is about 0.56 of its size in width).
TITLE, SUBTITLE, LINE = 13.0, 12.0, 16.0
MARGIN = 14.0


def group_count(size: int) -> int:
    """How many groups a list of `size` projects is cut into: one under 6 projects, then one
    more for each larger size, and GROUPS_AT_MOST from 30."""
    if size < 6:
        return 1
    if size < 16:
        return 2
    if size < 30:
        return 3
    return GROUPS_AT_MOST


def shortened(name: str, length: int = NAME_LENGTH) -> str:
    return name if len(name) <= length else name[: length - 1].rstrip() + "…"


def width_of(text: str, size: float) -> float:
    return 0.56 * size * len(text)


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'s' if count != 1 else ''}"


@dataclass(frozen=True)
class Group:
    number: int  # 1 to 4: its place, and its colour
    size: int
    category: str  # the category that most of its projects share; "" when none has one
    sharing: int  # how many of its projects have that category
    centre_id: int  # its most central project, after which it is named
    centre_name: str
    x: float = 0.0  # where its name stands
    y: float = 0.0
    anchor: str = "middle"

    @property
    def title(self) -> str:
        return f"Like {shortened(self.centre_name)}"

    def _shared(self) -> str:
        if not self.sharing:
            return ""
        if self.size == 1:
            return self.category
        return f"{'all' if self.sharing == self.size else self.sharing} in {self.category}"

    @property
    def subtitle(self) -> str:
        shared = self._shared()
        return plural(self.size, "project") + (f" · {shared}" if shared else "")

    @property
    def said(self) -> str:
        """Its size and category, in the words of the lists under the graph."""
        shared = self._shared()
        return plural(self.size, "project") + (f", {shared}" if shared else "")

    @property
    def wide(self) -> float:
        """The width of its name on the graph."""
        return max(width_of(self.title, TITLE), width_of(self.subtitle, SUBTITLE))


@dataclass(frozen=True)
class Dot:
    project_id: int
    group: int
    x: float
    y: float
    r: float
    rank: int | None  # its place in the search; None for a list without an idea
    near: int | None  # its closest project of the list in meaning


@dataclass(frozen=True)
class Line:
    a: int
    b: int
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True)
class Graph:
    dots: tuple[Dot, ...]
    lines: tuple[Line, ...]  # the projects with the same code or Hedera ID
    groups: tuple[Group, ...]
    ranked: bool  # drawn around an idea
    box: tuple[float, float, float, float]  # the view box: left, top, width, height
    by_meaning: bool = True  # with an idea: the distances are closeness in meaning, not places
    left_out: int = 0  # the projects of the list that have no embedding, so no place

    @property
    def view_box(self) -> str:
        return " ".join(f"{value:g}" for value in self.box)

    def members(self, number: int) -> list[Dot]:
        """The dots of one group, in the order of the list."""
        return [dot for dot in self.dots if dot.group == number]


def named(members: Sequence[int], categories: Mapping[int, str]) -> tuple[str, int]:
    """The category that most of the projects share, and how many share it; ("", 0) when none
    has one. On a tie, the category of the first project that has one of the tied ones."""
    counted = Counter(categories[pid] for pid in members if categories.get(pid))
    if not counted:
        return "", 0
    most = max(counted.values())
    first = next(categories[pid] for pid in members if counted.get(categories.get(pid, "")) == most)
    return first, most


def _spans(sizes: Sequence[int]) -> list[float]:
    """The part of the circle of each group: as its share of the projects, never under
    SECTOR_MIN, with SECTOR_GAP between two parts."""
    free = 2 * math.pi - SECTOR_GAP * len(sizes)
    whole = sum(sizes)
    spans = [free * size / whole for size in sizes]
    small = [span < SECTOR_MIN for span in spans]
    if any(small) and not all(small):
        left = free - SECTOR_MIN * sum(small)
        rest = sum(size for size, low in zip(sizes, small, strict=True) if not low)
        spans = [SECTOR_MIN if low else left * size / rest
                 for size, low in zip(sizes, small, strict=True)]  # fmt: skip
    return spans


def _distances(order: Sequence[int], distance: Mapping[int, float] | None) -> dict[int, float]:
    """How far from the idea each project stands: as far as it is in meaning, between NEAR for
    the closest of the list and FAR for the farthest; by its place in the list when the
    distances in meaning are not known."""
    if distance is None or any(pid not in distance for pid in order):
        span = max(len(order) - 1, 1)
        return {pid: NEAR + (FAR - NEAR) * place / span for place, pid in enumerate(order)}
    low, high = min(distance[pid] for pid in order), max(distance[pid] for pid in order)
    if high - low < 1e-9:
        return dict.fromkeys(order, (NEAR + FAR) / 2)
    return {pid: NEAR + (FAR - NEAR) * (distance[pid] - low) / (high - low) for pid in order}


def _apart(angles: dict[int, float], limits: Mapping[int, tuple[float, float]],
           radius: Mapping[int, float], size: Mapping[int, float]) -> None:  # fmt: skip
    """Turn the dots of each group apart on their circles until no two overlap, inside the part
    of their group. `angles` holds the angle of each dot, and changes."""
    ids = sorted(angles)
    for _ in range(80):
        moved = False
        for i, one in enumerate(ids):
            for two in ids[i + 1 :]:
                if limits[one] != limits[two]:
                    continue  # two groups never meet: their parts are apart
                a, b = angles[one], angles[two]
                dx = radius[one] * math.cos(a) - radius[two] * math.cos(b)
                dy = radius[one] * math.sin(a) - radius[two] * math.sin(b)
                need = size[one] + size[two] + 2.5
                if dx * dx + dy * dy >= need * need:
                    continue
                turn = (need - math.hypot(dx, dy)) / (radius[one] + radius[two])
                low, high = (one, two) if (a, one) <= (b, two) else (two, one)
                for pid, sign in ((low, -1.0), (high, 1.0)):
                    start, end = limits[pid]
                    angles[pid] = min(end, max(start, angles[pid] + sign * turn))
                moved = True
        if not moved:
            return


def around_idea(order: Sequence[int], groups: Sequence[Sequence[int]],
                distance: Mapping[int, float] | None) -> tuple[dict, list]:  # fmt: skip
    """The places of the projects of a search, closest first, around the idea at (0, 0), and the
    place of the name of each group: (x, y, anchor). Each group of `groups` lists its projects
    from the most typical, which stands on the middle line of its part, to the least typical,
    which stands at its edges."""
    spans = _spans([len(group) for group in groups])
    rank = {pid: place for place, pid in enumerate(order, start=1)}
    radius = _distances(order, distance)
    size = {pid: NUMBERED if rank[pid] <= FIRST else PLAIN for pid in order}
    edge = max(radius.values()) + 24  # the names of the groups stand outside the farthest dot
    angles: dict[int, float] = {}
    limits: dict[int, tuple[float, float]] = {}
    labels = []
    start = -math.pi / 2 + SECTOR_GAP / 2  # the first group starts at the top, clockwise
    for group, span in zip(groups, spans, strict=True):
        axis, half = start + span / 2, span / 2 - EDGE
        step = 2 * half / (len(group) - 1) if len(group) > 1 else 0.0
        middle = (len(group) - 1) / 2
        slots = sorted((axis + (place - middle) * step for place in range(len(group))),
                       key=lambda angle: (abs(angle - axis), angle))  # fmt: skip
        for pid, angle in zip(group, slots, strict=True):
            angles[pid] = angle
            limits[pid] = (axis - half, axis + half)
        labels.append(_label_at(axis, edge))
        start += span + SECTOR_GAP
    _apart(angles, limits, radius, size)
    places = {pid: (radius[pid] * math.cos(angles[pid]), radius[pid] * math.sin(angles[pid]),
                    size[pid]) for pid in order}  # fmt: skip
    return places, labels


def _label_at(angle: float, distance: float) -> tuple[float, float, str]:
    """Where the two lines of a group's name stand, outside the circle in the middle of its part:
    the first line's base, and the side the text grows to."""
    x, y = distance * math.cos(angle), distance * math.sin(angle)
    anchor = "start" if math.cos(angle) > 0.35 else "end" if math.cos(angle) < -0.35 else "middle"
    if math.sin(angle) < -0.35:
        y -= LINE  # above: the second line ends at the circle
    elif math.sin(angle) <= 0.35:
        y -= LINE / 2 - 4  # beside: the two lines stand around the middle of the part
    else:
        y += TITLE  # below
    return x, y, anchor


LABEL_ROOM = 2 * LINE + 12  # above each group, for its name
CELL_GAP = 28.0  # between two groups, side by side or one over the other


def in_groups(groups: Sequence[Sequence[int]], widths: Sequence[float]) -> tuple[dict, list]:
    """The places of the projects of a list without an idea: each group as a disc, its projects
    from the most typical, in the middle, outwards; up to three discs in a row, four in two rows,
    each under its name, whose width is in `widths`. And the place of the name of each group."""
    total = sum(len(group) for group in groups)
    dot = 6.0 if total <= 60 else 5.0 if total <= 150 else 4.0
    # The seeds of a sunflower: the i-th at the golden angle from the one before, at a distance
    # from the middle that grows as the root of i + 1/2. Two seeds are then never closer than
    # 1.546 times the step (measured for 300 seeds on 24 October 2026), so the dots never touch.
    space = (2 * dot + 2.5) / 1.54
    golden = math.pi * (3 - math.sqrt(5))
    discs = []
    for group in groups:
        seeds = [(space * math.sqrt(i + 0.5) * math.cos(i * golden),
                  space * math.sqrt(i + 0.5) * math.sin(i * golden))
                 for i in range(len(group))]  # fmt: skip
        discs.append((seeds, max(math.hypot(x, y) for x, y in seeds) + dot))
    columns = len(groups) if len(groups) <= 3 else 2
    cells = [(i // columns, i % columns) for i in range(len(groups))]
    wide = [max(max(2 * discs[i][1], widths[i]) for i, (_, column) in enumerate(cells)
                if column == c) for c in range(columns)]  # fmt: skip
    rows = max(row for row, _ in cells) + 1
    tall = [max(2 * discs[i][1] for i, (row, _) in enumerate(cells) if row == r)
            for r in range(rows)]  # fmt: skip
    places = {}
    labels = []
    for group, (seeds, reach), (row, column) in zip(groups, discs, cells, strict=True):
        cx = sum(wide[:column]) + CELL_GAP * column + wide[column] / 2
        top = sum(tall[:row]) + (LABEL_ROOM + CELL_GAP) * row
        cy = top + LABEL_ROOM + reach  # each disc right under its name, the names of a row level
        for pid, (x, y) in zip(group, seeds, strict=True):
            places[pid] = (cx + x, cy + y, dot)
        labels.append((cx, cy - reach - LINE - 8, "middle"))
    return places, labels


IDEA_NAME = (-36.0, -10.0, 36.0, 28.0)  # the room of the idea's dot and its name, around (0, 0)


def _box(places: Mapping[int, tuple[float, float, float]], groups: Sequence[Group],
         ranked: bool) -> tuple[float, float, float, float]:  # fmt: skip
    """The view box around the dots, the names of the groups, and the idea with its name."""
    left = top = math.inf
    right = bottom = -math.inf

    def take(x0: float, y0: float, x1: float, y1: float) -> None:
        nonlocal left, top, right, bottom
        left, top, right, bottom = min(left, x0), min(top, y0), max(right, x1), max(bottom, y1)

    for x, y, r in places.values():
        take(x - r, y - r, x + r, y + r)
    for group in groups:
        x0 = {"start": group.x, "end": group.x - group.wide}.get(
            group.anchor, group.x - group.wide / 2
        )
        take(x0, group.y - TITLE, x0 + group.wide, group.y + LINE + 4)
    if ranked:
        take(*IDEA_NAME)
    return (
        round(left - MARGIN, 1),
        round(top - MARGIN, 1),
        round(right - left + 2 * MARGIN, 1),
        round(bottom - top + 2 * MARGIN, 1),
    )


def build(
    order: Sequence[int],
    found: Sequence[Sequence[int]],
    *,
    typical: Mapping[int, float],
    nearest: Mapping[int, int],
    centres: Sequence[int],
    categories: Mapping[int, str],
    names: Mapping[int, str],
    ranked: bool,
    distance: Mapping[int, float] | None = None,
    linked: Sequence[Sequence[int]] = (),
    left_out: int = 0,
) -> Graph:
    """The graph of the projects of `order`, closest first when `ranked`, in the groups of
    `found`, each with its most central project in `centres`. `typical` gives the similarity of
    each project to the most central one of its group, `nearest` the closest project of each,
    `distance` the cosine distance of each project to the idea (its places in the list stand in
    when it is None), and `linked` the groups of projects with the same code or Hedera ID
    (search/seen.py). `left_out` counts the projects of the list that could not be placed."""
    together = list(zip(found, centres, strict=True))
    if not ranked:  # the largest group first, so that it takes the first colour
        together.sort(key=lambda one: -len(one[0]))
    # each group from its most typical project: the closest to its most central one
    ordered = [[centre, *sorted((pid for pid in group if pid != centre),
                                key=lambda pid: (-typical.get(pid, 0.0), pid))]
               for group, centre in together]  # fmt: skip
    groups = [Group(number, len(group), *named(group, categories), centre, names.get(centre, ""))
              for number, (group, centre) in enumerate(together, start=1)]  # fmt: skip
    if ranked:
        places, labels = around_idea(order, ordered, distance)
    else:
        places, labels = in_groups(ordered, [group.wide for group in groups])
    groups = [replace(group, x=round(x, 1), y=round(y, 1), anchor=anchor)
              for group, (x, y, anchor) in zip(groups, labels, strict=True)]  # fmt: skip
    group_of = {pid: number for number, group in enumerate(ordered, start=1) for pid in group}
    rank = {pid: place for place, pid in enumerate(order, start=1)} if ranked else {}
    dots = tuple(Dot(pid, group_of[pid], round(places[pid][0], 1), round(places[pid][1], 1),
                     places[pid][2], rank.get(pid), nearest.get(pid))
                 for pid in order if pid in places)  # fmt: skip
    joined: set[tuple[int, int]] = set()
    for linked_ids in linked:
        shown = [pid for pid in linked_ids if pid in places]
        for i, one in enumerate(shown):
            for two in shown[i + 1 :]:
                joined.add((min(one, two), max(one, two)))
    lines = tuple(Line(a, b, round(places[a][0], 1), round(places[a][1], 1),
                       round(places[b][0], 1), round(places[b][1], 1))
                  for a, b in sorted(joined))  # fmt: skip
    by_meaning = distance is not None and all(pid in distance for pid in order)
    return Graph(dots, lines, tuple(groups), ranked, _box(places, groups, ranked),
                 by_meaning, left_out)  # fmt: skip
