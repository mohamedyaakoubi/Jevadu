"""The groups of the graph (design 8.6), measured (31 October 2026).

    python -m evals.graph_groups

Ward's method builds the whole tree of joins and chooses no number of groups: the graph cuts it
at 1, 2, 3 or 4 groups by the size of its list (web/graph.py), four at most for the colours. Is
that the number that fits the projects best, and do the projects form groups at all? This measure
takes the lists that the graph draws, with no model call:

- around each project, it and its 49 closest projects: the shape of a search's 50, with the
  project's own embedding in the place of an idea's, which would cost a call to Google;
- the projects of each event that the graph cuts (6 projects or more);
- the whole collection, as the graph shows it with no search and no filter.

Each list is cut by the tool's own code (search/closeness.py) into 2 to 8 groups (more than 4 for
comparison only: the graph has four colours), and each cut gets its silhouette (Rousseeuw 1987):
for each project, how much nearer it is to its own group than to the nearest other group, from -1
to 1, averaged over the list; a project alone in its group counts 0. The usual reading, as the
Wikipedia page of the silhouette gives it (read on 31 October 2026): an average over 0.70 is a
strong structure, over 0.50 a reasonable one, over 0.25 a weak one. The distance is the one of
Ward's method here: the straight line between two embeddings of length one, the square root of
2 (1 - their cosine similarity).

It writes evals/results/<UTC time>-graph-groups.json: numbers only, the events by their number in
the database, never a text of a page.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from hackathon_memory.search import closeness
from hackathon_memory.settings import Settings
from hackathon_memory.web.graph import GROUPS_AT_MOST, group_count

RESULTS = Path(__file__).parent / "results"
AROUND = 50  # a search shows its 50 closest projects (web/app.py, SHOWN)
CUTS = range(2, 9)  # 2 to 8 groups; the graph draws at most GROUPS_AT_MOST
FEWEST = 6  # under 6 projects the graph draws one group (web/graph.py)
NO_STRUCTURE = 0.25  # the usual reading: over 0.25, at least a weak structure


def distance(pairs: closeness.Pairs, a: int, b: int) -> float:
    return math.sqrt(max(0.0, 2.0 * (1.0 - closeness.similarity(pairs, a, b))))


def silhouette(found: Sequence[Sequence[int]], pairs: closeness.Pairs) -> float:
    """The mean silhouette of the projects in the groups of `found`; a project alone in its group
    counts 0, as Rousseeuw sets it, and so does a list in one group."""
    if len(found) < 2:
        return 0.0
    scores = []
    for index, group in enumerate(found):
        for pid in group:
            if len(group) == 1:
                scores.append(0.0)
                continue
            own = sum(distance(pairs, pid, other) for other in group if other != pid)
            own /= len(group) - 1
            near = min(sum(distance(pairs, pid, other) for other in others) / len(others)
                       for number, others in enumerate(found) if number != index)  # fmt: skip
            scores.append((near - own) / max(own, near) if max(own, near) else 0.0)
    return sum(scores) / len(scores)


def cuts(order: Sequence[int], pairs: closeness.Pairs) -> dict[int, float]:
    """The silhouette of the list cut by the tool's own code into each number of CUTS that it
    allows (fewer groups than projects)."""
    return {count: round(silhouette(closeness.groups(order, pairs, count), pairs), 4)
            for count in CUTS if count < len(order)}  # fmt: skip


def summary(lists: Sequence[Mapping[int, float]], rules: Sequence[int]) -> dict:
    """For lists that were cut: the mean and the median silhouette of each number of groups, how
    often each number fits best (among those the graph can draw, and among all), how often the
    graph's own number is the best that it can draw, and how many lists have any structure."""
    by_count: dict[int, list[float]] = defaultdict(list)
    for scores in lists:
        for count, score in scores.items():
            by_count[count].append(score)
    drawable = [max((c for c in scores if c <= GROUPS_AT_MOST), key=scores.get) for scores in lists]
    anywhere = [max(scores, key=scores.get) for scores in lists]
    return {
        "lists": len(lists),
        "silhouette": {str(count): {"mean": round(statistics.mean(values), 4),
                                    "median": round(statistics.median(values), 4)}
                       for count, values in sorted(by_count.items())},
        "best_of_2_to_4": {str(c): drawable.count(c) for c in sorted(set(drawable))},
        "best_of_2_to_8": {str(c): anywhere.count(c) for c in sorted(set(anywhere))},
        "the_rule_is_the_best_of_2_to_4": sum(rule == best
                                              for rule, best in zip(rules, drawable, strict=True)),
        "best_above_0_25": sum(max(scores.values()) > NO_STRUCTURE for scores in lists),
        "highest": round(max(max(scores.values()) for scores in lists), 4),
    }  # fmt: skip


def main(argv: Sequence[str]) -> int:
    settings = Settings()
    conninfo = settings.database_conninfo()
    model = settings.gemini_embedding_model
    with psycopg.connect(conninfo) as conn:
        events = conn.execute("SELECT id, event_id FROM projects ORDER BY id").fetchall()
    every = sorted(closeness.with_embedding(conninfo, [pid for pid, _ in events], model=model))
    pairs = closeness.similarities(conninfo, every, model=model)
    around = []
    for pid in every:
        closest = sorted((other for other in every if other != pid),
                         key=lambda other: -closeness.similarity(pairs, pid, other))  # fmt: skip
        around.append(cuts([pid, *closest[: AROUND - 1]], pairs))
    kept, by_event = set(every), defaultdict(list)
    for pid, event in events:
        if pid in kept:
            by_event[event].append(pid)
    event_lists = {event: ids for event, ids in sorted(by_event.items()) if len(ids) >= FEWEST}
    event_scores = {event: cuts(ids, pairs) for event, ids in event_lists.items()}
    whole = cuts(every, pairs)
    now = datetime.now(UTC)
    result = {
        "test": "graph-groups",
        "made_on": now.date().isoformat(),
        "model": model,
        "distance": "sqrt(2 (1 - cosine similarity))",
        "projects": len(every),
        "around_each_project": {"size": AROUND, "rule": group_count(AROUND),
                                **summary(around, [group_count(AROUND)] * len(around))},
        "events": {
            **summary(list(event_scores.values()),
                      [group_count(len(ids)) for ids in event_lists.values()]),
            "by_event": [{"event": event, "projects": len(ids), "rule": group_count(len(ids)),
                          "silhouette": {str(c): s for c, s in event_scores[event].items()}}
                         for event, ids in event_lists.items()],
        },
        "whole_collection": {"projects": len(every), "rule": group_count(len(every)),
                             "silhouette": {str(c): s for c, s in whole.items()}},
    }  # fmt: skip
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{now:%Y%m%dT%H%M%SZ}-graph-groups.json"
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    for name in ("around_each_project", "events"):
        part = result[name]
        print(f"{name}: {part['lists']} lists; silhouette by groups {part['silhouette']}")
        print(
            f"  best of 2 to 4 {part['best_of_2_to_4']}; the rule is the best "
            f"{part['the_rule_is_the_best_of_2_to_4']}; above 0.25 {part['best_above_0_25']}"
        )
    print(f"whole collection: {result['whole_collection']}")
    print(f"Written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
